"""`whaleproof analyze` guards (Amendment 7). Synthetic rows only; every path points into tmp_path."""
import json

import pytest

from tests.unit.test_analysis import synth_check_rows, synth_simple_rows
from whaleproof.commands import analyze as cmd


@pytest.fixture
def env(tmp_path):
    prereg = tmp_path / "prereg.md"
    prereg.write_text("# rules\n")
    paths = cmd.Paths(prereg=prereg, freeze=tmp_path / "freeze.json", marker=tmp_path / "holdout.marker",
                      docs=tmp_path / "docs", weights=tmp_path / "v1.json", results=tmp_path / "results")
    calls = []

    def check(store, start, end, weights):
        calls.append(("check", start, end))
        return synth_check_rows(seed=len(calls)), 0

    def simple(store, start, end):
        calls.append(("simple", start, end))
        return synth_simple_rows(seed=len(calls)), 0

    return dict(paths=paths, runners=(check, simple), calls=calls, data_ok=lambda store, s, e: (True, "ok"))


def run(env, phase, **over):
    kw = dict(store=None, paths=env["paths"], runners=env["runners"], data_ok=env["data_ok"]) | over
    return cmd.run_phase(phase, **kw)


def test_train_uses_train_window_only_and_freezes(env):
    assert run(env, "train") == 0
    assert all(c[1] >= cmd.TRAIN[0] and c[2] <= cmd.TRAIN[1] for c in env["calls"])
    fz = json.loads(env["paths"].freeze.read_text())
    assert fz["prereg_sha256"] == cmd.sha256(env["paths"].prereg) and "H5.dark_pool" in fz["train_effects"]
    assert (env["paths"].docs / "analysis-train.md").exists() and env["paths"].weights.exists()
    simple_md = (env["paths"].docs / "analysis-train-simple.md").read_text()
    assert "profit factor" in simple_md and "trades/day" in simple_md
    assert (env["paths"].docs / "analysis-train-backtest.md").exists()
    combos = json.loads((env["paths"].results / "analysis-train-combos.json").read_text())
    assert "ranked" in combos and "finalists" in combos
    assert "Strategy lab" in (env["paths"].docs / "analysis-train-combos.md").read_text()


def test_train_on_incomplete_data_reports_but_does_not_freeze(env):
    assert run(env, "train", data_ok=lambda *a: (False, "history incomplete")) == 0
    assert (env["paths"].docs / "analysis-train.md").exists() and not env["paths"].freeze.exists()


def test_holdout_refuses_without_freeze(env):
    assert run(env, "holdout") != 0 and not env["paths"].marker.exists()


def test_holdout_refuses_when_prereg_changed_after_freeze(env):
    run(env, "train")
    env["paths"].prereg.write_text("# rules\n## Amendment 8\n")
    assert run(env, "holdout") != 0 and not env["paths"].marker.exists()


def test_holdout_refuses_on_incomplete_data(env):
    run(env, "train")
    assert run(env, "holdout", data_ok=lambda *a: (False, "prices not filled")) != 0
    assert not env["paths"].marker.exists()


def test_holdout_runs_once_on_holdout_window(env):
    run(env, "train")
    env["calls"].clear()
    assert run(env, "holdout") == 0
    assert all(c[1] >= cmd.HOLDOUT[0] and c[2] <= cmd.HOLDOUT[1] for c in env["calls"])
    md = (env["paths"].docs / "analysis-holdout.md").read_text()
    assert "Tradeable" in md and env["paths"].marker.exists()
    assert run(env, "holdout") != 0                            # second run refused
    assert run(env, "train") != 0                              # no re-freeze after the holdout


def test_marker_written_before_compute(env):
    run(env, "train")

    def boom(*a):
        raise RuntimeError("crash mid-run")
    with pytest.raises(RuntimeError):
        run(env, "holdout", runners=(boom, env["runners"][1]))
    assert env["paths"].marker.exists()


def test_fit_command_refuses_to_score_holdout_before_the_holdout_run(monkeypatch, tmp_path):
    from whaleproof.commands import fit
    monkeypatch.setattr(fit, "holdout_marker", lambda: tmp_path / "none.marker")
    assert fit.main(["--start", "2024-10-01", "--split", "2025-07-01", "--end", "2025-12-31"]) == 1


def test_backtest_command_refuses_holdout_overlap_before_the_holdout_run(monkeypatch, tmp_path):
    from whaleproof.commands import backtest, fit
    monkeypatch.setattr(fit, "holdout_marker", lambda: tmp_path / "none.marker")
    assert backtest.main(["--simple", "--start", "2026-05-01", "--end", "2026-06-30"]) == 1
    assert backtest.main(["--simple", "--start", "2024-10-01", "--end", "2025-09-30", "--dry-guard"]) == 0


def test_cost_comparison_written_for_train_and_holdout(env):
    """Amendment 18: report-only cost table beside the tests, both phases."""
    assert run(env, "train") == 0
    md = (env["paths"].docs / "analysis-train-costs.md").read_text()
    assert "Take list" in md and "Normal" in md
    assert "cost" in json.loads((env["paths"].results / "analysis-train.json").read_text())
    assert run(env, "holdout") == 0
    assert (env["paths"].docs / "analysis-holdout-costs.md").exists()
    assert "cost" in json.loads((env["paths"].results / "analysis-holdout.json").read_text())
