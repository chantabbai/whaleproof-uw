"""The Take list (pre-registration Amendment 16): which finalist trades to actually hold.

A sizing overlay only — every trade stays in the record. Per entry day: one per stock (biggest whale premium wins);
rank by finalists matched (more first) then premium; each trade uses a slot on the first of its finalists with room
(≤ PER_FINALIST new per finalist per day); at most MAX_OPEN taken trades open at once. A trade the 9:45 check skips
uses no slot — the next in line takes it."""
from __future__ import annotations

from collections import defaultdict

PER_FINALIST = 3
MAX_OPEN = 10


def take_plan(candidates: list[dict], fills: dict[str, dict]) -> dict[str, str]:
    """pick_id → "take" | "same stock" | "skipped at 9:45" | "over cap" | "open limit".
    Candidates need pick_id, ticker, entry_session, exit_by, finalists (ids in F1, F2, F3 order), premium."""
    by_day: dict[str, list[dict]] = defaultdict(list)
    for c in candidates:
        by_day[c["entry_session"]].append(c)
    out: dict[str, str] = {}
    taken: list[dict] = []
    for day in sorted(by_day):
        still_open = sum(1 for t in taken if t["entry_session"] < day <= (t["exit_by"] or ""))
        seen: set[str] = set()
        used: dict[str, int] = defaultdict(int)
        for c in sorted(by_day[day], key=lambda c: (-len(c["finalists"]), -(c.get("premium") or 0), c["ticker"])):
            if c["ticker"] in seen:
                out[c["pick_id"]] = "same stock"
                continue
            seen.add(c["ticker"])
            if (fills.get(c["pick_id"]) or {}).get("decision", "still a buy") != "still a buy":
                out[c["pick_id"]] = "skipped at 9:45"
                continue
            room = next((f for f in c["finalists"] if used[f] < PER_FINALIST), None)
            if room is None:
                out[c["pick_id"]] = "over cap"
            elif still_open >= MAX_OPEN:
                out[c["pick_id"]] = "open limit"
            else:
                used[room] += 1
                still_open += 1
                taken.append(c)
                out[c["pick_id"]] = "take"
    return out
