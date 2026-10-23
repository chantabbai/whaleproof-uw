"""EXPLORATORY (post-hoc, after the one-time run): concentration of the pre-period far-OTM signals
(docs/PREPERIOD-FAROTM-TEST.md). Cache-only. → journal/research/farotm-preperiod-robustness.json
Usage: uv run python scripts/research/farotm_preperiod_robustness.py"""
from __future__ import annotations

import json
import statistics as st
from collections import Counter, defaultdict

from whaleproof.config import REPO_ROOT, load_settings
from whaleproof.core.data_layer.store import Store
from whaleproof.desk.config import PRE
from whaleproof.desk.history import classify_rows, earnings_map, in_window, load_raw


def main() -> None:
    rows = classify_rows(load_raw(REPO_ROOT / "data" / "desk"), earnings_map(Store(load_settings().db_path)))
    rs = [r for r in in_window(rows, *PRE) if r.tier == "far_otm" and r.x5 is not None]
    x = sorted(r.x5 for r in rs)
    by_t = defaultdict(list)
    for r in rs:
        by_t[r.ticker].append(r.x5)
    tm = [st.fmean(v) for v in by_t.values()]
    out = {"label": "exploratory (post-hoc)", "n": len(x), "mean": st.fmean(x), "median": st.median(x),
           "mean_drop_top5": st.fmean(x[:-5]), "mean_trim5_each_side": st.fmean(x[5:-5]),
           "tickers": len(by_t), "top_tickers": Counter(r.ticker for r in rs).most_common(5),
           "ticker_weighted_mean": st.fmean(tm), "tickers_positive": sum(v > 0 for v in tm),
           "by_value": {v: {"n": len(g), "mean": st.fmean(g)} for v in ("cheap", "fair")
                        for g in [[r.x5 for r in rs if r.value == v]] if g}}
    path = REPO_ROOT / "journal" / "research" / "farotm-preperiod-robustness.json"
    path.write_text(json.dumps(out, indent=1))
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
