from datetime import datetime
from zoneinfo import ZoneInfo

from whaleproof.commands.backfill import in_quiet_hours
from whaleproof.config import load_settings

NY = ZoneInfo("America/New_York")


def test_budget_knobs_read_from_env(monkeypatch):
    monkeypatch.setenv("WHALEPROOF_DAILY_LIMIT", "40000")
    monkeypatch.setenv("WHALEPROOF_BACKFILL_RESERVE", "15000")
    monkeypatch.setenv("WHALEPROOF_BACKFILL_STOP", "06:30")
    s = load_settings()
    assert s.backfill_request_cap == 25000 and s.backfill_stop == "06:30"


def test_defaults(monkeypatch):
    for k in ("WHALEPROOF_DAILY_LIMIT", "WHALEPROOF_BACKFILL_RESERVE", "WHALEPROOF_BACKFILL_STOP"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setattr("whaleproof.config.load_dotenv", lambda *a, **k: None)
    s = load_settings()
    assert s.backfill_request_cap == 28000 and s.backfill_stop == "07:00"


def test_backfill_window():
    assert not in_quiet_hours(datetime(2026, 9, 28, 23, 0, tzinfo=NY), "07:00")   # night → run
    assert not in_quiet_hours(datetime(2026, 9, 29, 6, 59, tzinfo=NY), "07:00")
    assert in_quiet_hours(datetime(2026, 9, 29, 7, 0, tzinfo=NY), "07:00")         # day → stop
    assert in_quiet_hours(datetime(2026, 9, 29, 19, 59, tzinfo=NY), "07:00")
    assert not in_quiet_hours(datetime(2026, 9, 29, 20, 0, tzinfo=NY), "07:00")    # after reset → run
