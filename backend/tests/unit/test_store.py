from datetime import date

from whaleproof.core.data_layer import fetch
from whaleproof.core.data_layer.models import Bar


def test_wal_mode(store):
    assert store.conn.execute("PRAGMA journal_mode").fetchone()[0] == "wal"


def test_cache_roundtrip_and_ttl(store, monkeypatch):
    store.cache_put("k", "/x", {"a": 1})
    assert store.cache_get("k", None) == {"a": 1}
    monkeypatch.setattr("whaleproof.core.data_layer.store.time.time", lambda: 10**12)
    assert store.cache_get("k", max_age_s=60) is None
    assert store.cache_get("k", max_age_s=None) == {"a": 1}


def test_alerts_upsert_dedupes_and_filters(store):
    a = {"id": "1", "ticker": "NVDA", "created_at": "2026-09-25T15:00:00Z", "session_date": "2026-09-25"}
    b = {"id": "2", "ticker": "AMD", "created_at": "2026-09-24T15:00:00Z", "session_date": "2026-09-24"}
    assert store.upsert_alerts([a, b, a]) == 2
    assert [r["id"] for r in store.alerts_between(date(2026, 9, 25), date(2026, 9, 25))] == ["1"]
    assert [r["id"] for r in store.alerts_between(date(2026, 9, 1), date(2026, 9, 30), "AMD")] == ["2"]


def test_latest_metric_is_point_in_time(store):
    store.put_metric("NVDA", date(2026, 9, 24), "gex", {"v": 24})
    store.put_metric("NVDA", date(2026, 9, 26), "gex", {"v": 26})
    d, p = store.latest_metric("NVDA", date(2026, 9, 25), "gex")
    assert d == date(2026, 9, 24) and p == {"v": 24}
    assert store.latest_metric("NVDA", date(2026, 9, 23), "gex") is None


def test_ohlc_roundtrip_sorted(store):
    store.put_ohlc("NVDA", [Bar(date(2026, 9, 25), 2, 3, 1, 2.5, 100), Bar(date(2026, 9, 24), 1, 2, 0.5, 1.5, 90)])
    bars = store.get_ohlc("NVDA", date(2026, 9, 1), date(2026, 9, 30))
    assert [b.date for b in bars] == [date(2026, 9, 24), date(2026, 9, 25)]


def test_cached_get_hits_cache_second_time(store):
    calls = []

    class FakeClient:
        def get(self, path, params=None):
            calls.append((path, params))
            return {"data": [{"x": 1}]}

    p1 = fetch.cached_get(FakeClient(), store, "/api/a", {"date": "2025-01-02"})
    p2 = fetch.cached_get(FakeClient(), store, "/api/a", {"date": "2025-01-02"})
    assert p1 == p2 and len(calls) == 1


def test_rows_normalizes_shapes():
    assert fetch.rows({"data": [{"a": 1}]}) == [{"a": 1}]
    assert fetch.rows({"data": {"a": 1}}) == [{"a": 1}]
    assert fetch.rows([{"a": 1}]) == [{"a": 1}]
    assert fetch.rows({"data": None}) == []
    assert fetch.rows({"a": 1}) == [{"a": 1}]
