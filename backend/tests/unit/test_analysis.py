import random
from datetime import date, timedelta

import pytest

from whaleproof.core.backtest import analysis as an
from whaleproof.core.backtest.runner import BacktestRow
from whaleproof.core.verdict.weights import Weights

D0 = date(2025, 1, 2)


def row(day, x5=0.0, label="GO", scores=None, ticker="T", **kw):
    scores = scores or {}
    return BacktestRow(D0 + timedelta(days=day), ticker, 1, f"{day}{ticker}", 50, label, 1.0, scores,
                       {k: True for k in scores}, None, x5, None, None, None, x5=x5, **kw)


def test_boot_test_detects_clear_effect_and_is_deterministic():
    rnd = random.Random(1)
    daily = [0.01 + rnd.gauss(0, 0.01) for _ in range(100)]
    a, b = an.boot_test(daily), an.boot_test(daily)
    assert a == b
    assert a["n_days"] == 100 and a["p"] < 0.001 and a["ci_low"] > 0
    assert a["p"] >= 1 / (an.BOOT_B + 1)


def test_boot_test_null_is_not_significant():
    rnd = random.Random(2)
    daily = [rnd.gauss(0, 0.01) for _ in range(100)]
    m = sum(daily) / len(daily)
    assert an.boot_test([x - m + 0.0002 for x in daily])["p"] > 0.5


def test_boot_test_empty():
    assert an.boot_test([])["p"] == 1.0 and an.boot_test([])["mean"] is None


def test_paired_uses_days_with_both_sides():
    a = [row(0, 0.02), row(0, 0.04), row(1, 0.01), row(2, 0.05)]
    b = [row(0, 0.01), row(1, 0.03)]                       # day 2 has no b → dropped
    t = an.paired(a, b, "x5")
    assert t["n_days"] == 2
    assert t["mean"] == pytest.approx(((0.03 - 0.01) + (0.01 - 0.03)) / 2)


def test_one_sample_daily_means():
    t = an.one_sample([row(0, 0.02), row(0, 0.04), row(1, -0.01)], "x5")
    assert t["n_days"] == 2 and t["mean"] == pytest.approx((0.03 - 0.01) / 2)


def test_holm_step_down_and_monotone():
    adj = an.holm({"a": 0.01, "b": 0.04, "c": 0.03, "d": 0.5})
    assert adj["a"] == pytest.approx(0.04)
    assert adj["c"] == pytest.approx(0.09)
    assert adj["b"] == pytest.approx(0.09)                # max(2*0.04, previous) → monotone
    assert adj["d"] == pytest.approx(0.5)


def test_signed_rescore_uses_abs_denominator():
    w = Weights("v1", {"flow_quality": 0.5, "dark_pool": -0.5})
    r = row(0, scores={"flow_quality": 1.0, "dark_pool": -1.0})
    assert an.rescore(r, w) == pytest.approx(100.0)      # both agree with their signs
    r2 = row(0, scores={"flow_quality": 1.0, "dark_pool": 1.0})
    assert an.rescore(r2, w) == pytest.approx(50.0)


def test_top_n_rescored_go_only():
    w = Weights("v1", {"flow_quality": 1.0})
    rows = [row(0, scores={"flow_quality": s}, ticker=t) for s, t in [(0.9, "A"), (0.8, "B"), (0.1, "C")]]
    top = an.top_n(rows, w, 1)
    assert [r.ticker for r in top] == ["A"]
    assert all(an.rescore(r, w) >= 70 for r in an.top_n(rows, w, 5))


def test_tercile_cuts_and_degenerate_split():
    cuts = an.tercile_cuts([0.0] * 80 + [1.0] * 20)
    assert cuts[0] == cuts[1] == 0.0
    top, bottom = an.tercile_split([row(0, scores={"c": 1.0}), row(0, scores={"c": 0.0})], "c", cuts)
    assert len(top) == 1 and len(bottom) == 1
    cuts = an.tercile_cuts([i / 10 for i in range(11)])
    top, bottom = an.tercile_split([row(0, scores={"c": v / 10}) for v in range(11)], "c", cuts)
    assert min(r.scores["c"] for r in top) >= cuts[1] and max(r.scores["c"] for r in bottom) <= cuts[0]


