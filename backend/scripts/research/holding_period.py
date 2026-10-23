"""EXPLORATORY: why exit the stock after 5 sessions — what about 10, 20, 30? (owner 2026-09-30, run 2026-10-01)
Same signals as the desk evidence (frozen DEFAULT_FILTER, history rows under data/desk/). For each signal and each hold H:
entry at the next session's open, exit at the close of the H-th session, return in the signal direction minus SPY over
the same days, minus 0.10% costs — exactly the x5 definition (H=5 must reproduce the stored x5). Baseline: the same for
every directional alert. Trades without H sessions of future bars are excluded and counted; the main table uses only
trades that have all four horizons, so every horizon is measured on the same trades. 95% range: moving-block bootstrap of
daily means with block = H (holds overlap for H sessions). Earnings: the filter only blocks reports inside the 5-session
hold, so longer holds can include one — share reported (report-time aware, same rule as the filter).
The holdout was already opened once; this is descriptive. A 'preferred' horizon is picked on the practice year only.
Cache-only. → journal/research/holding-period.json   Usage: uv run python scripts/research/holding_period.py"""
from __future__ import annotations

import json
import statistics as st
from bisect import bisect_right
from collections import defaultdict
from datetime import date

from whaleproof.core.backtest.runner import COST
from whaleproof.core.data_layer.models import Bar

HORIZONS = (5, 10, 20, 30)


def _after(bars: list[Bar], d: date, dates: list[date] | None = None) -> list[Bar]:
    return bars[bisect_right(dates if dates is not None else [b.date for b in bars], d):]


def excess_return(bars: list[Bar], spy: list[Bar], d: date, direction: int, h: int,
                  dates: list[date] | None = None, spy_dates: list[date] | None = None) -> tuple[float | None, date | None]:
    """(return in signal direction - SPY same days - COST, exit date); (None, None) without h future sessions."""
    a, s = _after(bars, d, dates), _after(spy, d, spy_dates)
    if len(a) < h or len(s) < h or not a[0].open or not s[0].open:
        return None, None
    r = (a[h - 1].close / a[0].open - 1) * direction - COST
    return r - (s[h - 1].close / s[0].open - 1) * direction, a[h - 1].date


def earnings_between(d: date, end: date, earnings: list[tuple[date, str]]) -> bool:
    """Report after the flow-day close and before the exit close (same rule as desk.signals.earnings_in_hold)."""
    return any((e == d and w == "postmarket") or d < e < end or (e == end and w != "postmarket") for e, w in earnings)


def summarize(rows: list[tuple[date, float]], h: int) -> dict:
    from whaleproof.desk import evidence
    if not rows:
        return {"trades": 0}
    x = [v for _, v in rows]
    by = defaultdict(list)
    for d, v in rows:
        by[d].append(v)
    daily = [st.fmean(v) for _, v in sorted(by.items())]
    old, evidence.BLOCK = evidence.BLOCK, h          # holds overlap for h sessions → resample h-day blocks
    try:
        lo, hi = evidence.block_ci(daily)
    finally:
        evidence.BLOCK = old
    m = st.fmean(x)
    ok = lo == lo and hi == hi                       # NaN when fewer than 2 blocks of days
    lo, hi = (lo, hi) if ok else (None, None)
    return {"trades": len(x), "avg_per_trade": m, "avg_per_session_held": m / h, "win_rate": sum(v > 0 for v in x) / len(x),
            "median": st.median(x), "day_mean": st.fmean(daily), "range95_day_mean": [lo, hi],
            "range_includes_zero": (lo <= 0 <= hi) if ok else None}


