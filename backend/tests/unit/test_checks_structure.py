from datetime import date, datetime, timezone

from whaleproof.core.checks import ALL_CHECKS
from whaleproof.core.checks.structure import (
    catalyst, dark_pool, gamma_room, regime, unusualness, vol_price)
from whaleproof.core.data_layer.context import AlertContext
from whaleproof.core.data_layer.models import GexLevels

AS_OF = datetime(2026, 9, 25, 20, 15, tzinfo=timezone.utc)


def ctx(alert, **over):
    base = dict(alert=alert, as_of=AS_OF, gex=None, dp_levels=None, iv_rank=None, unusual_pct=None,
                tide=None, earnings=[], same_dir_recent=0, ref_price=None)
    base.update(over)
    return AlertContext(**base)


def bull(make_alert):
    return make_alert(underlying_price="100", iv="0.5", strike="105", expiry="2026-10-16")  # EM ≈ 12


def test_all_checks_unavailable_without_data(make_alert):
    a = bull(make_alert)
    for fn in (gamma_room, dark_pool, vol_price, unusualness, regime):
        assert not fn(ctx(a)).available


def test_gamma_room(make_alert):
    a = bull(make_alert)
    far = gamma_room(ctx(a, gex=GexLevels(125, 90, 95, 100)))
    near = gamma_room(ctx(a, gex=GexLevels(101, 90, 95, 100)))
    assert far.score == 1.0 and near.score < -0.5
    neg = gamma_room(ctx(a, gex=GexLevels(125, 90, 110, 100)))   # spot below flip
    assert "negative gamma" in neg.reason
    bear = make_alert(type="put", underlying_price="100", iv="0.5", strike="95", expiry="2026-10-16")
    assert gamma_room(ctx(bear, gex=GexLevels(125, 75, 95, 100))).score == 1.0


def test_gamma_room_missing_wall_is_neutral(make_alert):
    r = gamma_room(ctx(bull(make_alert), gex=GexLevels(None, None, None, None)))
    assert r.available and r.score == 0


def test_dark_pool_support_below_spot_bullish(make_alert):
    a = bull(make_alert)
    r = dark_pool(ctx(a, dp_levels=[(98.0, 9000), (102.0, 1000), (150.0, 99999)]))
    assert r.score == 0.8
    assert dark_pool(ctx(a, dp_levels=[(150.0, 5)])).score == 0


def test_vol_price(make_alert):
    a = bull(make_alert)
    assert vol_price(ctx(a, iv_rank=10)).score == 1.0
    assert vol_price(ctx(a, iv_rank=90)).score == -1.0
    assert "spread" in vol_price(ctx(a, iv_rank=85)).reason


def test_unusualness(make_alert):
    assert unusualness(ctx(bull(make_alert), unusual_pct=95)).score == 1.0
    assert unusualness(ctx(bull(make_alert), unusual_pct=50)).score == 0


def test_regime_signed_by_direction(make_alert):
    a = bull(make_alert)
    assert regime(ctx(a, tide=1e9)).score == 1.0
    bear = make_alert(type="put")
    assert regime(ctx(bear, tide=1e9)).score == -1.0


def test_catalyst(make_alert):
    a = bull(make_alert)  # session 2026-09-25, expiry 2026-10-16
    assert catalyst(ctx(a, earnings=[date(2026, 11, 18)])).score > 0
    crush = catalyst(ctx(a, earnings=[date(2026, 10, 1)]))
    assert crush.score < 0 and "IV crush" in crush.reason
    event = catalyst(ctx(a, earnings=[date(2026, 10, 14)]))
    assert event.score == 0 and "event_trade" in event.tags


def test_registry_order():
    assert [f.__name__ for f in ALL_CHECKS] == [
        "flow_quality", "persistence", "gamma_room", "dark_pool", "vol_price",
        "unusualness", "regime", "catalyst", "liquidity", "chase_guard",
        "dp_blocks", "ticker_flow", "sector_flow", "insider", "oi_confirm", "uw_flagged",
        "skew", "option_sentiment", "iv_rv", "macro_event"]
