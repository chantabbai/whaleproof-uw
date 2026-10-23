from datetime import date, datetime
from zoneinfo import ZoneInfo

from whaleproof import market_calendar as mc

NY = ZoneInfo("America/New_York")


def test_weekend_is_not_session():
    assert not mc.is_session(date(2026, 9, 27))  # Sunday
    assert mc.is_session(date(2026, 9, 28))      # Monday


def test_next_and_previous_session_skip_weekend():
    assert mc.next_session(date(2026, 9, 25)) == date(2026, 9, 28)
    assert mc.previous_session(date(2026, 9, 28)) == date(2026, 9, 25)


def test_sessions_range_inclusive():
    assert mc.sessions(date(2026, 9, 24), date(2026, 9, 28)) == [
        date(2026, 9, 24), date(2026, 9, 25), date(2026, 9, 28)]


def test_last_completed_session():
    # Sunday → Friday; Monday 10:00 (market open) → Friday; Monday 16:30 → Monday
    assert mc.last_completed_session(datetime(2026, 9, 27, 12, tzinfo=NY)) == date(2026, 9, 25)
    assert mc.last_completed_session(datetime(2026, 9, 28, 10, tzinfo=NY)) == date(2026, 9, 25)
    assert mc.last_completed_session(datetime(2026, 9, 28, 16, 30, tzinfo=NY)) == date(2026, 9, 28)


def test_early_close_day_after_thanksgiving():
    from datetime import date, time
    from whaleproof import market_calendar as mc
    assert mc.session_close(date(2025, 11, 28)).time() == time(13, 0)
    assert mc.session_close(date(2025, 11, 26)).time() == time(16, 0)


def test_market_state_labels():
    from datetime import datetime
    from whaleproof import market_calendar as mc
    at = lambda s: datetime.fromisoformat(s).replace(tzinfo=mc.NY)  # noqa: E731
    assert mc.market_state(at("2026-09-30T08:00:00"))["state"] == "pre"
    assert mc.market_state(at("2026-09-30T10:00:00"))["state"] == "open"
    assert mc.market_state(at("2026-09-30T17:00:00"))["state"] == "after"
    s = mc.market_state(at("2026-10-03T12:00:00"))          # Saturday
    assert s["state"] == "closed" and s["next_open"].startswith("2026-10-05T09:30")
    assert mc.market_state(at("2025-11-28T14:00:00"))["state"] == "after"   # early close 13:00
