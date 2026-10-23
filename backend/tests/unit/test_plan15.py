"""Plan 1.5 — extra confluence: dark-pool blocks, ticker net premium, sector tide, insiders, next-morning OI."""
from dataclasses import replace
from datetime import date, datetime, timezone

from tests.conftest import raw_alert
from whaleproof.core.checks import ALL_CHECKS
from whaleproof.core.checks.confluence import dp_blocks, insider, oi_confirm, sector_flow, ticker_flow
from whaleproof.core.data_layer import ingest
from whaleproof.core.data_layer.context import AlertContext, build_context
from whaleproof.core.data_layer.models import alert_to_row, parse_alert
from whaleproof.core.verdict.weights import BACKTESTABLE, CURRENT, V0

AS_OF = datetime(2026, 9, 25, 20, 15, tzinfo=timezone.utc)
D = date(2026, 9, 25)


class Fake:
    def __init__(self, routes):
        self.routes, self.calls = routes, []

    def get(self, path, params=None):
        self.calls.append((path, dict(params or {})))
        for k, fn in self.routes.items():
            if k in path:
                return fn(params or {})
        return {"data": []}


def ctx(a, **kw):
    return replace(AlertContext(a, AS_OF, None, None, None, None, None, [], 0, None), **kw)


# ---------- ingest ----------
def test_dp_blocks_classified_by_nbbo_regular_hours_only(store):
    blocks = [
        {"price": "100.10", "nbbo_bid": "100.00", "nbbo_ask": "100.10", "premium": "2000000", "canceled": False,
         "ext_hour_sold_codes": None},                                     # at ask → buy
        {"price": "99.90", "nbbo_bid": "99.90", "nbbo_ask": "100.00", "premium": "500000", "canceled": False,
         "ext_hour_sold_codes": None},                                     # at bid → sell
        {"price": "100.05", "nbbo_bid": "100.00", "nbbo_ask": "100.10", "premium": "900000", "canceled": False,
         "ext_hour_sold_codes": None},                                     # mid → neutral
        {"price": "101", "nbbo_bid": "100", "nbbo_ask": "100.5", "premium": "9000000", "canceled": False,
         "ext_hour_sold_codes": "extended_hours_trade"},                   # after hours → ignored
        {"price": "101", "nbbo_bid": "100", "nbbo_ask": "100.5", "premium": "9000000", "canceled": True,
         "ext_hour_sold_codes": None},                                     # canceled → ignored
    ]
    ingest.ingest_dp_blocks(Fake({"/api/darkpool/X": lambda p: {"data": blocks}}), store, "X", D)
    assert store.get_metric("X", D, "dp_blocks") == {"buy": 2000000.0, "sell": 500000.0, "neutral": 900000.0, "n": 3}


def test_net_prem_sums_ticks(store):
    ticks = [{"net_call_premium": "100", "net_put_premium": "-50"}, {"net_call_premium": "300", "net_put_premium": "150"}]
    ingest.ingest_net_prem(Fake({"net-prem-ticks": lambda p: {"data": ticks}}), store, "X", D)
    assert store.get_metric("X", D, "net_prem") == {"call": 400.0, "put": 100.0, "gross": 600.0}


def test_sector_and_sector_tide(store):
    f = Fake({"/info": lambda p: {"data": {"sector": "Technology"}},
              "sector-tide": lambda p: {"data": [{"net_call_premium": "10", "net_put_premium": "5"},
                                                 {"net_call_premium": "90", "net_put_premium": "-30"}]}})
    assert ingest.ingest_sector(f, store, "X") == "Technology"
    ingest.ingest_sector(f, store, "X")
    assert sum(1 for c in f.calls if "/info" in c[0]) == 1           # sector cached per ticker
    ingest.ingest_sector_tide(f, store, "Technology", D)
    assert store.get_metric("SECTOR:Technology", D, "tide") == {"net": 120.0, "gross": 120.0}


def test_insider_history_stored(store):
    rows = [{"date": "2026-09-01", "buy_sell": "buy", "premium": "500000", "premium_10b5": "0"},
            {"date": "2026-08-01", "buy_sell": "sell", "premium": "-900000", "premium_10b5": "-900000"}]
    ingest.ingest_insider(Fake({"ticker-flow": lambda p: {"data": rows}}), store, "X", D)
    assert store.get_metric("X", "all", "insider") == [["2026-08-01", -900000.0, -900000.0],
                                                       ["2026-09-01", 500000.0, 0.0]]


def test_contract_oi_history(store):
    chains = {"chains": [{"date": "2026-09-28", "open_interest": 9000}, {"date": "2026-09-25", "open_interest": 1000}]}
    ingest.ingest_contract_oi(Fake({"/historic": lambda p: chains}), store, "X261016C00100000")
    assert store.get_metric("X261016C00100000", "2026-09-28", "oi") == 9000


