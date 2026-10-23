"""Every-angle backtest report: buckets, official-like top-5, day-clustered stats, costs."""
from dataclasses import replace
from datetime import date, timedelta

from whaleproof.core.backtest.breakdowns import (
    bucket_dte, bucket_premium, bucket_rr, bucket_score, day_cluster, portfolio, top_n_per_day)
from whaleproof.core.backtest.runner import BacktestRow, render_report, summarize


def row(d, t, parity, x5, label="GO", **kw):
    base = BacktestRow(d, t, 1, t + str(d), parity, label, 1.0, {}, {}, None, x5, None, None, None,
                       x5=x5, plan_return=x5, score_parity=parity)
    return replace(base, **kw)


def test_buckets():
    assert bucket_rr(0.95) == "<1" and bucket_rr(1.2) == "1–1.5" and bucket_rr(1.7) == "1.5–2" and bucket_rr(3) == ">2"
    assert bucket_rr(None) == "n/a"
    assert bucket_score(72.5) == "70–75" and bucket_score(93) == "90+" and bucket_score(57) == "55–60"
    assert bucket_dte(10) == "≤14" and bucket_dte(30) == "15–45" and bucket_dte(60) == "46–90" and bucket_dte(200) == ">90"
    assert bucket_premium(150_000) == "$100K–250K" and bucket_premium(2e6) == "$1M–5M" and bucket_premium(9e6) == ">$5M"


def test_top_n_per_day_picks_best_go_by_parity():
    d = date(2025, 3, 3)
    rows = [row(d, "A", 80, .01), row(d, "B", 90, .02), row(d, "C", 95, .0, label="WATCH"),
            row(d, "D", 75, -.01), row(d + timedelta(1), "E", 71, .03)]
    top = top_n_per_day(rows, 2)
    assert [(r.session_date, r.ticker) for r in top] == [(d, "B"), (d, "A"), (d + timedelta(1), "E")]


def test_day_cluster_and_bootstrap_deterministic():
    d = date(2025, 3, 3)
    rows = [row(d, "A", 80, .02), row(d, "B", 80, .04), row(d + timedelta(1), "C", 80, -.01)]
    c1, c2 = day_cluster(rows, "x5"), day_cluster(rows, "x5")
    assert c1 == c2 and c1["n_days"] == 2 and abs(c1["mean_daily"] - 0.01) < 1e-12
    assert c1["boot_ci_low"] <= c1["mean_daily"] <= c1["boot_ci_high"]


def test_portfolio_drawdown():
    d = date(2025, 3, 3)
    rows = [row(d, "A", 80, .05), row(d + timedelta(1), "B", 80, -.10), row(d + timedelta(2), "C", 80, .02)]
    p = portfolio(rows, "plan_return", hold=5)
    assert p["n_cohorts"] == 3 and p["max_drawdown"] < 0


def test_summary_has_every_breakdown_and_report_renders(store):
    d = date(2025, 3, 3)
    rows = [row(d, "A", 80, .01, rr=1.7, dte=30, premium=2e6, iv_rank=20.0, sector="Technology",
                issue_type="Common Stock", catalyst="none", spy_trend=1)]
    s = summarize(rows, 0)
    for k in ("by_rr", "by_score", "by_dte", "by_premium", "by_ivr", "by_sector", "by_issue", "by_catalyst",
              "by_spy_trend", "by_weekday", "by_year", "official_like", "official_like_daily", "official_like_portfolio"):
        assert k in s, k
    md = render_report(s, {"start": "2025-03-03", "end": "2025-03-03", "weights": "v0.5"})
    assert "Reward : risk" in md and "low sample" in md and "Official-like" in md
