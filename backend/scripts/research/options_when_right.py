"""EXPLORATORY: did the whale's own call lose even when the stock moved the right way? (copy check, owner 2026-09-30)
Signals whose 5-session stock return in the signal direction (r5, net costs) was > 0 → the whale option's 5-session
return (conservative fills: buy = opening trade + half the gap, sell = closing bid), per window. Cache-only.
→ journal/research/options-when-right.json   Usage: uv run python scripts/research/options_when_right.py"""
from __future__ import annotations

import json

from whaleproof.config import REPO_ROOT, load_settings
from whaleproof.core.data_layer.store import Store

from vehicle_study import load, summ, window_of   # same rows and fills as docs/STOCK-VS-OPTIONS.md


def main() -> None:
    raw, rows = load(Store(load_settings().db_path))
    out: dict = {}
    for h, (r, _) in zip(rows, raw):
        w = window_of(h.session_date)
        if not h.tier or not w or h.r5 is None or r.get("opt_r5") is None:
            continue
        d = out.setdefault(w, {"stock_right": [], "stock_wrong": []})
        d["stock_right" if h.r5 > 0 else "stock_wrong"].append(r["opt_r5"])
    rep = {"label": "exploratory", "metric": "whale option 5-session return, conservative fills; split by stock r5 > 0",
           **{w: {k: summ(v) for k, v in d.items()} for w, d in out.items()}}
    (REPO_ROOT / "journal" / "research" / "options-when-right.json").write_text(json.dumps(rep, indent=1))
    for w in ("train", "holdout", "post"):
        for k in ("stock_right", "stock_wrong"):
            s = rep[w][k]
            print(f"{w:8} {k:12} n {s['n']:4}  median {s['median'] * 100:+6.1f}%  mean {s['mean'] * 100:+6.1f}%  win {s['win_rate'] * 100:.0f}%")


if __name__ == "__main__":
    main()
