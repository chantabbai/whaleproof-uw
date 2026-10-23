"""Signal tracker: what happened to every Signal Desk signal — stock entry/exit, P/L, vs S&P 500, peak and drawdown,
and what the whale's own option would have done instead.

Same definitions as the backtest rows (so the page agrees with Methodology):
stock  = buy the next session's open, sell the close of the 5th session, minus COST (forward_returns + runner.COST);
option = the whale's exact contract, buy = entry-day opening trade + half the bid/ask gap, sell = closing bid
         (real_option_return). Open signals are marked at the latest daily close. Missing data → None, never guessed.
Prices update once a day after the close (DeskService close job), so every row says what date it is priced through."""
from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from whaleproof import market_calendar as mc
from whaleproof.core.backtest.option_prices import _num, history, real_option_return
from whaleproof.core.backtest.runner import COST
from whaleproof.core.data_layer.ingest import ingest_bars, ingest_contract_oi
from whaleproof.core.data_layer.models import Bar

from .config import FORWARD_START, HOLD_SESSIONS
from .history import HOLDOUT_LABEL, POST_LABEL, PRE_LABEL, TRAIN_LABEL, HistRow, period_label
from .signals import exit_session

LIVE_PERIOD = "Live (from Sep 30, 2026)"
PERIODS = [POST_LABEL, HOLDOUT_LABEL, TRAIN_LABEL, PRE_LABEL]
CSV_COLS = ["signal_day", "ticker", "period", "tier", "premium", "otm_pct", "status", "entry_date", "entry", "exit_date",
            "exit", "last", "days_held", "stock_return", "vs_sp500", "peak", "peak_date", "drawdown", "drawdown_date",
            "option_contract", "option_buy", "option_sell", "option_return", "option_peak", "option_drawdown", "priced_through"]


def stock_move(entry: float | None, price: float | None, direction: int) -> dict:
    """The one definition of a signal's stock result, used by every page and the MCP.
    move = price change in the signal's direction (what a broker shows on an open position, no fees);
    net  = move minus the 0.10% round-trip cost (what the backtest, Track record and How it works score)."""
    if not entry or not price:
        return {"move": None, "net": None}
    move = (price / entry - 1) * direction
    return {"move": move, "net": move - COST}


def mark_price(spot: float | None, spot_at: str | None, bars: list[Bar], now: datetime) -> tuple[float | None, str | None]:
    """Price an open hold is marked at. Live quote only while the regular session is open and the quote is from
    today; otherwise the latest daily close, so after the bell every page shows the same number."""
    today = now.astimezone(mc.NY).date()
    if (spot and spot_at and mc.market_state(now)["state"] == "open"
            and datetime.fromisoformat(spot_at).astimezone(mc.NY).date() == today):
        return spot, "live"
    return (bars[-1].close, "close") if bars else (None, None)


def live_mark(bars: list[Bar], entry_on: date, direction: int, spot: float | None, spot_at: str | None,
              now: datetime) -> dict:
    """An open hold right now — the one price Sightings, the ticker page and Track record show for it. Entry = first
    open on/after the entry day (today's unfinished bar counts), price = mark_price. Display only: the record's
    results (ret, vs_spy) stay on daily closes."""
    held = [b for b in bars if b.date >= entry_on]
    entry = held[0].open if held and held[0].open else None
    price, src = mark_price(spot, spot_at, held, now)
    m = stock_move(entry, price, direction)
    return {"entry": entry, "price": price, "source": src, "at": spot_at if src == "live" else None,
            "move": m["move"], "net": m["net"]}


