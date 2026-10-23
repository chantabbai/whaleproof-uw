"""Pre-registered analysis (docs/preregistration.md, Amendment 7).

  whaleproof analyze --phase train     train window only: fit signed v1, choose signs/cuts/H6 cell, report, freeze
  whaleproof analyze --phase holdout   once: needs the freeze, an unchanged pre-registration and complete data
"""
from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path

from whaleproof.config import REPO_ROOT, load_settings
from whaleproof.core.backtest import analysis as an
from whaleproof.core.backtest import combos as cb
from whaleproof.core.backtest import costs
from whaleproof.core.backtest.runner import render_report, run_backtest, summarize
from whaleproof.core.backtest.simple import run_simple_backtest
from whaleproof.core.data_layer.store import Store
from whaleproof.core.verdict.weights import V05, Weights, save_weights

TRAIN = (date(2024, 10, 1), date(2025, 9, 30))
HOLDOUT = (date(2025, 10, 1), date(2026, 5, 29))
TRAIN_SPLIT = date(2025, 4, 1)          # Amendment 11 stability check: both halves of train must be positive


@dataclass(frozen=True)
class Paths:
    prereg: Path
    freeze: Path
    marker: Path
    docs: Path
    weights: Path
    results: Path


def default_paths() -> Paths:
    j = REPO_ROOT / "journal"
    return Paths(prereg=REPO_ROOT / "docs" / "preregistration.md", freeze=j / "analysis-freeze.json",
                 marker=j / "analysis-holdout.marker", docs=REPO_ROOT / "docs", weights=j / "weights" / "v1.json",
                 results=j)


def sha256(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def data_complete(store: Store, start: date, end: date) -> tuple[bool, str]:
    from whaleproof.commands.backfill import backfill_complete
    if not backfill_complete(store, start, end):
        return False, f"alert history incomplete for {start} → {end}"
    from whaleproof import market_calendar as mc
    if any(store.get_checkpoint(f"enrich:{d.isoformat()}") != "done" for d in mc.sessions(start, end)):
        return False, f"enrich (UW unusual list + IV/RV history) incomplete for {start} → {end}"
    done = store.get_checkpoint("prices_done")
    if not done or date.fromisoformat(done) < end:
        return False, f"price fill not complete through {end} (prices_done={done})"
    return True, "ok"


def _write(paths: Paths, phase: str, results: dict, meta: dict, check=None, simple=None,
           finalists: dict | None = None) -> None:
    paths.docs.mkdir(parents=True, exist_ok=True)
    (paths.docs / f"analysis-{phase}.md").write_text(an.render(results, meta))
    cost = costs.cost_table(simple[0], finalists or {}) if simple is not None else {}   # Amendment 18, report only
    if simple is not None:
        (paths.docs / f"analysis-{phase}-costs.md").write_text(costs.render(cost, meta))
    # headline tables (setups with profit factor + trades/day, breakdowns) from the same rows — no second run needed
    for name, pair, label in (("backtest", check, "v0.5"), ("simple", simple, "simple rules")):
        if pair is not None:
            rows, skipped = pair
            (paths.docs / f"analysis-{phase}-{name}.md").write_text(render_report(
                summarize(rows, skipped), {"start": meta["start"], "end": meta["end"], "weights": f"{label}, {phase}"}))
    paths.results.mkdir(parents=True, exist_ok=True)
    (paths.results / f"analysis-{phase}.json").write_text(
        json.dumps({"meta": meta, "results": results, "cost": cost}, indent=2, sort_keys=True, default=str))


def run_phase(phase: str, store, paths: Paths, runners=(run_backtest, run_simple_backtest),
              data_ok=data_complete, now=lambda: datetime.now(timezone.utc)) -> int:
    check_run, simple_run = runners
    if paths.marker.exists():
        print(f"refused: holdout already run ({paths.marker}); results are final")
        return 1
    if phase == "train":
        start, end = TRAIN
        ok, why = data_ok(store, start, end)
        check_rows, check_skip = check_run(store, start, end, V05)
        simple_rows, simple_skip = simple_run(store, start, end)
        ch = an.choose(check_rows, simple_rows)
        res = an.run_tests(check_rows, simple_rows, ch)
        train_effects = {k: v["mean"] for k, v in res.items()}
        res = an.finalize(res, train_effects, phase="train")
        meta = {"phase": "train", "start": start.isoformat(), "end": end.isoformat(), "data": why,
                "h6_cell": ch["h6_cell"], "dropped": ch["dropped"], "signs": ch["signs"]}
        _write(paths, "train", res, meta, (check_rows, check_skip), (simple_rows, simple_skip), ch.get("finalists"))
        # Amendment 11: strategy combinations on train (halves split at TRAIN_SPLIT); finalists chosen by hand later
        combo = cb.explore(simple_rows, split=TRAIN_SPLIT)
        (paths.docs / "analysis-train-combos.md").write_text(cb.render(combo, meta))
        (paths.results / "analysis-train-combos.json").write_text(
            json.dumps(combo, indent=2, sort_keys=True, default=str))
        if not ok:
            print(f"train report written, NOT frozen: {why}")
            return 0
        save_weights(Weights(ch["v1"]["version"], ch["v1"]["w"], ch["v1"]["meta"]), paths.weights)
        paths.freeze.parent.mkdir(parents=True, exist_ok=True)
        paths.freeze.write_text(json.dumps(
            {"frozen_at": now().isoformat(), "prereg_sha256": sha256(paths.prereg), "choices": ch,
             "train_effects": train_effects, "train": [start.isoformat(), end.isoformat()]},
            indent=2, sort_keys=True, default=str))
        print(f"train: {len(check_rows)} check rows, {len(simple_rows)} simple rows → frozen {paths.freeze}")
        return 0
    if phase != "holdout":
        print(f"unknown phase {phase}")
        return 2
    if not paths.freeze.exists():
        print("refused: no freeze — run `analyze --phase train` on complete train data first")
        return 1
    fz = json.loads(paths.freeze.read_text())
    if fz["prereg_sha256"] != sha256(paths.prereg):
        print("refused: docs/preregistration.md changed after the freeze — re-run the train phase to re-freeze")
        return 1
    start, end = HOLDOUT
    ok, why = data_ok(store, start, end)
    if not ok:
        print(f"refused: {why}")
        return 1
    paths.marker.parent.mkdir(parents=True, exist_ok=True)
    paths.marker.write_text(json.dumps({"started_at": now().isoformat(), "prereg_sha256": fz["prereg_sha256"]}))
    check_rows, check_skip = check_run(store, start, end, V05)
    simple_rows, simple_skip = simple_run(store, start, end)
    res = an.finalize(an.run_tests(check_rows, simple_rows, fz["choices"]), fz["train_effects"])
    meta = {"phase": "holdout", "start": start.isoformat(), "end": end.isoformat(), "frozen_at": fz["frozen_at"],
            "prereg_sha256": fz["prereg_sha256"]}
    _write(paths, "holdout", res, meta, (check_rows, check_skip), (simple_rows, simple_skip),
           fz["choices"].get("finalists"))
    print(f"holdout: {sum(v['tradeable'] for v in res.values())} tradeable of {len(res)} → "
          f"{paths.docs / 'analysis-holdout.md'}")
    return 0


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(prog="whaleproof analyze")
    p.add_argument("--phase", required=True, choices=["train", "holdout"])
    args = p.parse_args(argv)
    return run_phase(args.phase, Store(load_settings().db_path), default_paths())
