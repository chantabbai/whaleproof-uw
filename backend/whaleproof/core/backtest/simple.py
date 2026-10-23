"""Simple-rules backtest (pre-registration Amendment 3): every alert that passes the pure-directional gate, tagged
with its setup — no top-40 cut, no 5/day cap, no weighted score. Outcomes need only daily prices, so it covers far
more trades than the check-based backtest. Gate failures are kept as the noise control group."""
from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta

from whaleproof import market_calendar as mc
from whaleproof.core.data_layer.context import KIND_IVR, oi_ratio
from whaleproof.core.data_layer.models import FlowAlert, row_to_alert
from whaleproof.core.data_layer.store import Store
from whaleproof.core.verdict.setups import PUT_SALE, gate_failures, is_put_sale, setup_for

from .outcomes import forward_returns
from whaleproof.core.options.pricing import value_view

from .option_prices import real_option_return

from .runner import COST, BacktestRow, _spy_trend, repeat_count

AS_OF_DELAY = timedelta(minutes=15)   # same decision cut as run_backtest / live scan


def _net(x: float | None) -> float | None:
    return None if x is None else x - COST


def day_trades(store: Store, d: date) -> list[tuple[FlowAlert, list[str], bool]]:
    """(alert, gate failures, is put_sale) for the biggest alert per (ticker, direction, kind) known by D close
    + 15 min; kind = pure / put_sale / noise. put_sale rows stand apart (Amendment 9)."""
    as_of = mc.session_close(d) + AS_OF_DELAY
    alerts = [a for a in (row_to_alert(r) for r in store.alerts_between(d, d)) if a.created_at <= as_of]
    by_ticker = defaultdict(list)
    for a in alerts:
        by_ticker[a.ticker].append(a)
    best: dict[tuple[str, int, str], tuple[FlowAlert, list[str], bool]] = {}
    for a in alerts:
        if a.direction == 0:
            continue
        fails = gate_failures(a, by_ticker[a.ticker], as_of)
        sale = bool(fails) and is_put_sale(a, by_ticker[a.ticker], as_of)
        k = (a.ticker, a.direction, "pure" if not fails else PUT_SALE if sale else "noise")
        if k not in best or a.total_premium > best[k][0].total_premium:
            best[k] = (a, fails, sale)
    # a ticker+direction that has a clean buy is a trade; its noisier alerts are not a separate control row
    return sorted((v for k, v in best.items() if k[2] != "noise" or (k[0], k[1], "pure") not in best),
                  key=lambda t: (-t[0].total_premium, t[0].ticker))


def option_view(store: Store, a: FlowAlert) -> str:
    """Cheap / fair / rich from data known on the flow day (trailing realized vol, else IV rank)."""
    d = a.session_date.isoformat()
    hist = store.get_metric(a.ticker, "all", "vol_hist") or []
    trailing = [(end, rv) for _, _, rv, end in hist if rv and end and end[:10] <= d]
    ivr = store.latest_metric(a.ticker, a.session_date, KIND_IVR)
    return value_view(a.iv, max(trailing)[1] if trailing else None, ivr[1] if ivr else None)["verdict"]


def run_simple_backtest(store: Store, start: date, end: date) -> tuple[list[BacktestRow], int]:
    out: list[BacktestRow] = []
    skipped = 0
    for d in mc.sessions(start, end):
        spy = forward_returns(store.get_ohlc("SPY", d, d + timedelta(days=45)), d, 1)
        trend = _spy_trend(store, d)
        for a, fails, sale in day_trades(store, d):
            fr = forward_returns(store.get_ohlc(a.ticker, d, d + timedelta(days=45)), d, a.direction)
            if fr is None:
                skipped += 1
                continue
            setup = (PUT_SALE if sale else None) if fails else setup_for(
                a, [date.fromisoformat(x) for x in store.get_metric(a.ticker, "all", "earnings") or []],
                repeat_count(store, a, mc.session_close(d) + AS_OF_DELAY))
            r5 = _net(fr["r5"])
            exit_day = fr["entry_date"]
            for _ in range(4):
                exit_day = mc.next_session(exit_day)          # close of the 5th session, same as r5
            opt = real_option_return(store, a.option_chain, fr["entry_date"], exit_day)
            out.append(BacktestRow(
                session_date=d, ticker=a.ticker, direction=a.direction, alert_id=a.id, score=0.0,
                label="PUT_SALE" if sale else "PURE" if setup else "NOISE", coverage=0.0, scores={}, available={},
                r1=_net(fr["r1"]), r5=r5, r20=_net(fr["r20"]), mfe20=fr["mfe20"], mae20=fr["mae20"],
                x5=(r5 - spy["r5"] * a.direction) if r5 is not None and spy and spy["r5"] is not None else None,
                dte=a.dte, premium=a.total_premium, issue_type=a.issue_type,
                sector=store.get_metric(a.ticker, "all", "sector") or None,
                setup=setup, gate_fail=fails[0] if fails else None,
                oi_ratio=oi_ratio(store, a), otm_pct=a.otm_pct, spy_trend=trend, value=option_view(store, a),
                opt_r5=opt["ret"] if opt else None, opt_spread=opt["spread_pct"] if opt else None,
                opt_r5_mid=opt["ret_mid"] if opt else None, opt_r5_wide=opt["ret_wide"] if opt else None))
    out.sort(key=lambda r: (r.session_date, r.ticker, r.direction))
    return out, skipped


def missing_price_tickers(store: Store, start: date, end: date) -> list[str]:
    """Gate-passing (and put_sale) tickers with no daily bars yet — what a price-only fill needs to fetch."""
    need = set()
    for d in mc.sessions(start, end):
        for a, fails, sale in day_trades(store, d):
            if (sale or not fails) and not store.get_ohlc(a.ticker, d, d + timedelta(days=10)):
                need.add(a.ticker)
    return sorted(need)
