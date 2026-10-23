"""Live-refresh budget governor for the shared UW key (40K/day, reset 20:00 ET).

The burn rate comes from UW's own `x-uw-daily-req-count` header, so it includes anything else using the same key.
If the current pace would spend more than what is left (minus a reserve and an evening allowance) before the reset,
every refresh interval is stretched by the same factor; at the reserve, live pulls stop."""
from __future__ import annotations

import json
from collections import deque
from datetime import datetime, timedelta

from whaleproof import market_calendar as mc
from whaleproof.core.budget import next_reset

from .config import EOD_WINDOW, EVENING_KEEP, LIVE_RESERVE

WINDOW_S = 15 * 60


class BurnMeter:
    def __init__(self) -> None:
        self.points: deque[tuple[datetime, int]] = deque()

    def add(self, at: datetime, count: int | None) -> None:
        if count is None:
            return
        if self.points and count < self.points[-1][1]:
            self.points.clear()                       # daily reset happened
        self.points.append((at, count))
        while len(self.points) > 2 and (at - self.points[0][0]).total_seconds() > WINDOW_S:
            self.points.popleft()

    def per_min(self) -> float | None:
        if len(self.points) < 2:
            return None
        (t0, c0), (t1, c1) = self.points[0], self.points[-1]
        mins = (t1 - t0).total_seconds() / 60
        return (c1 - c0) / mins if mins >= 1 else None


def pace_factor(used: int, limit: int, burn_per_min: float | None, now: datetime) -> float:
    """1.0 = full speed; >1 = stretch intervals by this factor; inf = stop (reserve reached)."""
    left = limit - LIVE_RESERVE - used
    if left <= 0:
        return float("inf")
    if not burn_per_min or burn_per_min <= 0:
        return 1.0
    end = next_reset(now)
    if mc.is_session(now.astimezone(mc.NY).date()) and now < mc.session_close(now.astimezone(mc.NY).date()):
        end = mc.session_close(now.astimezone(mc.NY).date())      # fast cadence only runs while the market is open
    mins = (end - now).total_seconds() / 60
    spendable = max(left - EVENING_KEEP, 1)
    return max(1.0, burn_per_min * mins / spendable)


def live_allowed(now: datetime, mode: str) -> bool:
    """May the refresher call UW right now? eod: only inside EOD_WINDOW on a trading day."""
    if mode == "full":
        return True
    local = now.astimezone(mc.NY)
    if not mc.is_session(local.date()):
        return False
    (h0, m0), (h1, m1) = EOD_WINDOW
    return (h0, m0) <= (local.hour, local.minute) < (h1, m1)


USAGE_KEY = "desk:last_usage"


def save_usage(store, count: int, at: datetime, key: str = USAGE_KEY) -> None:
    """Remember UW's daily request count so a restart (or a paused day) still shows it."""
    store.set_checkpoint(key, json.dumps({"count": count, "at": at.isoformat()}))


def load_usage(store, now: datetime, key: str = USAGE_KEY) -> dict | None:
    """Last saved count if it belongs to the current budget day (after the last 20:00 ET reset), else None."""
    raw = store.get_checkpoint(key)
    if not raw:
        return None
    v = json.loads(raw)
    last_reset = next_reset(now) - timedelta(days=1)
    return v if datetime.fromisoformat(v["at"]) >= last_reset else None


TALLY_KEY = "desk:own_calls"


class DeskTally:
    """This desk's own UW requests in the current budget day. UW stopped sending x-uw-daily-req-count ~2026-10-07,
    so this is the only count left — it misses anything else on the shared key (e.g. the original project)."""

    def __init__(self, store, now: datetime) -> None:
        self.store, self.seen = store, 0
        self.today = (load_usage(store, now, TALLY_KEY) or {}).get("count", 0)
        self.reset_at = next_reset(now)

    def update(self, now: datetime, sent: int) -> int:
        """`sent` = the client's running request count since start; returns today's total and saves it."""
        new_day = now >= self.reset_at
        if new_day:
            self.today, self.reset_at = 0, next_reset(now)
        new = max(sent - self.seen, 0)
        self.today, self.seen = self.today + new, sent
        if new or new_day:
            save_usage(self.store, self.today, now, TALLY_KEY)
        return self.today
