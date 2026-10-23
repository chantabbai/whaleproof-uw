"""Flow health: is the money behind a pick still in the trade?

States (worst first): EXITED, ROLLED, FLOW_REVERSED, REDUCING, HOLDING, UNKNOWN.
Point-in-time: only OI dated ≤ as_of and alerts from sessions ≤ as_of are used. OI for a date is the
open interest published that morning (~6:45 ET), i.e. positions after the previous session.
"""
from __future__ import annotations

import json

from datetime import date

from whaleproof import market_calendar as mc
from whaleproof.core.data_layer.models import FlowAlert, row_to_alert
from whaleproof.core.data_layer.store import Store

EXIT_PCT, REDUCE_PCT, SELL_PCT, ROLL_PCT = 0.5, 0.25, 0.25, 0.5
SIDE = 0.7
REVERSAL_STRENGTH = 0.3
EXIT_STATES = {"EXITED", "FLOW_REVERSED"}


def source_alert(store: Store, pick: dict) -> FlowAlert | None:
    sd = date.fromisoformat(pick["session_date"])
    rows = store.alerts_between(sd, sd, pick["ticker"])
    match = [r for r in rows if r["id"] == pick.get("source_alert_id")] or \
        sorted((r for r in rows if r.get("option_chain") == pick.get("contract")),
               key=lambda r: -(float(r.get("total_premium") or 0)))
    return row_to_alert(match[0]) if match else None


def _buyer(a: FlowAlert) -> bool:
    return a.ask_share >= a.bid_share


def flow_health(store: Store, pick: dict, as_of: date, whale: FlowAlert | None = None,
                alerts_through: date | None = None) -> dict:
    """`alerts_through`: last session whose flow is known (pre-open decisions pass the previous session)."""
    whale = whale or source_alert(store, pick)
    base = {"pick_id": pick["pick_id"], "as_of": as_of.isoformat(), "state": "UNKNOWN", "reason": "no data yet"}
    if whale is None:
        return base | {"reason": "source alert not found"}
    size = whale.total_size or whale.volume or 0
    d = whale.session_date
    after = [s for s in mc.sessions(mc.next_session(d), as_of)] if as_of > d else []

    ois = [(s, store.get_metric(whale.option_chain, s, "oi")) for s in after]
    ois = [(s, v) for s, v in ois if v is not None]
    peak = max((v for _, v in ois), default=None)
    now = ois[-1][1] if ois else None
    closed_pct = ((peak - now) / size) if (ois and size) else 0.0

    through = alerts_through or as_of
    later = ([row_to_alert(r) for r in store.alerts_between(mc.next_session(d), through, whale.ticker)]
             if through > d else [])
    buyer = _buyer(whale)
    sells = [a for a in later if a.option_chain == whale.option_chain
             and ((a.bid_share >= SIDE) if buyer else (a.ask_share >= SIDE))]
    selling_pct = (sum(a.total_size or a.volume or 0 for a in sells) / size) if size else 0.0
    rolls = [a for a in later if a.option_chain != whale.option_chain and a.kind == whale.kind
             and ((a.ask_share >= SIDE) if buyer else (a.bid_share >= SIDE))
             and (a.total_size or 0) >= ROLL_PCT * size]

    rev_days = []
    for s in mc.sessions(mc.previous_session(mc.previous_session(through)), through)[-2:]:
        n = store.get_metric(whale.ticker, s, "net_prem")
        if n and n["gross"]:
            flow = (n["call"] - n["put"]) / n["gross"]
            rev_days.append(flow * pick["direction"] <= -REVERSAL_STRENGTH)
    reversed_ = len(rev_days) == 2 and all(rev_days)

    out = base | {"size": size, "oi_entry": ois[0][1] if ois else None, "oi_peak": peak, "oi_now": now,
                  "closed_pct": round(closed_pct, 4), "selling_pct": round(selling_pct, 4),
                  "rolled_to": rolls[-1].option_chain if rolls else None, "flow_reversed": reversed_}
    if not ois and not later and not rev_days:
        return out
    if closed_pct >= EXIT_PCT:
        if rolls:
            return out | {"state": "ROLLED", "reason": f"position moved to {rolls[-1].option_chain}"}
        return out | {"state": "EXITED", "reason": f"{closed_pct:.0%} of the whale's size closed (OI {peak:,}→{now:,})"}
    if reversed_:
        return out | {"state": "FLOW_REVERSED", "reason": "ticker money has bet the other way for 2 sessions"}
    if closed_pct >= REDUCE_PCT or selling_pct >= SELL_PCT:
        why = f"{closed_pct:.0%} of size closed" if closed_pct >= REDUCE_PCT else f"{selling_pct:.0%} of size sold on the same contract"
        return out | {"state": "REDUCING", "reason": why}
    if len(ois) < 2 and not later:
        # one post-trade OI reading and no later flow: nothing has left, but nothing has been tested yet either
        return out | {"state": "HOLDING", "early": True, "reason": "no exit seen yet (first reading after the trade)"}
    return out | {"state": "HOLDING", "early": False, "reason": "money still in the trade"}


def oi_trail(store: Store, pick: dict, limit: int = 15) -> list[dict]:
    """The whale contract's open interest day by day from the flow day on (dashboard trail)."""
    chain = pick.get("contract")
    if not chain:
        return []
    rows = store.conn.execute("SELECT date, payload FROM daily_metric WHERE ticker=? AND kind='oi' AND date>=? "
                              "ORDER BY date LIMIT ?", (chain, pick.get("session_date", ""), limit)).fetchall()
    return [{"date": d, "oi": int(json.loads(v))} for d, v in rows]
