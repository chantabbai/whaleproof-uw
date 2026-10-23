"""Plan 1.5 wiring: backfill/scan ingest new inputs, backtest OI-confirmation stats, pre-open confirm stage."""
from datetime import date, datetime, timedelta, timezone

from tests.conftest import raw_alert
from whaleproof.core.data_layer.models import Bar, alert_to_row, parse_alert
from whaleproof.core.journal.chain import append_pick, read_picks, verify_chain

D = date(2026, 9, 22)


def _seed_alert(store, **kw):
    r = raw_alert(created_at="2026-09-22T15:00:00Z", expiry="2026-10-16", **kw)
    a = parse_alert(r)
    store.upsert_alerts([alert_to_row(a, r)])
    return a


def test_backfill_ingests_plan15_inputs(store, monkeypatch):
    from whaleproof.commands import backfill as bf
    _seed_alert(store)
    seen = []
    for name in ("ingest_flow_day", "ingest_market", "ingest_series", "ingest_eod", "ingest_dp_blocks",
                 "ingest_net_prem", "ingest_insider", "ingest_contract_oi", "ingest_sector_tide"):
        monkeypatch.setattr(bf, name, lambda *a, _n=name, **k: seen.append(_n) or 0)
    monkeypatch.setattr(bf, "ingest_sector", lambda *a, **k: seen.append("ingest_sector") or "Technology")
    bf.backfill(object(), store, D, D, today=date(2026, 9, 27))
    for n in ("ingest_dp_blocks", "ingest_net_prem", "ingest_insider", "ingest_contract_oi",
              "ingest_sector", "ingest_sector_tide"):
        assert n in seen, n


def test_backtest_reports_oi_confirmation(store):
    from whaleproof.core.backtest.runner import run_backtest, summarize
    a = _seed_alert(store, total_size=2000)
    store.put_ohlc("NVDA", [Bar(D + timedelta(days=k), 190, 191, 189, 190 + k, 1) for k in range(30)])
    store.put_metric(a.option_chain, D, "oi", 1000)
    store.put_metric(a.option_chain, date(2026, 9, 23), "oi", 3000)
    rows, _ = run_backtest(store, D, D)
    assert rows[0].oi_ratio == 1.0
    assert rows[0].available["oi_confirm"] is False            # decision itself never sees next-day OI
    assert "oi_confirmed" in summarize(rows, 0)


def test_confirm_appends_preopen_record_once(store, tmp_path):
    from whaleproof.commands.confirm import confirm_picks
    a = _seed_alert(store, total_size=2000)
    j = tmp_path / "picks.jsonl"
    append_pick(j, {"pick_id": "p1", "kind": "official", "session_date": "2026-09-22", "entry_session": "2026-09-23",
                    "ticker": "NVDA", "direction": 1, "contract": a.option_chain, "source_alert_id": a.id})
    store.put_metric(a.option_chain, D, "oi", 1000)
    store.put_metric(a.option_chain, date(2026, 9, 23), "oi", 2600)
    now = datetime(2026, 9, 23, 12, 30, tzinfo=timezone.utc)   # 08:30 ET
    out = confirm_picks(None, store, j, now, fetch=False)
    assert out[0]["status"] == "confirmed" and out[0]["ratio"] == 0.8
    confirm_picks(None, store, j, now, fetch=False)
    recs = read_picks(j)
    assert [r["kind"] for r in recs] == ["official", "confirmation"] and verify_chain(j)


def test_confirm_refuses_after_open(store, tmp_path):
    from whaleproof.commands.confirm import confirm_picks
    a = _seed_alert(store)
    j = tmp_path / "picks.jsonl"
    append_pick(j, {"pick_id": "p1", "kind": "official", "session_date": "2026-09-22", "entry_session": "2026-09-23",
                    "ticker": "NVDA", "direction": 1, "contract": a.option_chain, "source_alert_id": a.id})
    assert confirm_picks(None, store, j, datetime(2026, 9, 23, 14, 0, tzinfo=timezone.utc), fetch=False) == []


def test_tracker_ignores_confirmation_records():
    from whaleproof.core.journal.tracker import tradable
    recs = [{"kind": "official"}, {"kind": "confirmation"}, {"kind": "intraday"}]
    assert [r["kind"] for r in tradable(recs)] == ["official", "intraday"]


def test_scheduler_has_preopen_confirm_job():
    from whaleproof.scheduler.runner import build_scheduler
    jobs = {j.id: j for j in build_scheduler(run=lambda *a: None, commit=lambda l: None).get_jobs()}
    t = str(jobs["confirm"].trigger)
    assert "hour='8'" in t and "minute='30'" in t


def test_pick_record_has_source_alert_id(make_alert):
    from whaleproof.core.data_layer.context import AlertContext
    from whaleproof.core.verdict.scan import pick_record
    from whaleproof.core.verdict.verdict import evaluate
    a = make_alert()
    rec = pick_record(evaluate(AlertContext(a, datetime(2026, 9, 25, 20, 15, tzinfo=timezone.utc),
                                            None, None, None, None, None, [], 0, None)), "official")
    assert rec["source_alert_id"] == a.id


def test_confirm_falls_back_to_contract_for_legacy_picks(store, tmp_path):
    from whaleproof.commands.confirm import confirm_picks
    a = _seed_alert(store, total_size=2000)
    j = tmp_path / "picks.jsonl"
    append_pick(j, {"pick_id": "old", "kind": "official", "session_date": "2026-09-22", "entry_session": "2026-09-23",
                    "ticker": "NVDA", "direction": 1, "contract": a.option_chain})   # v0 pick: no source_alert_id
    store.put_metric(a.option_chain, D, "oi", 1000)
    store.put_metric(a.option_chain, date(2026, 9, 23), "oi", 3000)
    out = confirm_picks(None, store, j, datetime(2026, 9, 23, 12, 30, tzinfo=timezone.utc), fetch=False)
    assert out and out[0]["status"] == "confirmed"
