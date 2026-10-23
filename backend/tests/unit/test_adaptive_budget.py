from datetime import date, datetime
from zoneinfo import ZoneInfo

from whaleproof.core.budget import live_reserve, next_reset

NY = ZoneInfo("America/New_York")
T = lambda d, h, m=0: datetime(2026, 9, d, h, m, tzinfo=NY)  # noqa: E731


def test_next_reset():
    assert next_reset(T(28, 19, 0)) == T(28, 20, 0)
    assert next_reset(T(28, 20, 0)) == T(29, 20, 0)


def test_reserve_weekday_morning_covers_whole_day():
    # Mon 07:00 → before reset at 20:00: confirm 100 + 24 intraday × 150 + live option marks 2 × 1200
    # + official 700 + track 100 + safety 1500
    assert live_reserve(T(28, 7, 0)) == 100 + 24 * 150 + 3 * 1200 + 700 + 100 + 1500


def test_reserve_shrinks_through_the_day():
    assert live_reserve(T(28, 15, 20)) == 1 * 150 + 1200 + 700 + 100 + 1500  # 15:30 intraday + 15:55 marks left
    assert live_reserve(T(28, 17, 30)) == 1500                               # all live jobs done
    assert live_reserve(T(28, 20, 30)) == 100 + 24 * 150 + 3 * 1200 + 700 + 100 + 1500  # new window: Tuesday


def test_reserve_weekend_is_just_safety():
    assert live_reserve(T(27, 12, 0)) == 1500                                # Sunday
    assert live_reserve(T(26, 21, 0)) == 1500                                # Saturday night → Sunday window


def test_backfill_stops_when_next_day_would_hit_reserve(store, monkeypatch):
    from whaleproof.commands import backfill as bf

    class C:
        class usage:
            daily_count = 30_000

    monkeypatch.setattr(bf, "ingest_flow_day", lambda *a, **k: 0)
    monkeypatch.setattr(bf, "ingest_market", lambda *a, **k: None)
    monkeypatch.setattr(bf, "ingest_series", lambda *a, **k: None)
    stop = bf.adaptive_stop(C, limit=40_000, now=lambda: T(28, 7, 0))       # reserve 9600 → 30400 cap
    assert not stop()
    C.usage.daily_count = 33_700                                             # + 400/day would cross 34000
    assert stop()


def test_backfill_complete_flag(store):
    from whaleproof.commands.backfill import DONE, backfill_complete
    from whaleproof import market_calendar as mc
    start, end = date(2026, 9, 22), date(2026, 9, 25)
    assert not backfill_complete(store, start, end)
    for d in mc.sessions(start, end):
        store.set_checkpoint(f"day:{d.isoformat()}", DONE)
    assert backfill_complete(store, start, end)


def test_intraday_mode(monkeypatch):
    from whaleproof.core.budget import intraday_enabled
    monkeypatch.setenv("WHALEPROOF_INTRADAY", "auto")
    assert not intraday_enabled(backfill_done=False) and intraday_enabled(backfill_done=True)
    monkeypatch.setenv("WHALEPROOF_INTRADAY", "on")
    assert intraday_enabled(backfill_done=False)
    monkeypatch.setenv("WHALEPROOF_INTRADAY", "off")
    assert not intraday_enabled(backfill_done=True)


def test_reserve_excludes_intraday_when_disabled():
    assert live_reserve(T(28, 7, 0), intraday=False) == 100 + 3 * 1200 + 700 + 100 + 1500


def test_backfill_max_ceiling(monkeypatch):
    from whaleproof.commands import backfill as bf

    class C:
        class usage:
            daily_count = 34_700

    # with a 42k limit adaptive alone allows up to 36k; the 35k ceiling stops first (34,700 + 400 > 35,000)
    assert bf.adaptive_stop(C, limit=42_000, now=lambda: T(27, 21, 0), intraday=False, ceiling=35_000)()
    assert not bf.adaptive_stop(C, limit=42_000, now=lambda: T(27, 21, 0), intraday=False, ceiling=None)()
