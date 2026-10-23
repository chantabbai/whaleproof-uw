"""EXPLORATORY: is the filtered signals' edge just market beta? (owner 2026-09-30, after the copy pass)
Beta per row = OLS slope of the stock's daily close-to-close returns on SPY's over the 120 sessions ending on the flow
day (point-in-time; >= 20 overlapping days, else skipped and reported: mostly new listings). Beta-adjusted 5-session return =
r5 - beta * SPY_r5 * direction, where r5 is the stock return in the signal direction net of 0.10% costs and SPY_r5 is
SPY over the same entry→exit (recovered from x5 = r5 - SPY_r5 * direction). Compared with plain x5 (beta = 1).
Per window: signals and all directional alerts; per-day 95% range by the same 5-day block bootstrap as the evidence.
Cache-only. → journal/research/beta-adjusted.json   Usage: uv run python scripts/research/beta_adjusted.py"""
from __future__ import annotations

import json
import statistics as st
from bisect import bisect_right
from collections import defaultdict
from datetime import date

from whaleproof.config import REPO_ROOT, load_settings
from whaleproof.core.data_layer.store import Store
from whaleproof.desk.config import HOLDOUT, PRE, TRAIN
from whaleproof.desk.evidence import block_ci
from whaleproof.desk.history import classify_rows, earnings_map, load_raw

LOOKBACK, MIN_OBS = 120, 20
WINDOWS = {"pre": PRE, "train": TRAIN, "holdout": HOLDOUT, "post": (date(2026, 6, 1), date(2026, 9, 22))}
START = date(2023, 3, 1)


def returns(store: Store, ticker: str) -> tuple[list[date], dict[date, float]]:
    bars = store.get_ohlc(ticker, START, date(2026, 12, 31))
    rets = {b.date: b.close / a.close - 1 for a, b in zip(bars, bars[1:]) if a.close and b.close}
    return sorted(rets), rets


def beta_at(dates: list[date], rets: dict, spy: dict, d: date) -> float | None:
    i = bisect_right(dates, d)
    xs, ys = [], []
    for k in dates[max(0, i - LOOKBACK):i]:
        if k in spy:
            xs.append(spy[k])
            ys.append(rets[k])
    if len(xs) < MIN_OBS:
        return None
    mx, my = st.fmean(xs), st.fmean(ys)
    vx = sum((x - mx) ** 2 for x in xs)
    return sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / vx if vx else None


def summarize(rows: list[tuple[date, float]]) -> dict:
    if not rows:
        return {"n": 0}
    x = [v for _, v in rows]
    by = defaultdict(list)
    for d, v in rows:
        by[d].append(v)
    daily = [st.fmean(v) for _, v in sorted(by.items())]
    lo, hi = block_ci(daily)
    return {"n": len(x), "mean": st.fmean(x), "median": st.median(x), "day_mean": st.fmean(daily), "ci_low": lo,
            "ci_high": hi}


def main() -> None:
    store = Store(load_settings().db_path)
    rows = classify_rows(load_raw(REPO_ROOT / "data" / "desk", include_holdout=True), earnings_map(store))
    _, spy = returns(store, "SPY")
    cache: dict[str, tuple] = {}
    acc: dict = defaultdict(lambda: defaultdict(list))
    for r in rows:
        w = next((k for k, (a, b) in WINDOWS.items() if a <= r.session_date <= b), None)
        if not w or r.x5 is None or r.r5 is None:
            continue
        if r.ticker not in cache:
            cache[r.ticker] = returns(store, r.ticker)
        b = beta_at(*cache[r.ticker], spy, r.session_date)
        if b is None:
            if r.tier:
                acc[w]["skipped:x5"].append((r.session_date, r.x5))
                acc[w]["skipped:tickers"].append((r.session_date, r.ticker))
            continue
        spy5 = (r.r5 - r.x5) * r.direction
        adj = r.r5 - b * spy5 * r.direction
        groups = ["all"] + (["signals", f"tier_{r.tier}"] if r.tier else [])
        for g in groups:
            acc[w][g + ":x5"].append((r.session_date, r.x5))
            acc[w][g + ":beta_adj"].append((r.session_date, adj))
            acc[w][g + ":beta"].append((r.session_date, b))
    out = {"label": "exploratory (post-holdout)", "method": __doc__}
    for w in WINDOWS:
        out[w] = {}
        for g in ("all", "signals", "tier_whale", "tier_far_otm"):
            if not acc[w][g + ":x5"]:
                continue
            out[w][g] = {"x5": summarize(acc[w][g + ":x5"]), "beta_adj": summarize(acc[w][g + ":beta_adj"]),
                         "avg_beta": st.fmean(v for _, v in acc[w][g + ":beta"])}
        sk = acc[w]["skipped:x5"]
        out[w]["signals_skipped_no_history"] = {"n": len(sk), "x5_mean": st.fmean(v for _, v in sk) if sk else None,
                                                "tickers": sorted({t for _, t in acc[w]["skipped:tickers"]})}
    (REPO_ROOT / "journal" / "research" / "beta-adjusted.json").write_text(json.dumps(out, indent=1, default=str))
    for w in WINDOWS:
        print(w, "skipped (no history):", out[w]["signals_skipped_no_history"])
        for g in ("all", "signals", "tier_far_otm", "tier_whale"):
            o = out[w].get(g)
            if not o:
                continue
            x, a = o["x5"], o["beta_adj"]
            print(f"{w:8} {g:13} n {x['n']:6}  beta {o['avg_beta']:.2f}  x5 {x['mean'] * 100:+.2f}%  "
                  f"beta-adj {a['mean'] * 100:+.2f}%  (day {a['day_mean'] * 100:+.2f}%, 95% {a['ci_low'] * 100:+.2f}…{a['ci_high'] * 100:+.2f})")


if __name__ == "__main__":
    main()
