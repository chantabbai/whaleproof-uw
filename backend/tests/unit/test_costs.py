"""Amendment 18: cost comparison (mid / normal / wide fills) per finalist and the Take list — report only."""
from datetime import date

from whaleproof.core.backtest import costs
from whaleproof.core.backtest.runner import BacktestRow


def row(d, ticker, normal, mid=None, wide=None, setup="far_otm", premium=1e6, direction=1, x5=0.01):
    return BacktestRow(session_date=d, ticker=ticker, direction=direction, alert_id=f"{ticker}{d}", score=0.0,
                       label="PURE", coverage=0.0, scores={}, available={}, r1=None, r5=None, r20=None, mfe20=None,
                       mae20=None, x5=x5, setup=setup, premium=premium,
                       opt_r5=normal, opt_r5_mid=mid if mid is not None else normal,
                       opt_r5_wide=wide if wide is not None else normal)


FIN = {"F1": ["long_only"], "F2": ["long_only"]}


def test_levels_stats_and_live_rule(monkeypatch):
    monkeypatch.setattr(costs.cb, "matches", lambda r, blocks: True)
    rows = [row(date(2025, 1, 2), f"T{i}", 0.10 if i % 2 else -0.05, mid=0.2, wide=-0.1) for i in range(40)]
    rows.append(row(date(2025, 1, 2), "NOPT", None))                              # no option history → not measured
    t = costs.cost_table(rows, FIN)
    f1 = t["F1"]
    assert f1["normal"]["n"] == 40 and f1["mid"]["n"] == 40 and f1["wide"]["n"] == 40
    assert f1["normal"]["win_rate"] == 0.5 and round(f1["normal"]["mean"], 4) == 0.025
    assert f1["normal"]["worst"] == -0.05 and f1["mid"]["mean"] == 0.2 and f1["wide"]["mean"] == -0.1
    assert f1["live_ok"] == "yes"                                                 # normal mean > 0, n ≥ 30


def test_live_rule_needs_30_and_positive_normal(monkeypatch):
    monkeypatch.setattr(costs.cb, "matches", lambda r, blocks: True)
    few = [row(date(2025, 1, 2), f"T{i}", 0.1) for i in range(10)]
    assert costs.cost_table(few, FIN)["F1"]["live_ok"] == "cost check unknown"
    bad = [row(date(2025, 1, 2), f"T{i}", -0.1, mid=0.5) for i in range(40)]
    assert costs.cost_table(bad, FIN)["F1"]["live_ok"] == "no"


def test_take_list_backtested_with_caps(monkeypatch):
    monkeypatch.setattr(costs.cb, "matches", lambda r, blocks: True)
    rows = [row(date(2025, 1, 2), f"T{i}", 0.1, premium=1e6 + i) for i in range(10)]   # 10 on one day
    rows += [row(date(2025, 1, 2), "T0", 0.1, premium=5e6)]                              # same stock, bigger
    taken = costs.take_rows(rows, FIN)
    assert len(taken) == 6                                                     # ≤ 3 per finalist × 2 finalists
    assert sum(r.ticker == "T0" for r in taken) == 1
    assert "Take list" in costs.cost_table(rows, FIN)


def test_non_setup_rows_excluded_and_render(monkeypatch):
    monkeypatch.setattr(costs.cb, "matches", lambda r, blocks: True)
    rows = [row(date(2025, 1, 2), "A", 0.1, setup=None), row(date(2025, 1, 2), "B", 0.2)]
    t = costs.cost_table(rows, FIN)
    assert t["F1"]["normal"]["n"] == 1
    md = costs.render(t, {"phase": "train", "start": "2024-10-01", "end": "2025-09-30"})
    assert "Mid" in md and "Normal" in md and "Wide" in md and "F1" in md and "closing" in md
