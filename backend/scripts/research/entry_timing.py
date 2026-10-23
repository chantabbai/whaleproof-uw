"""EXPLORATORY: buy at the signal day's close (proxy for an after-hours buy) instead of the next open?
(owner 2026-10-06: "OI doesn't change the decision anyway, so why wait for the open?"; filter untouched, post-holdout look.)
Same signals, same exit (close of the 5th session after the signal day), same −0.10% cost. Only the entry moves:
  next_open  = the tested rule (tracker rows as they are)
  same_close = the signal day's regular-session close. An after-hours fill (4:15–8 PM ET, once the day's flow is final)
               trades near that close, but with wider spreads, thinner books and any after-hours news move, so this is a
               best case for the after-hours buy. True extended-hours prices aren't in the cache.
SPY is moved the same way (close→close vs open→close) so both are measured against the market over matching windows.
Difference per trade = same_close − next_open = the overnight gap in the signal's direction (minus SPY's gap).
Ranges: 1,000× bootstrap resampling signal days. Cache only (tracker rows from the running desk API, bars from SQLite).
→ journal/research/entry-timing.json   Usage: uv run python scripts/research/entry_timing.py [tracker.json]"""
from __future__ import annotations

import json
import random
import statistics as st
import sys
import urllib.request
from collections import defaultdict
from datetime import date, timedelta

from whaleproof.config import REPO_ROOT, load_settings
from whaleproof.core.backtest.runner import COST
from whaleproof.core.data_layer.store import Store

SEED, BOOT = 11, 1000


def tracker_rows(path: str | None) -> list[dict]:
    if path:
        return json.loads(open(path).read())["rows"]
    with urllib.request.urlopen("http://127.0.0.1:8100/api/desk/tracker", timeout=120) as r:
        return json.loads(r.read())["rows"]


def close_on(store: Store, ticker: str, d: date, cache: dict) -> float | None:
    k = (ticker, d)
    if k not in cache:
        bars = [b for b in store.get_ohlc(ticker, d - timedelta(days=3), d) if b.date == d]
        cache[k] = bars[0].close if bars and bars[0].close else None
    return cache[k]


def boot(by_day: dict[str, list[float]], rng: random.Random) -> list[float] | None:
    days = list(by_day)
    if len(days) < 5:
        return None
    means = sorted(st.mean([x for d in (rng.choice(days) for _ in days) for x in by_day[d]]) for _ in range(BOOT))
    return [round(means[int(0.025 * BOOT)], 5), round(means[int(0.975 * BOOT) - 1], 5)]


def main() -> None:
    store = Store(load_settings().db_path)
    rows = tracker_rows(sys.argv[1] if len(sys.argv) > 1 else None)
    rng, cache = random.Random(SEED), {}
    per = defaultdict(lambda: {"open": defaultdict(list), "close": defaultdict(list), "diff": defaultdict(list), "gaps": []})
    skipped = 0
    for r in rows:
        s = r.get("stock") or {}
        if s.get("status") != "closed" or s.get("vs_spy") is None or s.get("spy_ret") is None:
            continue
        d = date.fromisoformat(r["session_date"])
        c0, spy_c0 = close_on(store, r["ticker"], d, cache), close_on(store, "SPY", d, cache)
        if not c0 or not spy_c0:
            skipped += 1
            continue
        dr = r["direction"]
        spy_bars = store.get_ohlc("SPY", date.fromisoformat(s["entry_date"]), date.fromisoformat(s["exit_date"]))
        if not spy_bars or not spy_bars[0].open:
            skipped += 1
            continue
        spy_exit = spy_bars[-1].close
        ret_close = (s["exit"] / c0 - 1) * dr - COST
        spy_close = spy_exit / spy_c0 - 1
        vs_close = ret_close - spy_close * dr
        gap = (s["entry"] / c0 - 1) * dr                        # overnight move in the signal's direction
        for p in (r["period"], "All periods"):
            per[p]["open"][r["session_date"]].append(s["vs_spy"])
            per[p]["close"][r["session_date"]].append(vs_close)
            per[p]["diff"][r["session_date"]].append(vs_close - s["vs_spy"])
            per[p]["gaps"].append(gap)
    out = {"note": __doc__.split("\n")[0], "skipped_no_close": skipped, "periods": {}}
    for p, v in per.items():
        flat = {k: [x for xs in v[k].values() for x in xs] for k in ("open", "close", "diff")}
        g = v["gaps"]
        out["periods"][p] = {
            "trades": len(flat["open"]),
            "next_open_vs_spy": round(st.mean(flat["open"]), 5),
            "same_close_vs_spy": round(st.mean(flat["close"]), 5),
            "difference": round(st.mean(flat["diff"]), 5), "difference_range": boot(v["diff"], rng),
            "beat_spy_next_open": round(sum(x > 0 for x in flat["open"]) / len(flat["open"]), 3),
            "beat_spy_same_close": round(sum(x > 0 for x in flat["close"]) / len(flat["close"]), 3),
            "gap_mean": round(st.mean(g), 5), "gap_median": round(st.median(g), 5),
            "gap_up_share": round(sum(x > 0 for x in g) / len(g), 3),
            "gap_over_5pct_either_way": round(sum(abs(x) > 0.05 for x in g) / len(g), 3),
        }
    path = REPO_ROOT / "journal/research/entry-timing.json"
    path.write_text(json.dumps(out, indent=1) + "\n")
    print(f"skipped (no signal-day close in cache): {skipped}")
    for p, v in out["periods"].items():
        rg = v["difference_range"]
        print(f"{p:42} {v['trades']:5}  next open {v['next_open_vs_spy']:+.2%}  same close {v['same_close_vs_spy']:+.2%}  "
              f"diff {v['difference']:+.2%} " + (f"[{rg[0]:+.2%}…{rg[1]:+.2%}]" if rg else "") +
              f"  gap mean {v['gap_mean']:+.2%} med {v['gap_median']:+.2%} up {v['gap_up_share']:.0%} >5% {v['gap_over_5pct_either_way']:.0%}")


if __name__ == "__main__":
    main()
