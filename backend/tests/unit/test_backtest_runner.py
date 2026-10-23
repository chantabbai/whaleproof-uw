from datetime import date, timedelta

from tests.conftest import raw_alert
from whaleproof.core.backtest.runner import render_report, run_backtest, summarize, summary_hash
from whaleproof.core.data_layer.models import Bar, alert_to_row, parse_alert


def seed(store):
    for i, (tkr, day, created) in enumerate([
        ("NVDA", "2026-09-22", "2026-09-22T15:00:00Z"),
        ("AMD", "2026-09-22", "2026-09-22T16:00:00Z"),
        ("GONE", "2026-09-22", "2026-09-22T17:00:00Z"),    # no OHLC → skipped
    ]):
        r = raw_alert(id=f"x{i}", ticker=tkr, created_at=created, expiry="2026-10-16")
        store.upsert_alerts([alert_to_row(parse_alert(r), r)])
    d0 = date(2026, 9, 22)
    for tkr, drift in (("NVDA", 1.0), ("AMD", -1.0)):
        store.put_ohlc(tkr, [Bar(d0 + timedelta(days=k), 190 + drift * k, 191 + drift * k,
                                 189 + drift * k, 190 + drift * k, 1) for k in range(40)])


def test_runs_and_skips_missing_prices(store):
    seed(store)
    rows, skipped = run_backtest(store, date(2026, 9, 22), date(2026, 9, 22))
    assert {r.ticker for r in rows} == {"NVDA", "AMD"} and skipped == 1
    nv = next(r for r in rows if r.ticker == "NVDA")
    assert nv.r5 > 0 and next(r for r in rows if r.ticker == "AMD").r5 < 0


def test_future_alerts_do_not_leak_into_past_rows(store):
    seed(store)
    before, _ = run_backtest(store, date(2026, 9, 22), date(2026, 9, 22))
    r = raw_alert(id="future", ticker="NVDA", created_at="2026-09-23T15:00:00Z", expiry="2026-10-16")
    store.upsert_alerts([alert_to_row(parse_alert(r), r)])
    after, _ = run_backtest(store, date(2026, 9, 22), date(2026, 9, 22))
    assert [x.scores for x in before] == [x.scores for x in after]


def test_summary_is_deterministic_and_renders(store):
    seed(store)
    rows, skipped = run_backtest(store, date(2026, 9, 22), date(2026, 9, 22))
    s1, s2 = summarize(rows, skipped), summarize(list(reversed(rows)), skipped)
    assert summary_hash(s1) == summary_hash(s2)
    assert s1["all"]["r5"]["n"] == 2 and s1["skipped"] == 1
    md = render_report(s1, {"start": "2026-09-22", "end": "2026-09-22", "weights": "v0"})
    assert "Not investment advice" in md and "| all |" in md and "excess of SPY" in md
    assert set(s1["by_direction"]) == {"bullish"}


def test_excess_return_and_plan_exit_present(store):
    seed(store)
    d0 = date(2026, 9, 22)
    store.put_ohlc("SPY", [Bar(d0 + timedelta(days=k), 500, 501, 499, 500 + 0.5 * k, 1) for k in range(40)])
    rows, _ = run_backtest(store, d0, d0)
    nv = next(r for r in rows if r.ticker == "NVDA")
    assert nv.x5 is not None and nv.x5 < nv.r5
    assert nv.plan_status in {"open", "target", "invalidated", "time_stop"}


# ---------- pure-directional gate + setups (pre-registration Amendment 3) ----------
def test_rows_carry_setup_or_gate_failure(store):
    seed(store)
    r = raw_alert(id="sold", ticker="NVDA", type="call", created_at="2026-09-22T18:00:00Z", expiry="2026-10-16",
                  total_ask_side_prem="50000", total_bid_side_prem="450000")    # sold call: bearish by old rule
    store.upsert_alerts([alert_to_row(parse_alert(r), r)])
    rows, _ = run_backtest(store, date(2026, 9, 22), date(2026, 9, 22))
    amd = next(x for x in rows if x.ticker == "AMD")
    assert amd.setup == "sweep" and amd.gate_fail is None                       # raw_alert: opening ask sweep
    sold = next(x for x in rows if x.alert_id == "sold")
    assert sold.setup is None and "not a buy" in sold.gate_fail