def test_tradeable_rule():
    ok = dict(effect=0.004, p_holm=0.01, train_effect=0.003, n_days=80)
    assert an.tradeable(**ok)
    assert not an.tradeable(**ok | {"p_holm": 0.06})
    assert not an.tradeable(**ok | {"train_effect": -0.001})
    assert not an.tradeable(**ok | {"effect": 0.0015})
    assert not an.tradeable(**ok | {"n_days": 59})


# ---------- orchestration: choose on train → test → Holm → tradeable (synthetic data only) ----------
from whaleproof.core.verdict.setups import SETUPS  # noqa: E402

CHECKS = ["flow_quality", "dark_pool", "dp_blocks", "ticker_flow", "sector_flow", "skew", "iv_rv", "macro_event",
          "uw_flagged", "regime", "gamma_room", "vol_price", "persistence", "catalyst", "insider"]


def synth_check_rows(days=120, per_day=12, seed=0):
    """Top-40-pool rows: flow_quality predicts, dark_pool is contrarian, the rest is noise.
    Wider targets pay (grid), follow-the-money helps, OI-confirmed beats unconfirmed."""
    rnd, out = random.Random(seed), []
    for d in range(days):
        for i in range(per_day):
            s = {c: rnd.choice([-1.0, -0.5, 0.0, 0.5, 1.0]) for c in CHECKS}
            s["macro_event"] = rnd.choice([0.0, 0.0, 1.0])
            s["uw_flagged"] = 1.0 if i < 3 else 0.0
            x5 = 0.01 * s["flow_quality"] - 0.01 * s["dark_pool"] + 0.004 * s["uw_flagged"] + rnd.gauss(0, 0.01)
            label = "GO" if s["flow_quality"] > 0 else "SKIP"
            base = rnd.gauss(0, 0.01)
            grid = {f"{a}x{b}": base + (0.004 if b == 2.0 else 0.0) for a in (0.75, 1.0, 1.5) for b in (1.25, 2.0)}
            out.append(BacktestRow(D0 + timedelta(days=d), f"T{i}", 1, f"{d}-{i}", 50, label, 1.0, s,
                                   {c: True for c in CHECKS}, None, x5, None, None, None, x5=x5,
                                   plan_return=base, plan_follow_return=base + 0.003,
                                   oi_ratio=0.8 if i % 2 else 0.2, grid=grid, em=1.0))
            if i % 2 == 0:
                out[-1] = out[-1].__class__(**{**out[-1].__dict__, "x5": x5 - 0.004})
    return out


def synth_simple_rows(days=120, seed=1):
    rnd, out = random.Random(seed), []
    for d in range(days):
        for i, setup in enumerate(list(SETUPS) + [None, None]):
            x5 = (0.006 if setup == "whale_sweep" else 0.0) + (-0.003 if setup is None else 0.0) + rnd.gauss(0, 0.01)
            out.append(BacktestRow(D0 + timedelta(days=d), f"S{i}", 1, f"s{d}-{i}", 0, "PURE" if setup else "NOISE",
                                   0.0, {}, {}, None, x5, None, None, None, x5=x5, setup=setup))
    return out


def test_choose_on_train_fixes_signs_cuts_cell_and_signed_v1():
    ch = an.choose(synth_check_rows(), synth_simple_rows())
    assert ch["signs"]["H5.dark_pool"] == -1 and ch["signs"]["H3"] == 1
    assert ch["h6_cell"].endswith("x2.0")
    assert ch["v1"]["w"]["dark_pool"] < 0 < ch["v1"]["w"]["flow_quality"]
    assert set(ch["cuts"]) >= {"dark_pool", "skew", "macro_event"}
    assert "option_sentiment" in ch["dropped"]                 # never available → not backtestable


def test_family_members_and_insufficient_data():
    ch = an.choose(synth_check_rows(), synth_simple_rows())
    res = an.run_tests(synth_check_rows(days=40, seed=5), synth_simple_rows(days=40, seed=6), ch)
    names = set(res)
    assert {"H1", "H2", "H3", "H4", "H6", "H7", "H8", "H10"} <= names
    assert {f"H5.{c}" for c in an.H5_CHECKS} <= names and {f"S.{s}" for s in SETUPS} <= names
    assert "H9.option_sentiment" in names and "H11" not in names
    assert all(r["status"] in ("insufficient data", "not backtestable") and r["p"] == 1.0 for r in res.values())


def test_h6_no_change_when_train_picks_current_cell():
    ch = an.choose(synth_check_rows(), synth_simple_rows()) | {"h6_cell": an.H6_BASE}
    res = an.run_tests(synth_check_rows(), synth_simple_rows(), ch)
    assert "H6" not in res


