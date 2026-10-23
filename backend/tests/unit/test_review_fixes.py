"""Regression tests for the whole-branch review findings (#1–#8)."""
from dataclasses import replace
from datetime import date, datetime, timezone

import pytest

from tests.conftest import raw_alert
from whaleproof.core.checks.flow import flow_quality, liquidity
from whaleproof.core.data_layer import ingest
from whaleproof.core.data_layer.context import AlertContext
from whaleproof.core.data_layer.models import GexLevels, num, parse_alert
from whaleproof.core.journal.chain import append_pick, read_picks, verify_chain
from whaleproof.core.verdict.verdict import evaluate

AS_OF = datetime(2026, 9, 25, 20, 15, tzinfo=timezone.utc)


# 1 — append after a truncated line must repair, not silently orphan later picks
def test_append_after_truncation_repairs_chain(tmp_path):
    p = tmp_path / "picks.jsonl"
    append_pick(p, {"pick_id": "1"})
    append_pick(p, {"pick_id": "2"})
    with p.open("a") as f:
        f.write('{"pick_id": "3", "trunc')
    append_pick(p, {"pick_id": "4"})
    assert [r["pick_id"] for r in read_picks(p)] == ["1", "2", "4"]
    assert verify_chain(p)


def test_append_refuses_tampered_chain(tmp_path):
    p = tmp_path / "picks.jsonl"
    append_pick(p, {"pick_id": "1", "ticker": "NVDA"})
    p.write_text(p.read_text().replace("NVDA", "TSLA"))
    with pytest.raises(ValueError):
        append_pick(p, {"pick_id": "2"})


# 2 — server ignoring the ms cursor must not spin forever
def test_pagination_stops_when_cursor_cannot_decrease(store):
    same = {"data": [raw_alert(id=f"s{i}", created_at="2026-09-25T15:00:00Z") for i in range(200)]}
    calls = []

    class C:
        def get(self, path, params=None):
            calls.append(params["older_than"])
            if len(calls) > 50:
                raise AssertionError("pagination loop")
            return same

    ingest.ingest_flow_day(C(), store, date(2026, 9, 25))
    assert len(calls) <= 3


# 8 — missing size/OI/volume stay None; not "opening", not a liquidity hard-fail
def test_missing_counts_are_none_not_zero():
    a = parse_alert(raw_alert(open_interest=None, volume=None, total_size=None,
                              all_opening_trades=False, volume_oi_ratio=None))
    assert a.open_interest is None and a.volume is None and a.total_size is None
    c = AlertContext(a, AS_OF, None, None, None, None, None, [], 0, None)
    assert "not clearly opening" in flow_quality(c).reason
    liq = liquidity(c)
    assert not liq.hard_fail and not liq.available


def test_num_rejects_non_finite():
    assert num("nan") is None and num("inf") is None


def test_dp_volume_float_string_does_not_crash(store):
    class C:
        def get(self, path, params=None):
            if "gex" in path:
                return {"data": {}}
            return {"data": [{"price": "10", "dark_pool_volume": "123.0"}]}
    ingest.ingest_eod(C(), store, "X", date(2026, 9, 25))
    assert store.get_metric("X", date(2026, 9, 25), "dp_levels") == [[10.0, 123]]


# 4 — GO label must not depend on live-only checks (unusualness)
def test_label_ignores_live_only_unusualness(make_alert):
    a = make_alert(total_premium="2000000", total_ask_side_prem="1950000", total_bid_side_prem="50000",
                   underlying_price="100", strike="105", iv="0.5", expiry="2026-10-16")
    base = AlertContext(a, AS_OF, GexLevels(125, 90, 95, 100), [(98.0, 9000)], 50, None, -6e8, [], 1, 100.5)
    hi = evaluate(replace(base, unusual_pct=99))
    lo = evaluate(replace(base, unusual_pct=1))
    assert hi.label == lo.label and hi.score_parity == lo.score_parity


# 3 — official picks only for the last completed session, and only before the next open
def test_official_window():
    from zoneinfo import ZoneInfo
    from whaleproof.commands.scan import official_allowed
    ny = ZoneInfo("America/New_York")
    fri = date(2026, 9, 25)
    assert official_allowed(fri, datetime(2026, 9, 27, 18, 0, tzinfo=ny))        # Sunday evening
    assert official_allowed(fri, datetime(2026, 9, 28, 9, 0, tzinfo=ny))         # Monday pre-open
    assert not official_allowed(fri, datetime(2026, 9, 28, 9, 45, tzinfo=ny))    # after Monday open
    assert not official_allowed(date(2026, 9, 24), datetime(2026, 9, 27, 18, 0, tzinfo=ny))  # backdated


