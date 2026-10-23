"""Plan 2a: scan snapshots, intraday feed, tracker entry-price picks, new API endpoints."""
import json
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient

from tests.conftest import raw_alert
from whaleproof.core.data_layer.models import Bar, alert_to_row, parse_alert
from whaleproof.core.journal.tracker import evaluate_pick

NY = ZoneInfo("America/New_York")


def test_store_scan_snapshots_latest_by_kind(store):
    store.put_scan("2026-09-25", "official", "2026-09-25T20:30:00Z", "v0.5", [{"ticker": "A"}])
    store.put_scan("2026-09-28", "official", "2026-09-28T20:30:00Z", "v0.5", [{"ticker": "B"}])
    store.put_scan("2026-09-28", "intraday", "2026-09-28T15:00:00Z", "v0.5", [{"ticker": "C"}])
    s = store.latest_scan("official")
    assert s["session_date"] == "2026-09-28" and s["rows"] == [{"ticker": "B"}]
    assert store.latest_scan("intraday")["rows"][0]["ticker"] == "C"
    assert store.latest_scan("nope") is None


def test_intraday_window():
    from whaleproof.core.verdict.intraday import in_intraday_window
    assert in_intraday_window(datetime(2026, 9, 28, 9, 45, tzinfo=NY))
    assert in_intraday_window(datetime(2026, 9, 28, 15, 30, tzinfo=NY))
    assert not in_intraday_window(datetime(2026, 9, 28, 9, 40, tzinfo=NY))
    assert not in_intraday_window(datetime(2026, 9, 28, 15, 50, tzinfo=NY))
    assert not in_intraday_window(datetime(2026, 9, 27, 11, 0, tzinfo=NY))   # Sunday


def test_intraday_scan_uses_only_alerts_before_now_and_latest_price(store, monkeypatch):
    from whaleproof.core.verdict import intraday
    for rid, t, px in (("a1", "2026-09-28T14:00:00Z", "190"), ("a2", "2026-09-28T15:00:00Z", "195"),
                       ("late", "2026-09-28T17:00:00Z", "199")):
        r = raw_alert(id=rid, created_at=t, underlying_price=px, expiry="2026-10-16")
        store.upsert_alerts([alert_to_row(parse_alert(r), r)])
    monkeypatch.setattr(intraday, "ingest_flow_day", lambda *a, **k: 0)
    monkeypatch.setattr(intraday, "ingest_market", lambda *a, **k: None)
    monkeypatch.setattr(intraday, "ingest_candidate", lambda *a, **k: None)
    now = datetime(2026, 9, 28, 11, 30, tzinfo=NY)   # 15:30Z → a1, a2 visible, 'late' not
    vs = intraday.run_intraday(object(), store, now, max_candidates=20)
    assert len(vs) == 1 and vs[0].plan.entry_ref == 195.0


def test_intraday_pick_record_enters_same_session_at_scan_price(make_alert):
    from whaleproof.core.data_layer.context import AlertContext
    from whaleproof.core.verdict.scan import pick_record
    from whaleproof.core.verdict.verdict import evaluate
    a = make_alert(created_at="2026-09-28T14:00:00Z")
    v = evaluate(AlertContext(a, datetime(2026, 9, 28, 15, 30, tzinfo=timezone.utc), None, None, None, None, None,
                              [], 0, 191.0))
    rec = pick_record(v, "intraday")
    assert rec["entry_session"] == "2026-09-28" and rec["entry_price"] == 191.0


def test_tracker_entry_price_pick_marks_day0_close_then_exits_later():
    pick = {"pick_id": "i", "direction": 1, "session_date": "2026-09-28", "entry_session": "2026-09-28",
            "entry_price": 100.0, "weights_version": "v0.5", "kind": "intraday",
            "plan": {"invalidation": 95.0, "target": 110.0, "time_stop_sessions": 10}}
    d = date(2026, 9, 28)
    day0 = [Bar(d, 90, 111, 89, 102, 1)]              # pre-scan range must NOT trigger exits
    r = evaluate_pick(pick, day0)
    assert r["status"] == "open" and round(r["return"], 3) == 0.02
    r2 = evaluate_pick(pick, day0 + [Bar(d + timedelta(1), 103, 111, 102, 108, 1)])
    assert r2["status"] == "target" and round(r2["return"], 3) == 0.1


def _app(tmp_path, store_path):
    from whaleproof.api.app import create_app
    return TestClient(create_app(journal_path=tmp_path / "j.jsonl", db_path=store_path, log_path=tmp_path / "l.log",
                                 backtest_path=tmp_path / "bt.json"))


def test_api_tomorrow_and_intraday(tmp_path):
    from whaleproof.core.data_layer.store import Store
    db = tmp_path / "db.sqlite"
    st = Store(db)
    rows = [{"ticker": "A", "label": "GO", "score_parity": 80}, {"ticker": "B", "label": "WATCH", "score_parity": 66},
            {"ticker": "C", "label": "SKIP", "score_parity": 40}]
    st.put_scan("2026-09-28", "official", "2026-09-28T20:30:00Z", "v0.5", rows)
    st.put_scan("2026-09-28", "intraday", "2026-09-28T15:00:00Z", "v0.5", rows[:1])
    c = _app(tmp_path, db)
    t = c.get("/api/tomorrow").json()
    assert t["session_date"] == "2026-09-28" and [r["ticker"] for r in t["watch"]] == ["B"]
    assert [r["ticker"] for r in t["go"]] == ["A"]
    i = c.get("/api/intraday").json()
    assert i["scanned_at"] == "2026-09-28T15:00:00Z" and i["go"][0]["ticker"] == "A"


def test_api_backtest_summary(tmp_path):
    (tmp_path / "bt.json").write_text(json.dumps({"meta": {"weights": "v0.5"}, "summary": {"n_sessions": 3}}))
    c = _app(tmp_path, tmp_path / "db.sqlite")
    assert c.get("/api/backtest").json()["meta"]["weights"] == "v0.5"
    (tmp_path / "bt.json").unlink()
    assert c.get("/api/backtest").json() == {"meta": None, "summary": None}
