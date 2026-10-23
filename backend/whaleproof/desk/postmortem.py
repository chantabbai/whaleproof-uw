"""Why a signal lost (W1-3): short descriptive notes for a finished signal that lagged the S&P 500, from cached data.

Checks (each skipped and listed in `not_checked` when its data is missing):
  gap_chased / gap_against  entry open vs the signal-day close, in the signal's direction (|move| >= ENTRY_GAP)
  overnight_gap             worst close→open gap against the signal inside the hold (<= -OVERNIGHT_GAP and at least
                            half of the stock's whole move from entry)
  tide                      UW market tide (net call − put premium) on the signal day vs summed over the hold
  sector                    the sector ETF's move over the same entry open → exit close vs SPY (<= -SECTOR_LAG)
  stock                     none of the above: the stock itself lagged
GEX walls are deliberately not a reason: they showed no support/resistance effect (docs/WALLS-SR.md).
Descriptive only — never feeds the frozen filter."""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta

from whaleproof.core.data_layer.models import Bar
from whaleproof.market_calendar import NY

ENTRY_GAP, OVERNIGHT_GAP, SECTOR_LAG, MIN_TIDE_DAYS = 0.01, 0.02, 0.01, 3
SECTOR_ETF = {"Technology": "XLK", "Consumer Cyclical": "XLY", "Financial Services": "XLF", "Industrials": "XLI",
              "Healthcare": "XLV", "Energy": "XLE", "Basic Materials": "XLB", "Communication Services": "XLC",
              "Consumer Defensive": "XLP", "Utilities": "XLU", "Real Estate": "XLRE"}


def _pct(v: float) -> str:
    return f"{v:+.1%}".replace("-", "−")                 # true minus, as everywhere in the app


def _usd(v: float) -> str:
    a = abs(v)
    s = f"${a / 1e9:.1f}B" if a >= 1e9 else f"${a / 1e6:.0f}M"
    return ("+" if v >= 0 else "−") + s


def _pts(v: float) -> str:
    """A gap between two returns (vs the S&P 500, vs a sector) is in percentage points, not percent."""
    return f"{abs(v) * 100:.1f} points"


def _md(d: date, today: date | None = None) -> str:
    """"Jan 8"; a date in another year also gets the year ("Jan 8, 2024"), so an old trade's note can't pass for this year."""
    today = today or datetime.now(NY).date()
    return f"{d:%b} {d.day}" if d.year == today.year else f"{d:%b} {d.day}, {d.year}"


def _span(bs: list[Bar], start: date, end: date) -> list[Bar]:
    return [b for b in bs if start <= b.date <= end]


def _move(bs: list[Bar], start: date, end: date) -> float | None:
    """Open of `start` → close of `end`, None unless both days are present."""
    s = _span(bs, start, end)
    if not s or s[0].date != start or s[-1].date != end or not s[0].open:
        return None
    return s[-1].close / s[0].open - 1


