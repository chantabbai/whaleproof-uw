from __future__ import annotations

import argparse
import json
from datetime import date

from whaleproof.config import REPO_ROOT, load_settings
from whaleproof.core.backtest.runner import render_report, run_backtest, summarize
from whaleproof.core.backtest.simple import run_simple_backtest
from whaleproof.core.data_layer.store import Store
from whaleproof.core.verdict.weights import CURRENT, load_weights


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(prog="whaleproof backtest")
    p.add_argument("--start", required=True, type=date.fromisoformat)
    p.add_argument("--end", required=True, type=date.fromisoformat)
    p.add_argument("--weights", default=None)
    p.add_argument("--simple", action="store_true",
                   help="simple rules: every pure-directional alert by setup (no cap, no score) → backtest-simple.md")
    p.add_argument("--gate", action="store_true",
                   help="v0.6 official-like pool: gate passers only before the top-40 cut → backtest-gated.md")
    p.add_argument("--out", default=None, help="report name override (e.g. backtest-train)")
    p.add_argument("--dry-guard", action="store_true", help=argparse.SUPPRESS)   # tests: check the guard only
    args = p.parse_args(argv)
    from whaleproof.commands.analyze import HOLDOUT
    from whaleproof.commands.fit import holdout_marker
    if args.start <= HOLDOUT[1] and args.end >= HOLDOUT[0] and not holdout_marker().exists():
        print(f"refused: {args.start} → {args.end} overlaps the holdout ({HOLDOUT[0]} → {HOLDOUT[1]}), which is run "
              "once by `analyze --phase holdout`")
        return 1
    if args.dry_guard:
        return 0
    weights = load_weights(args.weights) if args.weights else CURRENT
    store = Store(load_settings().db_path)
    if args.simple:
        rows, skipped = run_simple_backtest(store, args.start, args.end)
        name, label = args.out or "backtest-simple", "simple rules"
    else:
        rows, skipped = run_backtest(store, args.start, args.end, weights, gate=args.gate)
        name = args.out or ("backtest-gated" if args.gate else "backtest-report")
        label = f"{weights.version}{' gated' if args.gate else ''}"
    summary = summarize(rows, skipped)
    meta = {"start": args.start.isoformat(), "end": args.end.isoformat(), "weights": label}
    (REPO_ROOT / "docs" / f"{name}.md").write_text(render_report(summary, meta))
    (REPO_ROOT / "journal" / f"{name.replace('report', 'summary')}.json").write_text(
        json.dumps({"meta": meta, "summary": summary}, indent=2, sort_keys=True, default=str))
    print(f"{len(rows)} rows, {skipped} skipped → docs/{name}.md")
    return 0
