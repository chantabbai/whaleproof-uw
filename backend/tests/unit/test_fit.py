import random
from datetime import date, timedelta

import pytest

from whaleproof.core.backtest.fit import fit_weights
from whaleproof.core.backtest.runner import BacktestRow
from whaleproof.core.verdict.weights import BACKTESTABLE, V0


def synth(n=600, seed=0):
    rnd = random.Random(seed)
    rows, d0 = [], date(2025, 1, 1)
    for i in range(n):
        fq, dp = rnd.uniform(-1, 1), rnd.uniform(-1, 1)
        r5 = 0.02 * fq + rnd.gauss(0, 0.01)  # only flow_quality predicts
        scores = {k: 0.0 for k in V0.w} | {"flow_quality": fq, "dark_pool": dp}
        rows.append(BacktestRow(d0 + timedelta(days=i % 400), "T", 1, str(i), 50, "WATCH", 1.0,
                                scores, {k: True for k in scores}, None, r5, None, None, None))
    return rows


def test_fit_learns_predictive_check_and_is_deterministic():
    rows = synth()
    w1 = fit_weights(rows, date(2025, 10, 1), "v1", base=V0)
    w2 = fit_weights(rows, date(2025, 10, 1), "v1", base=V0)
    assert w1 == w2
    assert w1.w["flow_quality"] > w1.w["dark_pool"]
    assert all(v >= 0 for v in w1.w.values())
    assert w1.w["unusualness"] == V0.w["unusualness"]  # live-only keeps prior
    assert round(sum(w1.w[n] for n in BACKTESTABLE if n in V0.w), 6) == round(sum(V0.w[n] for n in BACKTESTABLE if n in V0.w), 6)
    assert w1.meta["n_train"] > 0 and "oos_auc" in w1.meta


def test_fit_refuses_tiny_sample():
    with pytest.raises(ValueError):
        fit_weights(synth(50), date(2025, 2, 1), "v1", base=V0)


def synth_signed(n=800, seed=0):
    rnd = random.Random(seed)
    rows, d0 = [], date(2025, 1, 1)
    for i in range(n):
        fq, dp = rnd.uniform(-1, 1), rnd.uniform(-1, 1)
        x5 = 0.02 * fq - 0.02 * dp + rnd.gauss(0, 0.01)   # dark_pool is contrarian
        scores = {k: 0.0 for k in V0.w} | {"flow_quality": fq, "dark_pool": dp}
        rows.append(BacktestRow(d0 + timedelta(days=i % 300), "T", 1, str(i), 50, "WATCH", 1.0,
                                scores, {k: True for k in scores}, None, x5, None, None, None, x5=x5))
    return rows


def test_signed_fit_flips_contrarian_check_on_x5():
    w = fit_weights(synth_signed(), date(2026, 1, 1), "v1", base=V0, signed=True, label="x5")
    assert w.w["dark_pool"] < 0 < w.w["flow_quality"]
    budget = sum(V0.w[n] for n in BACKTESTABLE if n in V0.w)
    assert round(sum(abs(w.w[n]) for n in BACKTESTABLE if n in V0.w), 6) == round(budget, 6)
    assert w.meta["signed"] is True and w.meta["label"] == "x5"
    assert w.meta["oos_n"] == 0                              # split after all rows: nothing scored out of sample


def test_clipped_fit_is_default():
    w = fit_weights(synth_signed(), date(2026, 1, 1), "v1", base=V0)
    assert all(v >= 0 for v in w.w.values())