def test_setup_summary_expectancy_and_profit_factor():
    from whaleproof.core.backtest.runner import BacktestRow
    d = date(2026, 9, 22)

    def row(tkr, setup, r5, day=d):
        return BacktestRow(session_date=day, ticker=tkr, direction=1, alert_id=tkr, score=50, label="WATCH",
                           coverage=1, scores={}, available={}, r1=None, r5=r5, r20=None, mfe20=None, mae20=None,
                           x5=r5, setup=setup, gate_fail=None if setup else "multi-leg")
    rows = [row("A", "sweep", 0.04), row("B", "sweep", -0.01), row("C", "sweep", 0.02, d + timedelta(days=1)),
            row("N", None, -0.03)]
    s = summarize(rows, 0)
    sw = s["by_setup"]["sweep"]
    assert sw["n"] == 3 and abs(sw["profit_factor"] - 6.0) < 1e-9 and abs(sw["win_rate"] - 2 / 3) < 1e-9
    assert abs(sw["trades_per_day"] - 1.5) < 1e-9
    assert s["by_setup"]["noise"]["n"] == 1 and s["by_setup"]["pure_all"]["n"] == 3
    assert s["gate_fail_counts"] == {"multi-leg": 1}
    md = render_report(s, {"start": "a", "end": "b", "weights": "v0.5"})
    assert "## Setups" in md and "| sweep" in md and "| noise" in md


def test_rows_carry_em_and_stop_target_grid(store):
    """H6 (Amendment 7): fixed-level plan exits for stop ∈ {0.75,1,1.5}×EM × target ∈ {1.25,2}×EM."""
    from whaleproof.core.backtest.runner import GRID
    seed(store)
    rows, _ = run_backtest(store, date(2026, 9, 22), date(2026, 9, 22))
    nv = next(r for r in rows if r.ticker == "NVDA")                       # steady +1/day uptrend
    assert nv.em and nv.em > 0
    assert set(nv.grid) == {f"{s}x{t}" for s, t in GRID} and len(GRID) == 6
    assert all(v is not None for v in nv.grid.values())
    assert nv.grid["0.75x2.0"] >= nv.grid["0.75x1.25"] > 0                  # wider target keeps more of a trend


def test_gated_backtest_drops_gate_failures_before_the_cut(store):
    seed(store)
    r = raw_alert(id="sold", ticker="NVDA", type="call", created_at="2026-09-22T18:00:00Z", expiry="2026-10-16",
                  total_ask_side_prem="50000", total_bid_side_prem="450000")
    store.upsert_alerts([alert_to_row(parse_alert(r), r)])
    ungated, _ = run_backtest(store, date(2026, 9, 22), date(2026, 9, 22))
    gated, _ = run_backtest(store, date(2026, 9, 22), date(2026, 9, 22), gate=True)
    assert "sold" in {x.alert_id for x in ungated}
    assert {x.alert_id for x in gated} == {"x0", "x1"} and all(x.setup for x in gated)


# ---------- Amendment 13: day-1 rule comparison (current plan vs hold overnight) ----------
def test_rows_carry_overnight_variant(store):
    seed(store)
    rows, _ = run_backtest(store, date(2026, 9, 22), date(2026, 9, 22))
    nv = next(r for r in rows if r.ticker == "NVDA")
    assert nv.overnight_status in {"open", "target", "invalidated", "time_stop"}
    assert nv.plan_days is not None and nv.overnight_days is not None


def test_day1_compare_block():
    from whaleproof.core.backtest.runner import BacktestRow, day1_compare
    d = date(2026, 9, 22)

    def row(tkr, plan, pdays, ovn, odays, day=d):
        return BacktestRow(session_date=day, ticker=tkr, direction=1, alert_id=tkr, score=50, label="GO",
                           coverage=1, scores={}, available={}, r1=None, r5=None, r20=None, mfe20=None, mae20=None,
                           x5=None, score_parity=50, plan_return=plan, plan_days=pdays,
                           overnight_return=ovn, overnight_days=odays)
    rows = [row("A", -0.03, 1, 0.02, 3), row("B", 0.05, 2, 0.05, 2), row("C", -0.02, 1, -0.06, 1, d + timedelta(days=1))]
    c = day1_compare(rows)
    assert c["plan"]["n"] == 3 and abs(c["plan"]["day1_share"] - 2 / 3) < 1e-9
    assert abs(c["overnight"]["day1_share"] - 1 / 3) < 1e-9
    assert c["overnight"]["worst"] == -0.06 and c["plan"]["worst"] == -0.03
    assert set(c["plan"]) >= {"mean", "median", "max_drawdown", "total_return"}
