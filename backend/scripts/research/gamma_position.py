"""EXPLORATORY: did a signal's position against UW's gamma levels change how it did?
(owner 2026-10-06, looking at AMAT: close 529.98 just under the 532.18 gamma flip, call wall 560, put wall 520.
"Can we tell the user to enter or wait based on gamma?" Filter untouched, post-holdout look.)
Levels = UW `gex-levels` for the signal day (stamped ~15:59 ET, known by that close; entry is the next open).
Groups, fixed before looking at any result:
  flip      above = signal-day close ≥ gamma flip (dealers long gamma, moves tend to be damped)
            below = close < gamma flip (dealers short gamma, moves tend to be amplified)
  call wall near  = call wall 0–3% above the close (little room before the wall)
            far   = call wall more than 3% above · through = close already above the call wall
  put wall  near  = put wall 0–3% below the close (a floor close by) · far = more than 3% below · through = close below it
Outcome = tracker stock trade (next open → 5th-session close, −0.10%) vs SPY, finished signals only.
Ranges: 1,000× bootstrap over signal days, for each group mean and for the gap between the two main groups.
Read: a difference only counts if it points the same way in the practice year AND the sealed test and the sealed-test
range of the gap excludes zero. Cache only (tracker rows from the running desk API, levels from SQLite).
→ journal/research/gamma-position.json   Usage: uv run python scripts/research/gamma_position.py [tracker.json]"""
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

SEED, BOOT, NEAR = 13, 1000, 0.03
SPLITS = {"flip": ("above", "below"), "call_wall": ("near", "far"), "put_wall": ("near", "far")}


def tracker_rows(path: str | None) -> list[dict]:
    if path:
        return json.loads(open(path).read())["rows"]
    with urllib.request.urlopen("http://127.0.0.1:8100/api/desk/tracker", timeout=120) as r:
        return json.loads(r.read())["rows"]


def groups(close: float, g: dict) -> dict[str, str | None]:
    out: dict[str, str | None] = {"flip": None, "call_wall": None, "put_wall": None}
    if g.get("gamma_flip"):
        out["flip"] = "above" if close >= g["gamma_flip"] else "below"
    if g.get("call_wall"):
        room = g["call_wall"] / close - 1
        out["call_wall"] = "through" if room < 0 else "near" if room <= NEAR else "far"
    if g.get("put_wall"):
        floor = 1 - g["put_wall"] / close
        out["put_wall"] = "through" if floor < 0 else "near" if floor <= NEAR else "far"
    return out


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


def main() -> None:
    store = Store(load_settings().db_path)
    rows = tracker_rows(sys.argv[1] if len(sys.argv) > 1 else None)
    rng = random.Random(SEED)
    data = defaultdict(lambda: {k: defaultdict(lambda: defaultdict(list)) for k in SPLITS})
    missing = 0
    for r in rows:
        s = r.get("stock") or {}
        if s.get("status") != "closed" or s.get("vs_spy") is None:
            continue
        d = date.fromisoformat(r["session_date"])
        g = store.conn.execute("SELECT payload FROM daily_metric WHERE ticker=? AND kind='gex' AND date=?",
                               (r["ticker"], d.isoformat())).fetchone()
        bars = [b for b in store.get_ohlc(r["ticker"], d - timedelta(days=3), d) if b.date == d]
        if not g or not bars or not bars[0].close:
            missing += 1
            continue
        for split, grp in groups(bars[0].close, json.loads(g[0])).items():
            if grp is None:
                continue
            for p in (r["period"], "All periods"):
                data[p][split][grp][r["session_date"]].append(s["vs_spy"])
    out = {"note": __doc__.split("\n")[0], "near_pct": NEAR, "no_levels_or_close": missing, "periods": {}}
    for p, splits in data.items():
        out["periods"][p] = {}
        for split, gs in splits.items():
            a, b = SPLITS[split]
            out["periods"][p][split] = {
                "groups": {k: {"trades": sum(len(v) for v in by.values()),
                               "mean_vs_spy": round(st.mean([x for v in by.values() for x in v]), 5),
                               "beat_spy": round(st.mean([x > 0 for v in by.values() for x in v]), 3),
                               "range": boot(by, rng)} for k, by in gs.items()},
                f"{a}_minus_{b}": gap_boot(gs.get(a, {}), gs.get(b, {}), rng),
            }
    path = REPO_ROOT / "journal/research/gamma-position.json"
    path.write_text(json.dumps(out, indent=1) + "\n")
    print(f"finished signals without levels or close: {missing}")
    for p, splits in sorted(out["periods"].items()):
        print(f"\n{p}")
        for split, v in splits.items():
            gs = "  ".join(f"{k} {x['trades']}·{x['mean_vs_spy']:+.2%}" for k, x in sorted(v["groups"].items()))
            gap = next(val for key, val in v.items() if key.endswith("_minus_" + SPLITS[split][1]))
            print(f"  {split:9} {gs}   gap " + (f"[{gap[0]:+.2%}…{gap[1]:+.2%}]" if gap else "—"))


if __name__ == "__main__":
    main()