def today_move(bars: list[Bar], entry_on: date, direction: int, spot: float | None, spot_at: str | None,
               now: datetime) -> dict:
    """An open hold's move today (Sightings tape): the same price as live_mark, against yesterday's close — or against
    the entry open when the hold was bought this session. `day` = the session that price belongs to; `since` = which
    base was used ("entry_open" / "prev_close"), so the tape can say so. Display only."""
    price, src = mark_price(spot, spot_at, bars, now)
    if price is None:
        return {"move": None, "day": None, "price": None, "since": None}
    day = now.astimezone(mc.NY).date() if src == "live" else bars[-1].date
    held = [b for b in bars if b.date >= entry_on]
    since = None
    if held and held[0].date == day:
        base, since = held[0].open, "entry_open"
    elif entry_on >= day:                      # bought this session, open not saved yet: no move to show
        base = None
    else:
        prev = [b for b in bars if b.date < day]
        base, since = (prev[-1].close, "prev_close") if prev else (None, None)
    return {"move": (price / base - 1) * direction if base else None, "day": day, "price": price,
            "since": since if base else None}


def option_now(buy: float | None, quote: dict | None, quote_at: str | None, now: datetime) -> dict | None:
    """The whale's option in an open hold, live: the bid now (the record's sell rule) against what was paid. Only while
    the market is open with a quote from today; otherwise None and pages keep the last closing bid. Display only."""
    bid = _num((quote or {}).get("bid"))
    if (not buy or not bid or not quote_at or mc.market_state(now)["state"] != "open"
            or datetime.fromisoformat(quote_at).astimezone(mc.NY).date() != now.astimezone(mc.NY).date()):
        return None
    return {"bid": bid, "at": quote_at, "ret": bid / buy - 1}


def hold_day(entry: date, now: datetime) -> int:
    """Day N of the hold: sessions from the entry open through now, today counted once the market has opened."""
    local = now.astimezone(mc.NY)
    n, d = 0, entry if mc.is_session(entry) else mc.next_session(entry)
    while n < HOLD_SESSIONS and (d < local.date() or (d == local.date() and local >= mc.session_open(d))):
        n += 1
        d = mc.next_session(d)
    return n


def still_holding(exit_by: date, now: datetime) -> bool:
    """A signal is held until the close of its sell day; after that it is finished (Sightings drops it)."""
    local = now.astimezone(mc.NY)
    return exit_by > local.date() or (exit_by == local.date() and local < mc.session_close(exit_by))


def unfinished_day(now: datetime) -> date | None:
    """Today while its session is still trading: the daily bar for it is an unfinished candle, not a close."""
    local = now.astimezone(mc.NY)
    d = local.date()
    return d if mc.is_session(d) and local < mc.session_close(d) else None


def track_stock(bars: list[Bar], spy_bars: list[Bar], session_date: date, direction: int,
                unfinished: date | None = None) -> dict:
    """unfinished = today while the market is open: its bar is a live candle, so it can't finish a hold or count as
    a close (the live price is shown separately)."""
    after = [b for b in bars if b.date > session_date][:HOLD_SESSIONS]
    if not after or not after[0].open:
        return {"status": "waiting", "entry_date": None, "entry": None, "exit_date": None, "exit": None, "last": None,
                "days_held": 0, "ret": None, "move": None, "vs_spy": None, "spy_ret": None, "peak": None, "peak_date": None,
                "drawdown": None, "drawdown_date": None, "priced_through": None, "path": []}
    entry, last = after[0].open, after[-1]
    live = last.date == unfinished
    closed = len(after) >= HOLD_SESSIONS and not live
    m = stock_move(entry, last.close, direction)
    ret = m["net"]
    hi = max(after, key=lambda b: b.high if direction > 0 else -b.low)
    lo = min(after, key=lambda b: b.low if direction > 0 else -b.high)
    move = (lambda p: (p / entry - 1) * direction)
    spy = [b for b in spy_bars if b.date > session_date][:len(after)]
    spy_ret = (spy[-1].close / spy[0].open - 1) if len(spy) == len(after) and spy[0].open else None
    return {"status": "closed" if closed else "open", "entry_date": after[0].date.isoformat(), "entry": entry,
            "exit_date": last.date.isoformat() if closed else None, "exit": last.close if closed else None,
            "last": last.close, "days_held": len(after), "ret": ret, "move": m["move"],
            "spy_ret": spy_ret, "vs_spy": ret - spy_ret * direction if spy_ret is not None else None,
            "peak": move(hi.high if direction > 0 else hi.low), "peak_date": hi.date.isoformat(),
            "drawdown": move(lo.low if direction > 0 else lo.high), "drawdown_date": lo.date.isoformat(),
            "priced_through": (after[-2].date.isoformat() if len(after) > 1 else None) if live else last.date.isoformat(),
            "path": [[b.date.isoformat(), move(b.close) - COST] for b in after]}   # daily close vs entry, after costs (last = ret)