def test_scheduler_official_job_tolerates_short_misfire():
    from whaleproof.scheduler.runner import build_scheduler
    job = {j.id: j for j in build_scheduler(run=lambda *a: None, commit=lambda l: None).get_jobs()}["official_scan"]
    assert job.misfire_grace_time >= 3600 and job.coalesce


# 5 — backfill must pick candidates with the same as_of filter as the backtest
def test_backfill_ignores_after_hours_alerts_for_candidates(store, monkeypatch):
    from whaleproof.commands import backfill as bf
    from whaleproof.core.data_layer.models import alert_to_row
    early = raw_alert(id="e", ticker="AAA", created_at="2026-09-25T15:00:00Z", total_premium="200000",
                      total_ask_side_prem="190000", total_bid_side_prem="0")
    late = raw_alert(id="l", ticker="ZZZ", created_at="2026-09-25T23:00:00Z", total_premium="9000000",
                     total_ask_side_prem="8900000", total_bid_side_prem="0")  # 19:00 ET, after as_of
    store.upsert_alerts([alert_to_row(parse_alert(r), r) for r in (early, late)])
    fetched = []
    monkeypatch.setattr(bf, "ingest_flow_day", lambda *a, **k: 0)
    monkeypatch.setattr(bf, "ingest_market", lambda *a, **k: None)
    monkeypatch.setattr(bf, "ingest_series", lambda c, s, t, today: None)  # SPY baseline
    monkeypatch.setattr(bf, "ingest_candidate", lambda c, s, a, d, today, live: fetched.append(a.ticker))
    bf.backfill(object(), store, date(2026, 9, 25), date(2026, 9, 25), today=date(2026, 9, 27))
    assert fetched == ["AAA"]


def test_backtest_never_uses_live_only_unusualness(store):
    from datetime import timedelta
    from whaleproof.core.backtest.runner import run_backtest
    from whaleproof.core.data_layer.models import Bar, alert_to_row
    r = raw_alert(id="u", created_at="2026-09-22T15:00:00Z", expiry="2026-10-16")
    store.upsert_alerts([alert_to_row(parse_alert(r), r)])
    d0 = date(2026, 9, 22)
    store.put_ohlc("NVDA", [Bar(d0 + timedelta(days=k), 190, 191, 189, 190, 1) for k in range(30)])
    store.put_metric("NVDA", d0, "unusual_opt_pct", 99.0)
    rows, _ = run_backtest(store, d0, d0)
    assert rows[0].available["unusualness"] is False


# 6 — stale cached series without session D's bar is refetched
def test_ensure_day_bar_refetches_when_bar_missing(store):
    state = {"fresh": False}

    class C:
        def get(self, path, params=None):
            if "ohlc" in path:
                rows = [{"date": "2026-09-24", "open": 1, "high": 1, "low": 1, "close": 1, "market_time": "r"}]
                if state["fresh"]:
                    rows.append({"date": "2026-09-25", "open": 2, "high": 2, "low": 2, "close": 2.5, "market_time": "r"})
                return {"data": rows}
            return {"data": []}

    ingest.ingest_series(C(), store, "NVDA", date(2026, 9, 25))   # morning: no D bar yet, checkpointed
    state["fresh"] = True
    assert ingest.ensure_day_bar(C(), store, "NVDA", date(2026, 9, 25)) == 2.5


# 7 — fit's GO hit-rate honours confidence and hard fails
def test_go_hit_respects_hard_fail_and_confidence():
    from whaleproof.core.backtest.fit import _go_hit
    from whaleproof.core.backtest.runner import BacktestRow
    w = {"flow_quality": 1.0}
    good = BacktestRow(date(2026, 1, 2), "T", 1, "g", 0, "", 1, {"flow_quality": 1.0}, {"flow_quality": True},
                       None, 0.01, None, None, None, confidences={"flow_quality": 1.0}, hard_fail=False)
    failed = replace(good, alert_id="f", r5=-0.01, hard_fail=True)
    lowconf = replace(good, alert_id="c", r5=-0.01, confidences={"flow_quality": 0.3})  # 50+50*.3 = 65 → not GO
    assert _go_hit([good, failed, lowconf], w) == 1.0