def main() -> None:
    from whaleproof.config import REPO_ROOT, load_settings
    from whaleproof.core.data_layer.store import Store
    from whaleproof.desk.config import HOLDOUT, POST, PRE, TRAIN
    from whaleproof.desk.history import classify_rows, earnings_map, load_raw

    periods = {"pre": ("Second sealed test · Oct 2023 – Sep 2024", PRE), "train": ("Practice year · Oct 2024 – Sep 2025", TRAIN),
               "holdout": ("Sealed test · Oct 2025 – May 2026", HOLDOUT),
               "post": ("Recent months · Jun – Sep 2026", (POST[0], date(2026, 12, 31)))}
    store = Store(load_settings().db_path)
    earn = earnings_map(store)
    rows = classify_rows(load_raw(REPO_ROOT / "data" / "desk", include_holdout=True), earn)
    spy = store.get_ohlc("SPY", date(2023, 1, 1), date(2026, 12, 31))
    spy_dates = [b.date for b in spy]
    cache: dict[str, tuple[list[Bar], list[date]]] = {}
    acc: dict = defaultdict(lambda: defaultdict(list))       # acc[period][(group, H)] -> [(date, x)]
    meta: dict = defaultdict(lambda: defaultdict(int))
    x5_check: dict = defaultdict(list)
    earn_in: dict = defaultdict(lambda: defaultdict(int))
    for r in rows:
        p = next((k for k, (_, (a, b)) in periods.items() if a <= r.session_date <= b), None)
        if not p or r.x5 is None:
            continue
        if r.ticker not in cache:
            bars = store.get_ohlc(r.ticker, date(2023, 1, 1), date(2026, 12, 31))
            cache[r.ticker] = (bars, [b.date for b in bars])
        bars, dates = cache[r.ticker]
        res = {h: excess_return(bars, spy, r.session_date, r.direction, h, dates, spy_dates) for h in HORIZONS}
        groups = ["all"] + (["signals"] if r.tier else [])
        if r.tier:
            meta[p]["signals_with_x5"] += 1
            x5_check[p].append((r.x5, res[5][0]))
        if any(res[h][0] is None for h in HORIZONS):
            for g in groups:
                meta[p][f"{g}_excluded_short_future"] += 1
            continue
        for g in groups:
            for h in HORIZONS:
                acc[p][(g, h)].append((r.session_date, res[h][0]))
        if r.tier:
            for h in HORIZONS:
                earn_in[p][h] += earnings_between(r.session_date, res[h][1], earn.get(r.ticker, []))
    out = {"label": "exploratory (holdout already opened once; official 5-session hold unchanged)", "method": __doc__,
           "horizons": HORIZONS, "periods": {}}
    for p, (name, _) in periods.items():
        chk = x5_check[p]
        diffs = [abs(a - b) for a, b in chk if b is not None]
        po = {"name": name, "signals_in_evidence": meta[p]["signals_with_x5"],
              "x5_reproduced": {"compared": len(diffs), "max_abs_diff": max(diffs) if diffs else None,
                                "stored_x5_avg": st.fmean(a for a, _ in chk) if chk else None},
              "signals_excluded_short_future": meta[p]["signals_excluded_short_future"],
              "all_excluded_short_future": meta[p]["all_excluded_short_future"], "by_horizon": {}}
        n_sig = len(acc[p][("signals", 5)])
        for h in HORIZONS:
            s, a = summarize(acc[p][("signals", h)], h), summarize(acc[p][("all", h)], h)
            po["by_horizon"][h] = {"signals": s, "every_alert": a,
                                   "beat_every_alert": s.get("avg_per_trade", 0) > a.get("avg_per_trade", 0) if s["trades"] else None,
                                   "share_with_earnings_inside": earn_in[p][h] / n_sig if n_sig else None}
        out["periods"][p] = po
    tr = out["periods"]["train"]["by_horizon"]
    out["preferred_on_practice_year"] = {
        "by_day_mean_per_session": max(HORIZONS, key=lambda h: tr[h]["signals"]["day_mean"] / h),
        "by_avg_per_trade_per_session": max(HORIZONS, key=lambda h: tr[h]["signals"]["avg_per_session_held"]),
        "range_excludes_zero": [h for h in HORIZONS if tr[h]["signals"]["range_includes_zero"] is False]}
    (REPO_ROOT / "journal" / "research" / "holding-period.json").write_text(json.dumps(out, indent=1, default=str))
    for p, po in out["periods"].items():
        print(f"\n{po['name']}: x5 check {po['x5_reproduced']}; signals excluded (short future) "
              f"{po['signals_excluded_short_future']}")
        for h in HORIZONS:
            b = po["by_horizon"][h]
            s, a = b["signals"], b["every_alert"]
            if not s["trades"]:
                continue
            lo, hi = (v * 100 if v is not None else float("nan") for v in s["range95_day_mean"])
            print(f"  H{h:<3} trades {s['trades']:4}  avg {s['avg_per_trade'] * 100:+6.2f}%  /session {s['avg_per_session_held'] * 100:+.3f}%  "
                  f"win {s['win_rate'] * 100:4.1f}%  day-mean {s['day_mean'] * 100:+.2f}% [{lo:+.2f}, {hi:+.2f}]  "
                  f"every-alert {a['avg_per_trade'] * 100:+.2f}%  earnings-inside {b['share_with_earnings_inside'] * 100:.0f}%")
    print("\npreferred on practice year:", out["preferred_on_practice_year"])


if __name__ == "__main__":
    main()