# ---------- context (point-in-time) ----------
def test_context_new_fields_point_in_time(store):
    r = raw_alert(created_at="2026-09-25T15:00:00Z")
    a = parse_alert(r)
    store.upsert_alerts([alert_to_row(a, r)])
    store.put_metric("NVDA", D, "dp_blocks", {"buy": 1, "sell": 0, "neutral": 0, "n": 1})
    store.put_metric("NVDA", D, "net_prem", {"call": 5, "put": 1, "gross": 6})
    store.put_metric("NVDA", "all", "sector", "Technology")
    store.put_metric("SECTOR:Technology", D, "tide", {"net": 10, "gross": 20})
    store.put_metric("NVDA", "all", "insider", [["2026-09-24", 5.0, 0.0], ["2026-09-01", 7.0, 0.0]])
    store.put_metric(a.option_chain, D, "oi", 1500)
    store.put_metric(a.option_chain, "2026-09-28", "oi", 3500)
    c = build_context(store, a, AS_OF)
    assert c.dp_blocks["n"] == 1 and c.net_prem["call"] == 5 and c.sector_tide["net"] == 10
    assert c.insider == [(date(2026, 9, 1), 7.0, 0.0)]                 # 9/24 not yet filed (≤ D-3 only)
    assert c.oi_next is None                                           # not known at 16:15 on D
    nxt = build_context(store, a, datetime(2026, 9, 28, 12, 30, tzinfo=timezone.utc))  # 08:30 ET D+1
    assert nxt.oi_next == (1500, 3500)


# ---------- checks ----------
def test_dp_blocks_check(make_alert):
    a = make_alert()
    assert not dp_blocks(ctx(a)).available
    assert dp_blocks(ctx(a, dp_blocks={"buy": 3e6, "sell": 1e6, "neutral": 0, "n": 2})).score == 0.5
    bear = make_alert(type="put")
    assert dp_blocks(ctx(bear, dp_blocks={"buy": 3e6, "sell": 1e6, "neutral": 0, "n": 2})).score == -0.5


def test_ticker_flow_check(make_alert):
    a = make_alert()
    assert ticker_flow(ctx(a, net_prem={"call": 400.0, "put": 100.0, "gross": 600.0})).score == 0.5
    assert not ticker_flow(ctx(a)).available


def test_sector_flow_check(make_alert):
    assert sector_flow(ctx(make_alert(), sector_tide={"net": -50.0, "gross": 100.0})).score == -0.5


def test_insider_check(make_alert):
    a = make_alert()
    buys = insider(ctx(a, insider=[(date(2026, 8, 1), 500000.0, 0.0)]))
    assert buys.score > 0 and "bought" in buys.reason
    plan_sells = insider(ctx(a, insider=[(date(2026, 8, 1), -900000.0, -900000.0)]))
    assert plan_sells.score == 0                                       # 10b5-1 plan sales are noise
    assert insider(ctx(a, insider=[])).score == 0 and insider(ctx(a, insider=[])).available


def test_oi_confirm_check(make_alert):
    a = make_alert(total_size=2000)
    assert not oi_confirm(ctx(a)).available
    assert oi_confirm(ctx(a, oi_next=(1500, 3500))).score == 1.0        # +2000 ≥ size
    assert oi_confirm(ctx(a, oi_next=(1500, 1400))).score < 0            # closed, not opened


# ---------- weights ----------
def test_current_weights_cover_new_checks_and_sum_to_one():
    names = {f.__name__ for f in ALL_CHECKS}
    assert {"dp_blocks", "ticker_flow", "sector_flow", "insider", "oi_confirm"} <= names
    assert CURRENT.version == "v0.6" and abs(sum(CURRENT.w.values()) - 1) < 1e-9
    assert set(CURRENT.w) <= names and "oi_confirm" not in CURRENT.w   # confirmation is a pre-open stage
    assert {"dp_blocks", "ticker_flow", "sector_flow", "insider"} <= BACKTESTABLE
    assert set(V0.w) == {"flow_quality", "persistence", "gamma_room", "dark_pool", "vol_price",
                         "unusualness", "regime", "catalyst"}          # v0 unchanged


def test_live_sector_tides_keep_the_day_total_for_rotation(store):
    """The Market page's 'recent sessions' reads SECTOR:<s> tide rows; the live refresher must write them too."""
    from whaleproof.desk.live import sector_tides
    f = Fake({"sector-tide": lambda p: {"data": [{"net_call_premium": "90", "net_put_premium": "-30", "timestamp": "t"}]}})
    out = sector_tides(f, store, D, live=True)
    assert out and out[0]["net"] == 120.0
    assert store.get_metric("SECTOR:Technology", D, "tide") == {"net": 120.0, "gross": 120.0}