def track_option(store, contract: str | None, entry: date, exit_: date, closed: bool) -> dict | None:
    """The whale's contract over our hold. Daily mark = what selling at that close would get (closing bid, or the last
    trade less half the entry gap). Closed signals use real_option_return exactly; None = not measured."""
    h = history(store, contract) if contract else None
    a = (h or {}).get(entry.isoformat())
    if not a or _num(a.get("open_price")) is None:
        return None
    bid0, ask0 = _num(a.get("nbbo_bid")), _num(a.get("nbbo_ask"))
    gap0 = ask0 - bid0 if bid0 and ask0 and ask0 >= bid0 else 0.0
    spread_pct = (ask0 - bid0) / ((ask0 + bid0) / 2) if bid0 and ask0 else None
    buy = _num(a["open_price"]) + gap0 / 2
    marks = []                                   # (date, sell price at that close)
    for d in sorted(k for k in h if entry.isoformat() <= k <= exit_.isoformat()):
        r = h[d]
        sell = _num(r.get("nbbo_bid"))
        if sell is None and (last := _num(r.get("last_price"))) is not None:
            sell = last * (1 - (spread_pct or 0) / 2)
        if sell is not None:
            marks.append((d, sell))
    if closed:
        ref = real_option_return(store, contract, entry, exit_)
        if ref is None:
            return None
        ret, sell, through = ref["ret"], ref["sell"], exit_.isoformat()
    else:
        if not marks:
            return None
        through, sell = marks[-1]
        ret = sell / buy - 1
    up = max((m for m in marks if m[1] > buy), key=lambda m: m[1], default=None)     # None: never closed above cost
    down = min((m for m in marks if m[1] < buy), key=lambda m: m[1], default=None)   # None: never closed below cost
    return {"contract": contract, "buy": buy, "spread_pct": spread_pct, "sell": sell, "sell_date": through, "ret": ret,
            "peak": up[1] / buy - 1 if up else None, "peak_date": up[0] if up else None,
            "drawdown": down[1] / buy - 1 if down else None, "drawdown_date": down[0] if down else None,
            "priced_through": through, "path": [[d, p / buy - 1] for d, p in marks]}


BENCHMARKS = {"SPY", "VOO", "IVV", "SPLG"}     # S&P 500 trackers: "vs the S&P" is always −costs for these


def _row(store, spy: list[Bar], sid: str, source: str, d: date, ticker: str, direction: int, tier: str, label: str,
         premium: float, otm_pct: float, sector: str | None, contract: str | None, spot: float | None) -> dict:
    stock = track_stock(store.get_ohlc(ticker, d, d + timedelta(days=45)), spy, d, direction,
                        unfinished_day(datetime.now(UTC)))
    option = None
    if stock["entry_date"]:
        option = track_option(store, contract, date.fromisoformat(stock["entry_date"]), exit_session(d),
                              stock["status"] == "closed")
    return {"id": sid, "source": source, "session_date": d.isoformat(), "ticker": ticker, "direction": direction,
            "tier": tier, "label": label, "premium": premium, "otm_pct": otm_pct, "sector": sector,
            "contract": contract, "spot_at_alert": spot, "entry_on": mc.next_session(d).isoformat(),
            "exit_by": exit_session(d).isoformat(),
            "period": LIVE_PERIOD if d >= FORWARD_START else period_label(d),
            "gap_at_entry": (stock["entry"] / spot - 1) * direction if stock["entry"] and spot else None,
            "stock": stock, "option": option}


