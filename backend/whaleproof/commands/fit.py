from __future__ import annotations

import argparse
import json
from datetime import date

from whaleproof.config import REPO_ROOT, load_settings
from whaleproof.core.backtest.fit import fit_weights
from whaleproof.core.backtest.runner import render_report, run_backtest, summarize
from whaleproof.core.data_layer.store import Store
from whaleproof.core.verdict.weights import V0, save_weights


def holdout_marker():
    from whaleproof.commands.analyze import default_paths
    return default_paths().marker


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(prog="whaleproof fit")
    p.add_argument("--start", required=True, type=date.fromisoformat)
    p.add_argument("--split", required=True, type=date.fromisoformat)
    p.add_argument("--end", required=True, type=date.fromisoformat)
    p.add_argument("--version", default="v1")
    args = p.parse_args(argv)
    from whaleproof.commands.analyze import TRAIN
    if args.end > TRAIN[1] and not holdout_marker().exists():
        print(f"refused: --end after {TRAIN[1]} would score holdout data before the pre-registered holdout run "
              "(use `analyze --phase train`)")
        return 1
    store = Store(load_settings().db_path)
    rows, _ = run_backtest(store, args.start, args.end, V0)
    w = fit_weights(rows, args.split, args.version)
    path = REPO_ROOT / "journal" / "weights" / f"{args.version}.json"
    save_weights(w, path)
    oos, skipped = run_backtest(store, args.split, args.end, w)
    meta = {"start": args.split.isoformat(), "end": args.end.isoformat(), "weights": w.version}
    (REPO_ROOT / "docs" / "backtest-report.md").write_text(
        render_report(summarize(oos, skipped), meta) + "\n## Fit\n\n```json\n" + json.dumps(w.meta, indent=2) + "\n```\n")
    print(f"saved {path}: {json.dumps(w.meta)}")
    return 0
