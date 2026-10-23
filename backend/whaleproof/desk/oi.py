"""Open interest of a signal's contract, day by day. UW's OI for date X = contracts open after X−1's session, published
~06:45 ET on X — so the flow day's next session shows whether the whale's position stayed open (context, not a filter:
across the whole tracker record only 42 of ~1,700 signals were unconfirmed and they did about the same — exploratory
study scripts/research/oi_confirm.py → journal/research/oi-confirm.json, shown on the card via oi_record)."""
from __future__ import annotations

from whaleproof import market_calendar as mc
from whaleproof.core.data_layer.store import Store
from datetime import date
import json
from pathlib import Path

CONFIRM_RATIO = 0.5       # OI grew by at least half the whale's size overnight


def oi_view(store: Store, chain: str, session_date: str, size: int | None, limit: int = 12) -> dict:
    rows = store.conn.execute("SELECT date, payload FROM daily_metric WHERE ticker=? AND kind='oi' AND date>=? "
                              "ORDER BY date LIMIT ?", (chain, session_date, limit)).fetchall()
    trail = [{"date": d, "oi": int(float(v))} for d, v in rows]
    by = {p["date"]: p["oi"] for p in trail}
    nxt = mc.next_session(date.fromisoformat(session_date)).isoformat()
    base, after = by.get(session_date), by.get(nxt)
    nm = None
    if base is not None and after is not None:
        change = after - base
        nm = {"date": nxt, "change": change, "ratio": round(change / size, 3) if size else None}
    confirmed = None if nm is None or nm["ratio"] is None else nm["ratio"] >= CONFIRM_RATIO
    return {"trail": trail, "next_morning": nm, "confirmed": confirmed,
            "latest": {"date": trail[-1]["date"], "oi": trail[-1]["oi"]} if trail else None}


def oi_record(path: Path) -> dict | None:
    """How unconfirmed signals did in the whole tracker record (exploratory study output), or None if not run."""
    try:
        p = json.loads(Path(path).read_text())["periods"]["All periods"]
    except (OSError, KeyError, ValueError):
        return None
    pick = lambda g: {"trades": g["trades"], "mean_vs_spy": g["mean_vs_spy"]}
    return {"unconfirmed": pick(p["unconfirmed"]), "confirmed": pick(p["groups"]["confirmed"]),
            "difference_range": p.get("unconfirmed_minus_confirmed")}


def oi_by_session(store: Store, chain: str | None, session_date: str, end: str) -> list[list]:
    """[[session, oi, change vs the session before]] from the signal day to `end`. UW's OI dated X is what stayed open
    after X−1's session (published ~06:45 ET on X), so each number sits on the session it describes."""
    if not chain:
        return []
    rows = store.conn.execute("SELECT date, payload FROM daily_metric WHERE ticker=? AND kind='oi' AND date>=? "
                              "ORDER BY date", (chain, session_date)).fetchall()
    out, prev = [], None
    for d, v in rows:
        n, s = int(float(v)), mc.previous_session(date.fromisoformat(d)).isoformat()
        if s >= session_date and s <= end:
            out.append([s, n, None if prev is None else n - prev])
        prev = n
    return out