def frozen_day(live_dir: Path, day: str, compute) -> list[dict]:
    """A decided live day's signals, written once (data/desk/live/<day>.json, gitignored) so the forward record never
    shifts when later cache refreshes (earnings dates, sectors) would re-decide a past day differently."""
    p = live_dir / f"{day}.json"
    if p.exists():
        return json.loads(p.read_text())
    sigs = compute()
    live_dir.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(sigs, default=str))
    return sigs


def saved_day(live_dir: Path, day: str, compute, final: bool) -> list[dict]:
    """A decided live day. Saved (frozen_day) only when final: built after the live feed caught up on that day's alerts.
    Until then it's shown, not saved. Bug 10-16: a restart after downtime froze Oct 16 a minute before the catch-up
    reached CIEN."""
    p = live_dir / f"{day}.json"
    if final or p.exists():
        return frozen_day(live_dir, day, compute)
    return compute()


def build_rows(store, hist: list[HistRow], live: list[dict]) -> list[dict]:
    """Every signal: history rows (tier set) + live signal dicts from the desk service (deduped by alert id), newest
    first. Cache only — prices come from the daily bars and option histories the close job keeps current."""
    sigs = [h for h in hist if h.tier]
    if not sigs and not live:
        return []
    first = min([h.session_date for h in sigs] + [date.fromisoformat(s["session_date"]) for s in live])
    spy_all = store.get_ohlc("SPY", first, date.today() + timedelta(days=1))
    def spy(d: date) -> list[Bar]:
        return [b for b in spy_all if d < b.date <= d + timedelta(days=45)]
    out, seen = [], set()
    for h in sigs:
        seen.add(h.alert_id)
        out.append(_row(store, spy(h.session_date), h.alert_id, "history", h.session_date, h.ticker, h.direction,
                        h.tier, h.reason, h.premium, h.otm_pct, h.sector, h.contract, h.price or None))
    for s in live:
        if s["id"] in seen:
            continue
        seen.add(s["id"])
        d = date.fromisoformat(s["session_date"])
        out.append(_row(store, spy(d), s["id"], "live", d, s["ticker"], s["direction"], s["tier"], s["label"],
                        s["premium"], s["otm_pct"], s.get("sector"), s.get("contract"), s.get("spot_at_alert")))
    return sorted(out, key=lambda r: (r["session_date"], r["premium"]), reverse=True)


MAX_TRIES = 4             # per item per close day: a contract with no quote that day must not cost a call every pass


def needs_close_prices(row: dict, close_day: date) -> bool:
    """Still in its hold, or exited in the last two sessions with the whale option's exit-day price not in yet
    (UW can post a contract's day row after the stock bar — without this the option would stay 'not measured')."""
    if row["stock"]["status"] != "closed":
        return True
    if not row.get("contract") or row["exit_by"] < mc.previous_session(close_day).isoformat():
        return False
    o = row.get("option")
    return o is None or o["priced_through"] < row["exit_by"]


def close_items(rows: list[dict], close_day: date) -> list[tuple[str, str | None]]:
    """(ticker, contract) the close job refreshes: signals needing prices, then their sector ETFs (for 'why it lost')."""
    from .postmortem import SECTOR_ETF
    need = [r for r in rows if needs_close_prices(r, close_day)]
    etfs = dict.fromkeys(SECTOR_ETF[r["sector"]] for r in need if r.get("sector") in SECTOR_ETF)
    return [(r["ticker"], r["contract"]) for r in need] + [(e, None) for e in etfs]


def _try(store, kind: str, key: str, day: date, fetch, have) -> bool:
    """One fetch per item per close day; done once `have()` is true, retried on later passes up to MAX_TRIES."""
    done, tries = f"tracker:{kind}:{key}", f"tracker:{kind}-try:{key}"
    if store.get_checkpoint(done) == day.isoformat():
        return True
    d, n = (store.get_checkpoint(tries) or ":0").split(":")
    n = int(n) if d == day.isoformat() else 0
    if n >= MAX_TRIES:
        return False
    store.set_checkpoint(tries, f"{day.isoformat()}:{n + 1}")
    fetch()
    if have():
        store.set_checkpoint(done, day.isoformat())
        return True
    return False


