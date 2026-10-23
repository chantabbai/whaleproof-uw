"""Amendment 11: strategy combinations on TRAIN — singles, pairs, triples; risk-first ranking; ≤ 3 finalists.
Synthetic rows only."""
import random
from datetime import date, timedelta

from whaleproof.core.backtest import combos as cb
from whaleproof.core.backtest.runner import BacktestRow
from whaleproof.core.verdict.setups import SETUPS

D0 = date(2024, 10, 1)


def mk(day, setup, x5, oi=None, prem=5e5, direction=1, dte=40, otm=0.02, trend=1, value="fair", i=0):
    return BacktestRow(D0 + timedelta(days=day), f"T{i}", direction, f"{day}-{i}", 0.0, "PURE", 0.0, {}, {},
                       None, x5, None, None, None, x5=x5, dte=dte, premium=prem, setup=setup, oi_ratio=oi,
                       otm_pct=otm, spy_trend=trend, value=value)


def synth(days=360, seed=0):
    """whale_sweep + OI confirmed pays +1% vs market in both halves; everything else is noise around 0."""
    rnd, rows = random.Random(seed), []
    for d in range(days):
        for i, s in enumerate(SETUPS):
            confirmed = rnd.random() < 0.5
            edge = 0.01 if (s == "whale_sweep" and confirmed) else 0.0
            rows.append(mk(d, s, edge + rnd.gauss(0, 0.02), oi=0.8 if confirmed else 0.1,
                           prem=2e6 if s == "whale_sweep" else 4e5, direction=rnd.choice([1, -1]),
                           dte=rnd.choice([20, 60]), trend=rnd.choice([1, -1]), i=i))
        if d < 20:                                                   # a lucky but thin group: must not rank
            rows.append(mk(d, "far_otm", 0.08, otm=0.2, value="cheap", i=99))
    return rows


def test_blocks_cover_every_family_and_unknown_is_excluded():
    fams = {f for f, _ in cb.BLOCKS.values()}
    assert {"setup", "confirmed", "value", "dte", "size", "direction", "trend", "otm"} <= fams
    r = mk(0, "sweep", 0.01, oi=None)
    assert cb.BLOCKS["OI confirmed"][1](r) is None                 # unknown ≠ false


def test_combinations_are_singles_pairs_and_cross_family_triples():
    names = cb.combinations()
    assert ("OI confirmed",) in names and ("setup: whale sweep", "OI confirmed") in names
    assert all(len({cb.BLOCKS[b][0] for b in c}) == len(c) for c in names)   # never two blocks of one family
    assert max(len(c) for c in names) == 3


def test_stats_measure_return_and_risk():
    rows = [mk(d, "sweep", 0.01 if d % 2 else -0.004) for d in range(100)]
    s = cb.stats(rows, total_days=100)
    assert s["n"] == 100 and s["n_days"] == 100 and 0.4 < s["win_rate"] < 0.6
    assert s["max_drawdown"] < 0 and s["worst_day"] < 0 and s["losing_streak"] == 1
    assert s["shrunk"] < s["mean_x5"]                              # pulled toward zero


def test_explore_finds_the_real_edge_and_ignores_thin_luck():
    res = cb.explore(synth(), split=D0 + timedelta(days=180))
    top = res["ranked"][0]
    assert set(top["blocks"]) >= {"setup: whale sweep", "OI confirmed"} or set(top["blocks"]) == {"OI confirmed", "whale ≥ $1M"}
    assert all(r["n"] >= cb.MIN_TRADES and r["n_days"] >= cb.MIN_DAYS for r in res["ranked"])
    assert all(r["stable"] for r in res["ranked"])
    assert not any(r["blocks"] == ("setup: far OTM", "option cheap") for r in res["ranked"])   # 20 lucky days
    assert 1 <= len(res["finalists"]) <= 3
    assert res["baseline"]["n"] > 0


def test_finalists_prefer_the_simpler_rule_when_close():
    ranked = [{"blocks": ("a", "b", "c"), "score": 1.00}, {"blocks": ("a", "b"), "score": 0.95},
              {"blocks": ("d",), "score": 0.50}]
    assert cb.pick_finalists(ranked)[0]["blocks"] == ("a", "b")


def test_render_is_plain_english():
    md = cb.render(cb.explore(synth(days=200), split=D0 + timedelta(days=100)), {"start": "a", "end": "b"})
    assert "Beat the market" in md and "Biggest drop" in md and "finalist" in md.lower()


def test_stats_report_real_option_results_descriptively():
    rows = [mk(d, "sweep", 0.01) for d in range(10)]
    rows = [r.__class__(**{**r.__dict__, "opt_r5": 0.5 if i % 2 else -0.3}) for i, r in enumerate(rows)]
    rows.append(mk(11, "sweep", 0.01))                                   # no option history → not counted
    s = cb.stats(rows, total_days=11)
    assert s["opt_n"] == 10 and abs(s["opt_mean"] - 0.1) < 1e-9 and s["opt_win_rate"] == 0.5
    assert abs(s["opt_median"] - 0.1) < 1e-9 and s["opt_coverage"] == 10 / 11
