"""Surfacing: today's signals while the day's flow is still forming (final at the close + 15 min), and the ones that
'went back under' — passed every check earlier today, then stopped (a bigger opposite print, a sale leg, or the alert
left the flow). Keyed by ticker + direction, because a signal is the biggest bet of that pair and its alert can change.
Watch only: the rule buys at the next open after the day is final. Stored per day under data/desk/live/."""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

GONE = "no longer in today's flow"


def empty(day: str) -> dict:
    return {"day": day, "seen": {}, "under": {}}


def _key(x: dict) -> str:
    return f"{x['ticker']}:{x['direction']}"


def update(log: dict, signals: list[dict], bets: list[dict], now: datetime) -> dict:
    at = now.isoformat()
    cur = {_key(s): s for s in signals}
    for k, s in cur.items():
        prev = log["seen"].get(k, {})
        log["seen"][k] = {"ticker": s["ticker"], "direction": s["direction"], "tier": s.get("tier"),
                          "label": s.get("label"), "premium": s.get("premium"),
                          "first_seen": prev.get("first_seen", at), "last_seen": at}
        log["under"].pop(k, None)                            # resurfaced
    why = {_key(b): b.get("reason") or "" for b in bets if b.get("verdict") != "signal"}
    for k, s in log["seen"].items():
        if k not in cur and k not in log["under"]:
            log["under"][k] = s | {"went_under": at, "reason": why.get(k) or GONE}
    return log


def went_under(log: dict) -> list[dict]:
    return sorted(log["under"].values(), key=lambda u: u["went_under"], reverse=True)


def load(path: Path, day: str) -> dict:
    try:
        log = json.loads(path.read_text())
        return log if log.get("day") == day else empty(day)
    except (OSError, ValueError):
        return empty(day)


def save(path: Path, log: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(log))
    tmp.replace(path)
