"""EXPLORATORY: compounded return of trading Signal Desk signals with stock (owner question 2026-09-30).
Portfolio: capital split into HOLD_SESSIONS (5) sleeves; the sleeve of flow day i is re-used on day i+5 (enter next
open, exit close of the 5th session). Each day's signals share their sleeve equally; no signal → sleeve stays in cash
(0%). Returns = r5 (raw, in the signal direction, net 0.10% round trip), booked on each trade's exit day. Benchmark =
SPY bought at the first entry open and sold at the last exit close.
Cache-only. → journal/research/compound-stock-signals.json
Usage: uv run python scripts/research/compound_stock_signals.py"""
from __future__ import annotations

import json
import statistics as st
from collections import defaultdict
from datetime import date

from whaleproof import market_calendar as mc
from whaleproof.config import REPO_ROOT, load_settings
from whaleproof.core.data_layer.store import Store
from whaleproof.desk.config import HOLD_SESSIONS, HOLDOUT, POST, PRE, TRAIN
from whaleproof.desk.history import classify_rows, earnings_map, load_raw

LAST = date(2026, 9, 22)          # last flow day with a complete 5-session outcome in the cache
WINDOWS = {"pre": PRE, "train": TRAIN, "holdout": HOLDOUT, "post": (POST[0], LAST), "all": (PRE[0], LAST)}


def with_exits(sessions: list[date]) -> list[date]:
    """The window's sessions plus the HOLD_SESSIONS sessions after it, so the last signals' exits are on the timeline."""
    ext = list(sessions)
    for _ in range(HOLD_SESSIONS):
        ext.append(mc.next_session(ext[-1]))
    return ext


def simulate(day_ret: dict[date, float], sessions: list[date], keep_curve: bool = False) -> dict:
    """Each trade's result is booked on its EXIT day (close of the 5th session after the signal day), when the money
    actually arrives. Sleeve of signal day i = i % 5; it is free again for signal day i + 5 (entry the next open)."""
    sleeves = [1.0 / HOLD_SESSIONS] * HOLD_SESSIONS
    ext = with_exits(sessions)
    curve, peak, mdd, active = [], 0.0, 0.0, 0
    for j in range(len(ext)):
        i = j - HOLD_SESSIONS                      # the signal day whose trade exits at ext[j]
        if i >= 0 and sessions[i] in day_ret:
            sleeves[i % HOLD_SESSIONS] *= 1 + day_ret[sessions[i]]
            active += 1
        eq = sum(sleeves)
        peak = max(peak, eq)
        mdd = min(mdd, eq / peak - 1)
        curve.append(eq)
    years = len(sessions) / 252
    total = curve[-1] - 1 if curve else 0.0
    out = {"sessions": len(sessions), "days_invested": active, "total_return": total,
           "cagr": (1 + total) ** (1 / years) - 1 if years else None, "max_drawdown": mdd}
    return out | {"_curve": curve, "_dates": ext} if keep_curve else out


def weekly_curve(store: Store, dates: list[date], eq: list[float]) -> list[dict]:
    """One point per week (every 5th session + the last), dated by the day money arrives: signals equity vs SPY
    buy-and-hold over the same span (bought at the first entry open), both starting at 1.0."""
    closes = {b.date: b.close for b in store.get_ohlc("SPY", dates[0], dates[-1])}
    base = store.get_ohlc("SPY", dates[1], dates[1])[0].open
    idx = [i for i in range(1, len(dates)) if i % HOLD_SESSIONS == 0 or i == len(dates) - 1]
    return [{"d": dates[i].isoformat(), "eq": round(eq[i], 4), "spy": round(closes[dates[i]] / base, 4)}
            for i in idx if dates[i] in closes]


def spy_hold(store: Store, a: date, b: date) -> dict:
    """SPY bought at the first trade's entry (open after the first session) and sold at the last trade's exit."""
    ext = with_exits(mc.sessions(a, b))
    bars = store.get_ohlc("SPY", ext[1], ext[-1])
    t = bars[-1].close / bars[0].open - 1
    years = len(mc.sessions(a, b)) / 252
    return {"total_return": t, "cagr": (1 + t) ** (1 / years) - 1}


def main() -> None:
    store = Store(load_settings().db_path)
    rows = classify_rows(load_raw(REPO_ROOT / "data" / "desk", include_holdout=True), earnings_map(store))
    out = {"label": "exploratory (portfolio simulation of the frozen filter; tiers as live)", "method": __doc__,
           "windows": {w: [a.isoformat(), b.isoformat()] for w, (a, b) in WINDOWS.items()}}
    for tier in ("all", "whale", "far_otm"):
        by = defaultdict(list)
        for r in rows:
            if r.tier and r.r5 is not None and (tier == "all" or r.tier == tier):
                by[r.session_date].append(r.r5)
        day_ret = {d: st.fmean(v) for d, v in by.items()}
        res = {}
        for w, (a, b) in WINDOWS.items():
            sessions = mc.sessions(a, b)
            res[w] = simulate({d: v for d, v in day_ret.items() if a <= d <= b}, sessions, keep_curve=w == "all")
            if tier == "all" and w == "all":
                out["curve"] = weekly_curve(store, res[w].pop("_dates"), res[w].pop("_curve"))
            res[w].pop("_curve", None)
            res[w].pop("_dates", None)
            res[w]["trades"] = sum(len(v) for d, v in by.items() if a <= d <= b)
        out[tier] = res
    out["spy"] = {w: spy_hold(store, a, b) for w, (a, b) in WINDOWS.items()}
    path = REPO_ROOT / "journal" / "research" / "compound-stock-signals.json"
    path.write_text(json.dumps(out, indent=1, default=str))
    for w in WINDOWS:
        line = " | ".join(f"{t}: {out[t][w]['total_return'] * 100:+.1f}% (cagr {out[t][w]['cagr'] * 100:+.1f}%, "
                          f"mdd {out[t][w]['max_drawdown'] * 100:.1f}%, n {out[t][w]['trades']})"
                          for t in ("all", "whale", "far_otm"))
        print(f"{w:8} {line} | SPY {out['spy'][w]['total_return'] * 100:+.1f}% (cagr {out['spy'][w]['cagr'] * 100:+.1f}%)")


if __name__ == "__main__":
    main()
