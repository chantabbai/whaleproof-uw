from datetime import date

from tests.conftest import raw_alert
from whaleproof.core.data_layer import ingest


class FakeClient:
    def __init__(self, responses):
        self.responses = responses  # path -> callable(params) -> payload
        self.calls = []

    def get(self, path, params=None):
        self.calls.append((path, dict(params or {})))
        return self.responses[path](params or {})


def test_flow_day_paginates_until_short_page(store):
    page1 = [raw_alert(id=f"p1-{i}", created_at=f"2026-09-25T15:{i:02d}:00Z") for i in range(59, -1, -1)]
    page1 += [raw_alert(id=f"p1b-{i}", created_at="2026-09-25T14:59:00Z") for i in range(140)]
    page2 = [raw_alert(id="p2-0", created_at="2026-09-25T14:00:00Z")]
    pages = iter([{"data": page1}, {"data": page2}])
    c = FakeClient({"/api/option-trades/flow-alerts": lambda p: next(pages)})
    n = ingest.ingest_flow_day(c, store, date(2026, 9, 25))
    assert n == 201
    assert c.calls[0][1]["newer_than"] == "2026-09-25" and c.calls[0][1]["older_than"] == "2026-09-26"
    assert c.calls[1][1]["older_than"] != c.calls[0][1]["older_than"]


def test_flow_day_does_not_loop_when_page_shares_one_timestamp(store):
    same = [raw_alert(id=f"s{i}", created_at="2026-09-25T15:00:00Z") for i in range(200)]
    responses = iter([{"data": same}, {"data": same}, {"data": []}])
    c = FakeClient({"/api/option-trades/flow-alerts": lambda p: next(responses)})
    ingest.ingest_flow_day(c, store, date(2026, 9, 25))
    assert len(c.calls) <= 3
    olders = [call[1]["older_than"] for call in c.calls]
    assert len(set(olders)) == len(olders)  # cursor always moves


def test_flow_day_stops_on_full_page_of_unparseable_rows(store):
    junk = [{"id": f"j{i}"} for i in range(200)]
    c = FakeClient({"/api/option-trades/flow-alerts": lambda p: {"data": junk}})
    assert ingest.ingest_flow_day(c, store, date(2026, 9, 25)) == 0
    assert len(c.calls) == 1


def test_eod_stores_gex_and_dp(store):
    c = FakeClient({
        "/api/stock/NVDA/gex-levels": lambda p: {"data": {"call_wall": "210", "put_wall": "180",
                                                          "gamma_flip": "188", "gamma_magnet": "200"}},
        "/api/darkpool/NVDA/price-levels": lambda p: {"data": [
            {"price": "189.5", "dark_pool_volume": 1000, "regular_volume": 5},
            {"price": "191", "dark_pool_volume": 300, "regular_volume": 5}], "date": "2026-09-25"},
    })
    ingest.ingest_eod(c, store, "NVDA", date(2026, 9, 25))
    assert store.get_metric("NVDA", date(2026, 9, 25), "gex")["call_wall"] == 210.0
    assert store.get_metric("NVDA", date(2026, 9, 25), "dp_levels") == [[189.5, 1000], [191.0, 300]]


def test_market_tide_uses_last_row(store):
    c = FakeClient({"/api/market/market-tide": lambda p: {"data": [
        {"net_call_premium": "100", "net_put_premium": "50", "timestamp": "t1"},
        {"net_call_premium": "900", "net_put_premium": "100", "timestamp": "t2"}]}})
    ingest.ingest_market(c, store, date(2026, 9, 25))
    assert store.get_metric("MARKET", date(2026, 9, 25), "tide") == 800.0


def test_series_iv_ohlc_earnings(store):
    def ivr(p):
        if p.get("date"):  # older year window
            return {"data": [{"date": "2025-09-24", "iv_rank_1y": "0.8"}]}
        return {"data": [{"date": "2026-09-24", "iv_rank_1y": "35.5"}, {"date": "2026-09-25", "iv_rank_1y": None}]}
    c = FakeClient({
        "/api/stock/NVDA/iv-rank": ivr,
        "/api/stock/NVDA/ohlc/1d": lambda p: {"data": [
            {"date": "2026-09-25", "open": "1", "high": "2", "low": "0.5", "close": "1.5",
             "total_volume": 10, "volume": 12, "market_time": "r"},
            {"date": "2026-09-25", "open": "9", "high": "9", "low": "9", "close": "9",
             "total_volume": 1, "volume": 1, "market_time": "po"}]},
        "/api/earnings/NVDA": lambda p: {"data": [{"report_date": "2026-11-18"}, {"report_date": "2026-08-26"}]},
    })
    ingest.ingest_series(c, store, "NVDA", date(2026, 9, 27))
    assert store.get_metric("NVDA", date(2026, 9, 24), "iv_rank") == 35.5
    assert store.get_metric("NVDA", date(2025, 9, 24), "iv_rank") == 0.8
    assert store.get_metric("NVDA", date(2026, 9, 25), "iv_rank") is None
    bars = store.get_ohlc("NVDA", date(2026, 9, 1), date(2026, 9, 30))
    assert len(bars) == 1 and bars[0].close == 1.5
    assert store.get_metric("NVDA", "all", "earnings") == ["2026-08-26", "2026-11-18"]
    n = len(c.calls)
    ingest.ingest_series(c, store, "NVDA", date(2026, 9, 27))
    assert len(c.calls) == n  # second call same day is a no-op
