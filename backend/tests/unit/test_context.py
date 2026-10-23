from datetime import date, datetime, timezone

from tests.conftest import raw_alert
from whaleproof.core.data_layer.context import AlertContext, build_context
from whaleproof.core.data_layer.models import alert_to_row, parse_alert

AS_OF = datetime(2026, 9, 25, 20, 15, tzinfo=timezone.utc)  # 16:15 ET


def _store_alert(store, **over):
    r = raw_alert(**over)
    a = parse_alert(r)
    store.upsert_alerts([alert_to_row(a, r)])
    return a


def test_uses_same_session_eod_and_ignores_future_metrics(store):
    a = _store_alert(store)
    store.put_metric("NVDA", date(2026, 9, 25), "gex", {"call_wall": 210, "put_wall": 180,
                                                        "gamma_flip": 188, "gamma_magnet": 200})
    store.put_metric("NVDA", date(2026, 9, 26), "gex", {"call_wall": 999, "put_wall": 1,
                                                        "gamma_flip": 1, "gamma_magnet": 1})
    store.put_metric("NVDA", date(2026, 9, 24), "iv_rank", 30.0)
    store.put_metric("NVDA", date(2026, 9, 28), "iv_rank", 99.0)
    ctx = build_context(store, a, AS_OF)
    assert ctx.gex.call_wall == 210
    assert ctx.iv_rank == 30.0


def test_persistence_counts_only_past_same_direction_alerts(store):
    a = _store_alert(store, id="main")
    _store_alert(store, id="same1", created_at="2026-09-24T15:00:00Z")          # prior session, bullish
    _store_alert(store, id="same2", created_at="2026-09-25T13:40:00Z")          # same day earlier
    _store_alert(store, id="opp", type="put", created_at="2026-09-25T13:41:00Z")  # bearish
    _store_alert(store, id="future", created_at="2026-09-25T21:00:00Z")         # after as_of
    _store_alert(store, id="old", created_at="2026-09-15T15:00:00Z")            # > 3 sessions back
    ctx = build_context(store, a, AS_OF)
    assert ctx.same_dir_recent == 2


def test_missing_data_is_none_not_zero(store):
    a = _store_alert(store)
    ctx = build_context(store, a, AS_OF)
    assert ctx.gex is None and ctx.dp_levels is None and ctx.iv_rank is None and ctx.tide is None
    assert ctx.earnings == []


def test_expected_move():
    a = parse_alert(raw_alert(iv="0.5", underlying_price="100", expiry="2026-10-16"))
    ctx = AlertContext(a, AS_OF, None, None, None, None, None, [], 0, None)
    assert round(ctx.expected_move, 2) == round(100 * 0.5 * (21 / 365) ** 0.5, 2)
    b = parse_alert(raw_alert(iv=None, underlying_price="100"))
    assert AlertContext(b, AS_OF, None, None, None, None, None, [], 0, None).expected_move == 5.0
