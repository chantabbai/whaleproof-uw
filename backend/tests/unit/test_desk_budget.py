"""Budget governor: stretch live refresh intervals when the projected spend to the 20:00 ET reset would eat the reserve."""
from datetime import datetime

from whaleproof import market_calendar as mc
from whaleproof.desk.budget import BurnMeter, pace_factor

AT = datetime(2026, 9, 30, 10, 0, tzinfo=mc.NY)


def test_full_speed_when_budget_is_ample():
    assert pace_factor(used=9_000, limit=40_000, burn_per_min=30, now=AT) == 1.0


def test_slows_when_projection_exceeds_budget():
    f = pace_factor(used=30_000, limit=40_000, burn_per_min=60, now=AT)      # 8.5K left, 360 min to close × 60 = 21.6K
    assert f > 2


def test_stops_when_reserve_reached():
    assert pace_factor(used=38_600, limit=40_000, burn_per_min=10, now=AT) == float("inf")


def test_burn_meter_rate_from_header_counts():
    m = BurnMeter()
    m.add(datetime(2026, 9, 30, 10, 0, tzinfo=mc.NY), 9_000)
    m.add(datetime(2026, 9, 30, 10, 10, tzinfo=mc.NY), 9_300)
    assert m.per_min() == 30


def test_live_window_eod_mode():
    from whaleproof.desk.budget import live_allowed
    at = lambda hm: datetime(2026, 9, 30, *hm, tzinfo=mc.NY)  # noqa: E731
    assert live_allowed(at((11, 0)), "eod") is False
    assert live_allowed(at((15, 30)), "eod") is True
    assert live_allowed(at((16, 59)), "eod") is True
    assert live_allowed(at((17, 1)), "eod") is False
    assert live_allowed(at((11, 0)), "full") is True
    assert live_allowed(datetime(2026, 10, 3, 16, 0, tzinfo=mc.NY), "eod") is False     # Saturday


def test_last_usage_kept_only_within_budget_day(store):
    from whaleproof.desk.budget import load_usage, save_usage
    save_usage(store, 34_095, datetime(2026, 9, 30, 19, 27, tzinfo=mc.NY))
    assert load_usage(store, datetime(2026, 9, 30, 19, 50, tzinfo=mc.NY))["count"] == 34_095
    assert load_usage(store, datetime(2026, 9, 30, 20, 5, tzinfo=mc.NY)) is None        # reset at 20:00 → stale


def test_desk_tally_counts_own_calls_per_budget_day_and_survives_restart(store):
    from whaleproof.desk.budget import DeskTally
    t = DeskTally(store, datetime(2026, 10, 9, 10, 0, tzinfo=mc.NY))
    assert t.update(datetime(2026, 10, 9, 10, 1, tzinfo=mc.NY), 40) == 40
    assert t.update(datetime(2026, 10, 9, 11, 0, tzinfo=mc.NY), 100) == 100
    again = DeskTally(store, datetime(2026, 10, 9, 12, 0, tzinfo=mc.NY))   # restart: client count starts at 0
    assert again.update(datetime(2026, 10, 9, 12, 1, tzinfo=mc.NY), 5) == 105
    assert again.update(datetime(2026, 10, 9, 20, 1, tzinfo=mc.NY), 8) == 3    # 20:00 ET reset → new budget day
    assert DeskTally(store, datetime(2026, 10, 10, 9, 0, tzinfo=mc.NY)).update(
        datetime(2026, 10, 10, 9, 0, tzinfo=mc.NY), 0) == 3
