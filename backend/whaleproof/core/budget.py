"""Adaptive API budget: reserve only what live jobs still need before the next 8 PM ET reset."""
from __future__ import annotations

import os
from datetime import datetime, time, timedelta

from whaleproof import market_calendar as mc

RESET = time(20, 0)


def _cost(name: str, default: int) -> int:
    return int(os.environ.get(name, str(default)))


def intraday_enabled(backfill_done: bool) -> bool:
    """auto (default): intraday feed stays off until the history backfill is complete — history comes first."""
    mode = os.environ.get("WHALEPROOF_INTRADAY", "auto").strip().lower()
    return mode == "on" or (mode == "auto" and backfill_done)


def _events(day, intraday: bool = True) -> list[tuple[datetime, int]]:
    """Live jobs on a trading day with their approximate request cost."""
    at = lambda h, m: datetime.combine(day, time(h, m), tzinfo=mc.NY)  # noqa: E731
    ev = [(at(8, 30), _cost("WHALEPROOF_CONFIRM_COST", 100))]
    t = at(9, 45)
    while intraday and t <= at(15, 30):
        ev.append((t, _cost("WHALEPROOF_INTRADAY_COST", 150)))
        t += timedelta(minutes=15)
    ev += [(at(9, 35), _cost("WHALEPROOF_MARKS_COST", 1200)), (at(9, 45), _cost("WHALEPROOF_MARKS_COST", 1200)),
           (at(15, 55), _cost("WHALEPROOF_MARKS_COST", 1200))]
    ev += [(at(16, 30), _cost("WHALEPROOF_SCAN_COST", 700)), (at(17, 0), _cost("WHALEPROOF_TRACK_COST", 100))]
    ev.sort()
    return ev


def next_reset(now: datetime) -> datetime:
    local = now.astimezone(mc.NY)
    r = datetime.combine(local.date(), RESET, tzinfo=mc.NY)
    return r if local < r else r + timedelta(days=1)


def live_reserve(now: datetime, intraday: bool = True) -> int:
    """Requests the live jobs will still use before the budget resets, plus a safety margin."""
    local, end = now.astimezone(mc.NY), next_reset(now)
    total = 0
    d = local.date()
    while d <= end.date():
        if mc.is_session(d):
            total += sum(c for t, c in _events(d, intraday) if local < t <= end)
        d += timedelta(days=1)
    return total + _cost("WHALEPROOF_SAFETY", 1500)
