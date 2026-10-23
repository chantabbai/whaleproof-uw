from datetime import date

from whaleproof.desk.evidence import block_ci, funnel, summarize
from whaleproof.desk.history import HistRow


def row(d, x5, stage="gate", tier=None, sector="Tech"):
    return HistRow(d, "T", 1, 1e6, 0.1, 50, "fair", 30, sector, None, x5, x5, stage, "r", tier)


def test_summarize_trade_and_day_weighted():
    rs = [row(date(2025, 1, 2), 0.02), row(date(2025, 1, 2), 0.0), row(date(2025, 1, 3), -0.01)]
    s = summarize(rs)
    assert s["n"] == 3 and s["days"] == 2
    assert abs(s["mean"] - 0.01 / 3) < 1e-12
    assert abs(s["day_mean"] - (0.01 + -0.01) / 2) < 1e-12
    assert abs(s["win_rate"] - 1 / 3) < 1e-12
    assert abs(s["profit_factor"] - 2.0) < 1e-12


def test_summarize_empty():
    assert summarize([])["n"] == 0


def test_block_ci_brackets_mean_and_is_deterministic():
    vals = [0.01 * ((i % 7) - 3) for i in range(200)]
    lo, hi = block_ci(vals, seed=1)
    assert lo < sum(vals) / len(vals) < hi
    assert block_ci(vals, seed=1) == (lo, hi)


def test_funnel_counts_per_day():
    d = date(2025, 1, 2)
    rs = [row(d, 0.0), row(d, 0.0, "conviction"), row(d, 0.0, "signal", "whale")]
    f = funnel(rs, raw_counts={d: 40})
    assert f == {"days": 1, "raw": 40, "directional": 3, "clean": 2, "signals": 1,
                 "per_day": {"raw": 40.0, "directional": 3.0, "clean": 2.0, "signals": 1.0}}


def test_farotm_verdict_rules():
    from whaleproof.commands.evidence import farotm_verdict
    allr = {"n": 1000, "mean": -0.001}
    assert farotm_verdict({"n": 29, "mean": 0.05, "ci_low": 0.01}, allr) == "inconclusive"
    assert farotm_verdict({"n": 0, "days": 0}, allr) == "inconclusive"
    assert farotm_verdict({"n": 30, "mean": 0.01, "ci_low": 0.001}, allr) == "supports the far-OTM edge"
    assert farotm_verdict({"n": 30, "mean": 0.01, "ci_low": -0.001}, allr) == "does not support"
    assert farotm_verdict({"n": 30, "mean": -0.002, "ci_low": 0.001}, allr) == "does not support"


def test_preperiod_farotm_refuses_second_run(tmp_path, monkeypatch, capsys):
    import whaleproof.commands.evidence as ev
    out = tmp_path / "farotm.json"
    out.write_text("{}")
    monkeypatch.setattr(ev, "PRE_FAROTM_OUT", out)
    monkeypatch.setattr(ev, "Store", lambda *_: None)
    monkeypatch.setattr(ev, "raw_counts", lambda _: {})
    monkeypatch.setattr(ev, "earnings_map", lambda _: {})
    assert ev.main(["--preperiod-farotm"]) == 1
    assert out.read_text() == "{}" and "refusing" in capsys.readouterr().out