def close_update(client, store, open_items: list[tuple[str, str | None]], day: date) -> dict:
    """After the close: refresh daily bars (ticker + SPY) and the whale contract's daily history for signals that still
    need prices (needs_close_prices). ~1 call per ticker + 1 per contract; late-posting data retried (MAX_TRIES)."""
    missing_bars = [t for t in dict.fromkeys(["SPY", *(t for t, _ in open_items)])
                    if not _try(store, "bars", t, day, lambda t=t: ingest_bars(client, store, t, 0),
                                lambda t=t: bool(store.get_ohlc(t, day, day)))]
    missing_opt = [ch for ch in dict.fromkeys(c for _, c in open_items if c)
                   if not _try(store, "opt", ch, day, lambda ch=ch: ingest_contract_oi(client, store, ch, 0),
                               lambda ch=ch: day.isoformat() in (history(store, ch) or {}))]
    return {"day": day.isoformat(), "bars_missing": missing_bars, "options_missing": missing_opt}


SETTLE_HOUR = 8           # ET, the morning after a close: UW's daily bar carries the official close by then


def settle_items(rows: list[dict], day: date) -> list[str]:
    """Tickers whose record uses `day`'s close: every hold priced through it (finished there or still open), SPY and
    their sector ETFs. The close job's 16:15 bar can be the last trade before the closing auction (CRDO 10-13: 198.45,
    official 198.31), so these get one more fetch the next morning."""
    from .postmortem import SECTOR_ETF
    used = [r for r in rows if (r.get("stock") or {}).get("priced_through") == day.isoformat()]
    etfs = [SECTOR_ETF[r["sector"]] for r in used if r.get("sector") in SECTOR_ETF]
    return list(dict.fromkeys(["SPY", *(r["ticker"] for r in used), *etfs]))


def settle_update(client, store, items, close_day: date, now: datetime) -> list[str]:
    """From 08:00 ET the next day: refetch the bars of `items(day)` for close_day and the session before it (in case the
    desk was off that morning). One fetch per ticker covers every due day (3y bars); returns the tickers fetched."""
    local = now.astimezone(mc.NY)
    due = [d for d in (mc.previous_session(close_day), close_day)
           if local >= datetime.combine(d + timedelta(days=1), datetime.min.time(), mc.NY).replace(hour=SETTLE_HOUR)]
    if not due:
        return []
    got: list[str] = []
    for d in due:
        for t in items(d):
            key = f"tracker:settle:{t}"
            if t in got or (store.get_checkpoint(key) or "") >= d.isoformat():
                continue
            ingest_bars(client, store, t, 0)
            store.set_checkpoint(key, due[-1].isoformat())
            got.append(t)
    return got


def rounded(x):
    """Floats to 6 significant-enough decimals — halves the page payload, no visible change."""
    if isinstance(x, float):
        return round(x, 6)
    if isinstance(x, dict):
        return {k: rounded(v) for k, v in x.items()}
    if isinstance(x, list):
        return [rounded(v) for v in x]
    return x


def csv_text(rows: list[dict]) -> str:
    import csv
    import io
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(CSV_COLS)
    for r in rows:
        s, o = r["stock"], r["option"] or {}
        w.writerow([r["session_date"], r["ticker"], r["period"], r["tier"], r["premium"], r["otm_pct"], s["status"],
                    s["entry_date"], s["entry"], s["exit_date"], s["exit"], s["last"], s["days_held"], s["ret"],
                    s["vs_spy"], s["peak"], s["peak_date"], s["drawdown"], s["drawdown_date"], o.get("contract"),
                    o.get("buy"), o.get("sell"), o.get("ret"), o.get("peak"), o.get("drawdown"), s["priced_through"]])
    return buf.getvalue()
