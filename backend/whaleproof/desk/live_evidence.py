"""Live row of 'Does the filter help?': live days (from FORWARD_START) scored exactly like the four history periods —
the same run_simple_backtest, the same row/extra conversion the history pickles use, classify_rows, window_report.
Index options are left out because UW's history replies drop them, so history days never had them.

Prices: every one-way bet's ticker needs a daily bar on its exit day. The close job fetches them (`due_tickers`,
1 call per ticker, once per close day) — the desk otherwise prices only signal tickers. Bets with no prices yet are
counted (`unpriced`; bets still in their hold are `open`) so a half-priced comparison never reads as complete. Rows are UW-derived: never committed."""
from __future__ import annotations

import json
from datetime import date, timedelta

from whaleproof import market_calendar as mc
from whaleproof.core.backtest.simple import day_trades, run_simple_backtest
from whaleproof.core.data_layer.store import Store

from .config import FORWARD_START, INDEX_TICKERS as INDEX
from .history import HistRow, classify_rows, earnings_map
from .signals import exit_session

EXTRA_KEYS = ("has_sweep", "iv", "underlying_price", "created_at", "option_chain", "type", "strike", "expiry",
              "total_size", "open_interest", "volume")


def extras(store: Store, rows) -> dict:
    """Alert fields the history pickles carry next to each row (scripts/desk_build_rows.py uses this too)."""
    out = {}
    for r in rows:
        p = store.conn.execute("SELECT payload FROM flow_alerts WHERE id=?", (r.alert_id,)).fetchone()
        if p:
            a = json.loads(p[0])
            out[r.alert_id] = {k: a.get(k) for k in EXTRA_KEYS}
    return out


def rows(store: Store, start: date, end: date) -> dict:
    """{'rows': [HistRow], 'unpriced': finished bets with no prices, 'open': bets still in their 5-session hold} for
    live sessions start..end, index options left out."""
    import dataclasses
    bt, _ = run_simple_backtest(store, start, end)
    bt = [r for r in bt if r.ticker not in INDEX]
    ex = extras(store, bt)
    raw = [(dataclasses.asdict(r), ex.get(r.alert_id, {})) for r in bt]
    hist = classify_rows(raw, earnings_map(store))
    done = {d for d in mc.sessions(start, end) if exit_session(d) <= end}
    bets = {d: sum(1 for a, _, _ in day_trades(store, d) if a.ticker not in INDEX) for d in mc.sessions(start, end)}
    scored = {h.alert_id for h in hist if h.x5 is not None}
    unpriced = sum(n for d, n in bets.items() if d in done) - sum(1 for r in bt if r.alert_id in scored)
    return {"rows": hist, "unpriced": max(unpriced, 0), "open": sum(n for d, n in bets.items() if d not in done)}


def due_tickers(store: Store, close_day: date, start: date = FORWARD_START) -> list[str]:
    """Tickers of one-way bets whose 5-session hold ended by `close_day` but whose exit-day bar isn't saved."""
    need: set[str] = set()
    for d in mc.sessions(start, close_day):
        ex = exit_session(d)
        if ex > close_day:
            break
        for a, _, _ in day_trades(store, d):
            if a.ticker not in INDEX and a.ticker not in need and not store.get_ohlc(a.ticker, ex, ex):
                need.add(a.ticker)
    return sorted(need)


def exit_tickers(store: Store, day: date, start: date = FORWARD_START) -> list[str]:
    """Tickers of one-way bets whose 5-session hold ended on `day`: their exit-day bar (fetched at 16:15) can be the
    last trade before the closing auction, so tracker.settle_update refetches them the next morning."""
    out: set[str] = set()
    for d in mc.sessions(max(start, day - timedelta(days=14)), day):
        if exit_session(d) == day:
            out |= {a.ticker for a, _, _ in day_trades(store, d) if a.ticker not in INDEX}
    return sorted(out)


def report(store: Store, end: date, counts: dict[date, int], window_report) -> dict:
    out = rows(store, FORWARD_START, end)
    hist: list[HistRow] = out["rows"]
    return {"window": [FORWARD_START.isoformat(), end.isoformat()], "label": "live (signals nobody had seen)",
            "unpriced": out["unpriced"], "open": out["open"], **window_report(hist, counts)}
