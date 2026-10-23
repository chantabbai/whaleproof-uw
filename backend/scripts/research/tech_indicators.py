"""EXPLORATORY: did a signal stock's own RSI or 50-day trend change how the signal did?
(owner 2026-10-07, parked research: "technical indicators as a confluence note". Filter frozen, post-holdout look →
any effect becomes a card note only, like OI.) Prior: SPY above/below its 50-day made no difference on train
(46.6% vs 46.9% beat SPY); chase_guard (price stretch) did help (55.1%).
Indicators from our stored daily bars (no UW calls), closes up to and including the signal day (known at that close;
entry is the next open). Groups, fixed before looking at any result:
  rsi      RSI(14), Wilder, read in the bet's direction (bearish bet → 100 − RSI)
           stretched = ≥ 70 (stock already ran hard the bet's way) · rest = < 70   (also counted: washed = ≤ 30)
  trend50  with    = signal-day close on the bet's side of its 50-day average (bull above, bear below)
           against = close on the other side
Outcome = tracker stock trade (next open → 5th-session close, −0.10%) vs SPY, finished signals only.
Ranges: 1,000× bootstrap over signal days, for each group mean and for the gap between the two main groups.
Read: a difference only counts if it points the same way in the practice year AND the sealed test and the sealed-test
range of the gap excludes zero. Cache only (tracker rows from a desk API or a saved tracker JSON, bars from SQLite).
→ journal/research/tech-indicators.json   Usage: uv run python scripts/research/tech_indicators.py [tracker.json]"""
from __future__ import annotations

import json
import random
import statistics as st
import sys
import urllib.request
from collections import defaultdict
from datetime import date, timedelta

from whaleproof.config import REPO_ROOT, load_settings
from whaleproof.core.data_layer.store import Store

SEED, BOOT, RSI_N, SMA_N, HOT, COLD = 13, 1000, 14, 50, 70.0, 30.0
SPLITS = {"rsi": ("stretched", "rest"), "trend50": ("with", "against")}


def tracker_rows(path: str | None) -> list[dict]:
    if path:
        return json.loads(open(path).read())["rows"]
    with urllib.request.urlopen("http://127.0.0.1:8100/api/desk/tracker", timeout=300) as r:
        return json.loads(r.read())["rows"]


def rsi(closes: list[float], n: int = RSI_N) -> float | None:
    if len(closes) < n + 1:
        return None
    ch = [b - a for a, b in zip(closes, closes[1:])]
    gain = sum(max(c, 0) for c in ch[:n]) / n
    loss = sum(max(-c, 0) for c in ch[:n]) / n
    for c in ch[n:]:
        gain = (gain * (n - 1) + max(c, 0)) / n
        loss = (loss * (n - 1) + max(-c, 0)) / n
    if loss == 0:
        return 100.0 if gain > 0 else 50.0
    return 100 - 100 / (1 + gain / loss)


def sma(closes: list[float], n: int) -> float | None:
    return st.mean(closes[-n:]) if len(closes) >= n else None


def groups(closes: list[float], direction: int) -> dict[str, str | None]:
    out: dict[str, str | None] = {"rsi": None, "trend50": None}
    r = rsi(closes)
    if r is not None:
        out["rsi"] = "stretched" if (r if direction > 0 else 100 - r) >= HOT else "rest"
    m = sma(closes, SMA_N)
    if m is not None:
        out["trend50"] = "with" if direction * (closes[-1] - m) > 0 else "against"
    return out


def washed(closes: list[float], direction: int) -> bool:
    r = rsi(closes)
    return r is not None and (r if direction > 0 else 100 - r) <= COLD


def boot(by_day: dict[str, list[float]], rng: random.Random) -> list[float] | None:
    days = list(by_day)
    if len(days) < 5:
        return None
    means = sorted(st.mean([x for d in (rng.choice(days) for _ in days) for x in by_day[d]]) for _ in range(BOOT))
    return [round(means[int(0.025 * BOOT)], 5), round(means[int(0.975 * BOOT) - 1], 5)]


def gap_boot(a: dict, b: dict, rng: random.Random) -> list[float] | None:
    days = sorted(set(a) | set(b))
    if len(a) < 5 or len(b) < 5:
        return None
    out = []
    for _ in range(BOOT):
        pick = [rng.choice(days) for _ in days]
        xa = [x for d in pick for x in a.get(d, [])]
        xb = [x for d in pick for x in b.get(d, [])]
        if xa and xb:
            out.append(st.mean(xa) - st.mean(xb))
    out.sort()
    return [round(out[int(0.025 * len(out))], 5), round(out[int(0.975 * len(out)) - 1], 5)]


def summary(by: dict[str, list[float]], rng: random.Random) -> dict:
    xs = [x for v in by.values() for x in v]
    return {"trades": len(xs), "mean_vs_spy": round(st.mean(xs), 5), "beat_spy": round(st.mean([x > 0 for x in xs]), 3),
            "range": boot(by, rng)}


def main() -> None:
    store = Store(load_settings().db_path)
    rows = tracker_rows(sys.argv[1] if len(sys.argv) > 1 else None)
    rng = random.Random(SEED)
    data = defaultdict(lambda: {k: defaultdict(lambda: defaultdict(list)) for k in SPLITS})
    wash = defaultdict(lambda: defaultdict(list))
    short = 0
    for r in rows:
        s = r.get("stock") or {}
        if s.get("status") != "closed" or s.get("vs_spy") is None:
            continue
        d = date.fromisoformat(r["session_date"])
        closes = [b.close for b in store.get_ohlc(r["ticker"], d - timedelta(days=160), d) if b.close]
        g = groups(closes, r["direction"])
        if g["trend50"] is None:
            short += 1
        for p in (r["period"], "All periods"):
            for split, grp in g.items():
                if grp is not None:
                    data[p][split][grp][r["session_date"]].append(s["vs_spy"])
            if washed(closes, r["direction"]):
                wash[p][r["session_date"]].append(s["vs_spy"])
    out = {"note": __doc__.split("\n")[0], "rsi_n": RSI_N, "sma_n": SMA_N, "stretched_at": HOT, "washed_at": COLD,
           "under_50_bars": short, "periods": {}}
    for p, splits in data.items():
        out["periods"][p] = {}
        for split, gs in splits.items():
            a, b = SPLITS[split]
            out["periods"][p][split] = {"groups": {k: summary(by, rng) for k, by in gs.items()},
                                        f"{a}_minus_{b}": gap_boot(gs.get(a, {}), gs.get(b, {}), rng)}
        if wash[p]:
            out["periods"][p]["rsi"]["groups"]["washed (info)"] = summary(wash[p], rng)
    path = REPO_ROOT / "journal/research/tech-indicators.json"
    path.write_text(json.dumps(out, indent=1) + "\n")
    print(f"finished signals with under {SMA_N} bars (no 50-day): {short}")
    for p, splits in sorted(out["periods"].items()):
        print(f"\n{p}")
        for split, v in splits.items():
            gs = "  ".join(f"{k} {x['trades']}·{x['mean_vs_spy']:+.2%}·{x['beat_spy']:.0%}"
                           for k, x in sorted(v["groups"].items()))
            gap = next(val for key, val in v.items() if key.endswith("_minus_" + SPLITS[split][1]))
            print(f"  {split:8} {gs}   gap " + (f"[{gap[0]:+.2%}…{gap[1]:+.2%}]" if gap else "—"))


if __name__ == "__main__":
    main()