def test_finalize_holm_and_tradeable_table():
    ch = an.choose(synth_check_rows(), synth_simple_rows())
    train = an.run_tests(synth_check_rows(), synth_simple_rows(), ch)
    hold = an.finalize(an.run_tests(synth_check_rows(seed=9), synth_simple_rows(seed=10), ch),
                       {k: v["mean"] for k, v in train.items()})
    assert hold["H5.dark_pool"]["mean"] > 0                      # oriented by the train sign (fade)
    assert hold["H5.dark_pool"]["tradeable"] and hold["S.whale_sweep"]["tradeable"]
    assert not hold["S.sweep"]["tradeable"] and not hold["H9.skew"]["tradeable"]
    assert all(v["p_holm"] >= v["p"] for v in hold.values())
    md = an.render(hold, {"phase": "holdout", "start": "a", "end": "b"})
    assert "Tradeable" in md and "H5.dark_pool" in md and "Not investment advice" in md


def test_train_report_never_claims_tradeable():
    ch = an.choose(synth_check_rows(), synth_simple_rows())
    res = an.run_tests(synth_check_rows(), synth_simple_rows(), ch)
    fin = an.finalize(res, {k: v["mean"] for k, v in res.items()}, phase="train")
    assert not any(v["tradeable"] for v in fin.values())
    md = an.render(fin, {"phase": "train", "start": "a", "end": "b"})
    assert "**yes**" not in md and "in-sample" in md


def test_unavailable_check_stays_in_family_as_insufficient():
    ch = an.choose(synth_check_rows(), synth_simple_rows())
    res = an.run_tests(synth_check_rows(), synth_simple_rows(), ch)
    assert res["H9.option_sentiment"]["status"] == "not backtestable" and res["H9.option_sentiment"]["p"] == 1.0


def test_holm_runs_per_family_setups_separate_from_score_hypotheses():
    """Amendment 8: family A = setups + H10 (the trading engine), family B = weighted-score hypotheses."""
    assert an.family("S.sweep") == an.family("H10") == "A"
    assert an.family("H1") == an.family("H5.dark_pool") == an.family("H9.skew") == "B"
    res = {k: {"p": 0.01, "status": "tested", "mean": 0.01, "n_days": 100} for k in ["S.sweep", "H10"]}
    res |= {f"H5.c{i}": {"p": 0.01, "status": "tested", "mean": 0.01, "n_days": 100} for i in range(10)}
    fin = an.finalize(res, {k: 0.01 for k in res})
    assert fin["S.sweep"]["p_holm"] == pytest.approx(0.02) and fin["H5.c0"]["p_holm"] == pytest.approx(0.10)


def test_finalists_are_family_c_and_tested_on_matching_simple_rows():
    """Amendment 12: F1–F3 frozen in combos.FINALISTS, one-sample x5 on matching gate passers, Holm within family C."""
    from whaleproof.core.backtest import combos as cb
    assert set(cb.FINALISTS) == {"F.1", "F.2", "F.3"} and an.family("F.2") == "C"
    assert all(b in cb.BLOCKS for blocks in cb.FINALISTS.values() for b in blocks)
    rnd, simple = random.Random(3), []
    for d in range(100):
        for i in range(4):
            cheap_long = i < 2
            simple.append(BacktestRow(D0 + timedelta(days=d), f"S{i}", 1 if cheap_long else -1, f"f{d}{i}", 0, "PURE",
                                      0.0, {}, {}, None, 0.0, None, None, None,
                                      x5=(0.01 if cheap_long else 0.0) + rnd.gauss(0, 0.005), setup="clean_other",
                                      value="cheap" if cheap_long else "rich", dte=40, otm_pct=0.02))
    ch = an.choose(synth_check_rows(), synth_simple_rows())
    assert ch["finalists"] == cb.FINALISTS
    res = an.finalize(an.run_tests(synth_check_rows(), simple, ch), {"F.2": 0.01, "F.1": 0.0, "F.3": 0.0})
    assert res["F.2"]["n_days"] == 100 and res["F.2"]["mean"] > 0.009 and res["F.2"]["tradeable"]
    assert res["F.1"]["status"] == "insufficient data"                     # no OI on these rows
    assert "F.2" in an.render(res, {"phase": "holdout", "start": "a", "end": "b"})