def why_lost(row: dict, bars: list[Bar], spy_bars: list[Bar], sector_bars: list[Bar],
             tide: dict[date, float], any_result: bool = False) -> dict | None:
    """Notes for a finished signal that lagged the S&P 500 (`any_result=True` also runs it on winners, for base rates)."""
    st = row.get("stock") or {}
    if st.get("status") != "closed" or st.get("vs_spy") is None or (st["vs_spy"] >= 0 and not any_result):
        return None
    d0, dr = date.fromisoformat(row["session_date"]), row["direction"]
    entry, exit_ = date.fromisoformat(st["entry_date"]), date.fromisoformat(st["exit_date"])
    notes: list[dict] = []
    not_checked: list[str] = []

    hold = _span(bars, entry, exit_)
    sig = next((b for b in bars if b.date == d0), None)
    whole = _move(bars, entry, exit_)
    if sig and hold and hold[0].date == entry and sig.close:
        gap = (hold[0].open / sig.close - 1) * dr
        where = lambda g: f"{abs(g):.1%} {'above' if g * dr > 0 else 'below'} the signal-day close"  # noqa: E731
        if gap >= ENTRY_GAP:
            text = f"Paid up: opened {where(gap)}, so part of the move came before the entry"
            text += ("." if whole is None else f". It still made {_pct(whole * dr)} from that open." if whole * dr >= 0
                     else f", then went {_pct(whole * dr)} from that open.")
            notes.append({"kind": "gap_chased", "text": text})
        elif gap <= -ENTRY_GAP:
            notes.append({"kind": "gap_against", "text": f"Opened {where(gap)}: a better entry price, but the stock was moving against the signal at the start."})
    else:
        not_checked.append("entry gap")
    if len(hold) >= 2 and whole is not None:
        gaps = [((b.open / a.close - 1) * dr, b.date) for a, b in zip(hold, hold[1:]) if a.close and b.open]
        worst = min(gaps, default=None)
        tot = whole * dr
        if worst and worst[0] <= -OVERNIGHT_GAP and tot < 0 and worst[0] / tot >= 0.5:
            notes.append({"kind": "overnight_gap", "text": f"Gapped {_pct(worst[0])} against the signal overnight into "
                          f"{_md(worst[1])}, most of the {_pct(tot)} move from entry."})

    held = [tide[b.date] for b in hold if b.date in tide]
    if d0 in tide and len(held) >= MIN_TIDE_DAYS:
        s0, s1 = tide[d0], sum(held)
        if s1 * dr < 0:
            lean = lambda v: "call-heavy" if v >= 0 else "put-heavy"  # noqa: E731
            text = (f"Market options flow turned against the signal: {lean(s0)} ({_usd(s0)}) on the signal day, "
                    f"{lean(s1)} ({_usd(s1)}) over the hold." if s0 * dr > 0 else
                    f"Market options flow was against the signal throughout: {lean(s0)} ({_usd(s0)}) on the signal "
                    f"day and {lean(s1)} ({_usd(s1)}) over the hold.")
            notes.append({"kind": "tide", "text": text})
    else:
        not_checked.append("market tide")

    etf = SECTOR_ETF.get(row.get("sector") or "")
    em, sm = (_move(sector_bars, entry, exit_), _move(spy_bars, entry, exit_)) if etf else (None, None)
    if etf and em is not None and sm is not None:
        lag = (em - sm) * dr
        if lag <= -SECTOR_LAG:
            rel = (whole - em) * dr if whole is not None else None
            vs_sector = "" if rel is None else f"; the stock did {_pts(rel)} {'better' if rel >= 0 else 'worse'} than its sector"
            notes.append({"kind": "sector", "text": f"Sector headwind: {row['sector']} ({etf}) lagged the S&P 500 by "
                                                    f"{_pts(lag)} over the hold{vs_sector}."})
    else:
        not_checked.append("sector")

    if not notes:
        notes.append({"kind": "stock", "text": "No outside cause in the saved data: the stock itself lagged the "
                                               f"S&P 500 by {_pts(st['vs_spy'])}."})
    return {"notes": notes, "not_checked": not_checked,
            "label": "Descriptive notes from cached prices and UW market tide; not a tested rule."}


GAVE_BACK, RECOVERED = 0.03, -0.03     # best point ≥ +3% and finished ≥ 3 pts lower / worst ≤ −3% and finished up


