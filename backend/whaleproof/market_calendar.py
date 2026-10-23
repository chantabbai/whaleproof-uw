from __future__ import annotations

from datetime import date, datetime, time, timedelta
from functools import lru_cache
from zoneinfo import ZoneInfo

import exchange_calendars as xcals
import pandas as pd

NY = ZoneInfo("America/New_York")
CLOSE = time(16, 0)


@lru_cache(maxsize=1)
def _cal():
    return xcals.get_calendar("XNYS", start="2021-01-01")


def is_session(d: date) -> bool:
    return bool(_cal().is_session(pd.Timestamp(d)))


def next_session(d: date) -> date:
    x = d + timedelta(days=1)
    while not is_session(x):
        x += timedelta(days=1)
    return x


def previous_session(d: date) -> date:
    x = d - timedelta(days=1)
    while not is_session(x):
        x -= timedelta(days=1)
    return x


def sessions(start: date, end: date) -> list[date]:
    return [ts.date() for ts in _cal().sessions_in_range(pd.Timestamp(start), pd.Timestamp(end))]


def session_close(d: date) -> datetime:
    """Real close (13:00 on early-close days); non-sessions fall back to 16:00."""
    if is_session(d):
        return _cal().session_close(pd.Timestamp(d)).to_pydatetime().astimezone(NY)
    return datetime.combine(d, CLOSE, tzinfo=NY)


def session_open(d: date) -> datetime:
    return datetime.combine(d, time(9, 30), tzinfo=NY)


def market_state(now: datetime) -> dict:
    """pre (before 09:30 on a session day) / open / after (after the close) / closed (weekend, holiday)."""
    local = now.astimezone(NY)
    d = local.date()
    nxt = d if is_session(d) and local < session_open(d) else next_session(d)
    base = {"now": local.isoformat(), "next_open": session_open(nxt).isoformat()}
    if not is_session(d):
        return base | {"state": "closed", "label": "Market closed (weekend/holiday)"}
    close = session_close(d)
    if local < session_open(d):
        return base | {"state": "pre", "label": "Pre-market", "close": close.isoformat()}
    if local < close:
        return base | {"state": "open", "label": "Market open" + (" (early close)" if close.time() < CLOSE else ""),
                       "close": close.isoformat()}
    return base | {"state": "after", "label": "After hours", "close": close.isoformat()}


def last_completed_session(now: datetime) -> date:
    local = now.astimezone(NY)
    d = local.date()
    if is_session(d) and local >= session_close(d):
        return d
    return previous_session(d)