def review(row: dict, bars: list[Bar], spy_bars: list[Bar], sector_bars: list[Bar],
           tide: dict[date, float]) -> dict | None:
    """What went well and what could have gone better, for any finished signal (owner 10-07). 'Better' reuses the
    why-it-lagged checks; a winner drops the 'stock itself lagged' fallback. Descriptive only, never a filter."""
    st = row.get("stock") or {}
    if st.get("status") != "closed" or st.get("vs_spy") is None:
        return None
    lagged = st["vs_spy"] < 0
    w = why_lost(row, bars, spy_bars, sector_bars, tide, any_result=True) or {"notes": [], "not_checked": []}
    better = [n for n in w["notes"] if lagged or n["kind"] != "stock"]
    good: list[dict] = []
    d0, dr = date.fromisoformat(row["session_date"]), row["direction"]
    entry, exit_ = date.fromisoformat(st["entry_date"]), date.fromisoformat(st["exit_date"])
    if not lagged:
        good.append({"kind": "beat_spx", "text": f"Beat the S&P 500 by {_pts(st['vs_spy'])} over the hold."})
    held = [tide[b.date] for b in _span(bars, entry, exit_) if b.date in tide]
    if d0 in tide and len(held) >= MIN_TIDE_DAYS and sum(held) * dr > 0:
        s0, s1 = tide[d0], sum(held)
        lean = lambda v: "call-heavy" if v >= 0 else "put-heavy"  # noqa: E731
        good.append({"kind": "tide_with", "text": (
            f"Market options flow turned the signal's way: {lean(s0)} ({_usd(s0)}) on the signal day, {lean(s1)} "
            f"({_usd(s1)}) over the hold." if s0 * dr < 0 else
            f"Market options flow backed the signal: {lean(s0)} ({_usd(s0)}) on the signal day and {lean(s1)} "
            f"({_usd(s1)}) over the hold.")})
    etf = SECTOR_ETF.get(row.get("sector") or "")
    em, sm = (_move(sector_bars, entry, exit_), _move(spy_bars, entry, exit_)) if etf else (None, None)
    if em is not None and sm is not None and (em - sm) * dr >= SECTOR_LAG:
        good.append({"kind": "sector_with", "text": f"Sector tailwind: {row['sector']} ({etf}) beat the S&P 500 by "
                                                    f"{_pts((em - sm) * dr)} over the hold."})
    move, peak, dd = st.get("move"), st.get("peak"), st.get("drawdown")
    word = lambda v: f"{'up' if v >= 0 else 'down'} {abs(v):.1%}"  # noqa: E731
    if move is not None and dd is not None and dd <= RECOVERED and move > 0:
        good.append({"kind": "recovered", "text": f"Was down {abs(dd):.1%} at its worst "
                                                  f"({_md(date.fromisoformat(st['drawdown_date']))}) and still finished {word(move)}."})
    if move is not None and peak is not None and peak >= GAVE_BACK and peak - move >= GAVE_BACK:
        better.append({"kind": "gave_back", "text": f"Was up {peak:.1%} at its best ({_md(date.fromisoformat(st['peak_date']))})"
                                                    f" but finished {word(move)}: most of the gain went back."})
    o = (row.get("option") or {}).get("ret")
    if o is not None and st.get("ret") is not None:
        if o > st["ret"] and o > 0:
            good.append({"kind": "option_beat", "text": f"The whale's own option made {_pct(o)}, against "
                                                        f"{_pct(st['ret'])} on the stock."})
        elif o < st["ret"]:
            better.append({"kind": "option_lagged", "text": f"The whale's own option made {_pct(o)}, against "
                                                            f"{_pct(st['ret'])} on the stock: the stock was the better way to hold it."})
    return {"went_well": good, "better": better, "lagged": lagged, "not_checked": w["not_checked"],
            "label": "Descriptive notes from cached prices and UW market tide; not a tested rule."}


REVIEW_KINDS = ("beat_spx", "tide_with", "sector_with", "recovered", "option_beat",
                "gap_chased", "gap_against", "overnight_gap", "tide", "sector", "stock", "gave_back", "option_lagged")


def market_tide(store, start: date, end: date) -> dict[date, float]:
    """Daily UW market tide (net call − put premium at the day's last print): backfilled daily_metric, else the
    live refresher's raw 5-minute cache when that day's series reached the close."""
    out = {date.fromisoformat(d): float(json.loads(p)) for d, p in store.conn.execute(
        "SELECT date, payload FROM daily_metric WHERE kind='tide' AND ticker='MARKET' AND date BETWEEN ? AND ?",
        (start.isoformat(), end.isoformat()))}
    d = start
    while d <= end:
        if d not in out:
            key = "/api/market/market-tide?" + json.dumps({"date": d.isoformat(), "interval_5m": True})
            hit = store.conn.execute("SELECT payload FROM raw_cache WHERE key=?", (key,)).fetchone()
            if (v := _close_tide(hit[0] if hit else None)) is not None:
                out[d] = v
        d += timedelta(days=1)
    return out


def _close_tide(payload: str | None) -> float | None:
    try:
        last = (json.loads(payload).get("data") or [])[-1]
        if str(last.get("timestamp", ""))[11:16] < "15:55":
            return None
        return float(last["net_call_premium"]) - float(last["net_put_premium"])
    except (ValueError, KeyError, IndexError, TypeError, AttributeError):
        return None


KINDS = ("gap_chased", "gap_against", "overnight_gap", "tide", "sector", "stock")


def explain(store, row: dict, any_result: bool = False) -> dict | None:
    """Notes for one tracker row, cache only."""
    st = row.get("stock") or {}
    if st.get("status") != "closed" or st.get("vs_spy") is None or (st["vs_spy"] >= 0 and not any_result):
        return None
    d0, end = date.fromisoformat(row["session_date"]), date.fromisoformat(st["exit_date"])
    etf = SECTOR_ETF.get(row.get("sector") or "")
    return why_lost(row, store.get_ohlc(row["ticker"], d0, end), store.get_ohlc("SPY", d0, end),
                    store.get_ohlc(etf, d0, end) if etf else [], market_tide(store, d0, end), any_result)


def note_rates(store, rows: list[dict]) -> dict:
    """How often each note shows up on finished losers vs winners: a note common to both explains little."""
    seen: dict = {k: {"losers": 0, "winners": 0} for k in KINDS}
    tot = {"losers": 0, "winners": 0}
    for r in rows:
        w = explain(store, r, any_result=True)
        if not w:
            continue
        side = "losers" if r["stock"]["vs_spy"] < 0 else "winners"
        tot[side] += 1
        for k in {n["kind"] for n in w["notes"]}:
            seen[k][side] += 1
    return {"signals": tot, "share": {k: {s: round(v[s] / tot[s], 3) if tot[s] else None for s in tot}
                                      for k, v in seen.items()}}


def explain_review(store, row: dict) -> dict | None:
    """review() for one tracker row, cache only."""
    st = row.get("stock") or {}
    if st.get("status") != "closed" or st.get("vs_spy") is None:
        return None
    d0, end = date.fromisoformat(row["session_date"]), date.fromisoformat(st["exit_date"])
    etf = SECTOR_ETF.get(row.get("sector") or "")
    return review(row, store.get_ohlc(row["ticker"], d0, end), store.get_ohlc("SPY", d0, end),
                  store.get_ohlc(etf, d0, end) if etf else [], market_tide(store, d0, end))


def review_rates(store, rows: list[dict]) -> dict:
    """How often each review note shows up on finished winners vs losers: a note common to both explains little."""
    seen: dict = {k: {"losers": 0, "winners": 0} for k in REVIEW_KINDS}
    tot = {"losers": 0, "winners": 0}
    for r in rows:
        w = explain_review(store, r)
        if not w:
            continue
        side = "losers" if w["lagged"] else "winners"
        tot[side] += 1
        for k in {n["kind"] for n in [*w["went_well"], *w["better"]]}:
            seen[k][side] += 1
    return {"signals": tot, "share": {k: {s: round(v[s] / tot[s], 3) if tot[s] else None for s in tot}
                                      for k, v in seen.items()}}
