from __future__ import annotations

import json
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone

from whaleproof.core.backtest.stats import summarize_returns
from whaleproof.core.data_layer.models import Bar
from whaleproof.core.data_layer.store import Store

CLOSED = {"target", "invalidated", "time_stop"}
TRADABLE = {"official", "intraday"}


def tradable(records: list[dict]) -> list[dict]:
    """Journal holds picks and pre-open confirmation notes; only picks are traded/scored."""
    return [r for r in records if r.get("kind") in TRADABLE]


def evaluate_pick(pick: dict, bars: list[Bar], day1: str = "plan") -> dict:
    """Plan exits from the entry session. day1="overnight" (Amendment 13): on the entry day only an emergency stop at
    twice the planned stop distance applies; target and normal stop count from day 2 (hold at least one night)."""
    entry_day = date.fromisoformat(pick["entry_session"])
    bars = [b for b in bars if b.date >= entry_day]
    base = {"pick_id": pick["pick_id"], "weights_version": pick["weights_version"], "kind": pick["kind"]}
    if not bars:
        return {**base, "status": "pending", "return": None}
    d = pick["direction"]
    plan = pick["plan"]
    inv, tgt, stop_n = plan["invalidation"], plan["target"], plan["time_stop_sessions"]
    entry = bars[0].open
    if pick.get("entry_price"):
        # intraday pick: entered mid-session at a known price. The entry day's high/low may predate the
        # entry, so exits are only checked from the next session; day 0 is marked to its close.
        entry = pick["entry_price"]
        day0, bars = bars[0], [b for b in bars if b.date > entry_day]
        if not bars:
            r0 = (day0.close / entry - 1) * d
            return {**base, "status": "open", "entry": entry, "entry_date": entry_day.isoformat(),
                    "exit_date": None, "return": r0, "mfe": max(r0, 0.0), "mae": min(r0, 0.0), "sessions_held": 1}
    mfe = mae = 0.0

    def ret(px: float) -> float:
        return (px / entry - 1) * d

    ref = plan.get("entry_ref") or entry
    emergency = ref - 2 * d * abs(ref - inv)
    for i, b in enumerate(bars, start=1):
        hi, lo = (b.high, b.low) if d > 0 else (b.low, b.high)
        mfe, mae = max(mfe, ret(hi)), min(mae, ret(lo))
        stop, can_win = (emergency, False) if day1 == "overnight" and i == 1 and not pick.get("entry_price") \
            else (inv, True)
        hit_inv = (b.low <= stop) if d > 0 else (b.high >= stop)
        hit_tgt = can_win and ((b.high >= tgt) if d > 0 else (b.low <= tgt))
        status, px = None, None
        if hit_inv:
            status, px = "invalidated", (min(b.open, stop) if d > 0 else max(b.open, stop))  # gap-through fills worse
        elif hit_tgt:
            status, px = "target", tgt
        elif i >= stop_n:
            status, px = "time_stop", b.close
        if status:
            return {**base, "status": status, "entry": entry, "entry_date": entry_day.isoformat(),
                    "exit_date": b.date.isoformat(), "return": ret(px), "mfe": mfe, "mae": mae, "sessions_held": i}
    last = bars[-1]
    return {**base, "status": "open", "entry": entry, "entry_date": entry_day.isoformat(), "exit_date": None,
            "return": ret(last.close), "mfe": mfe, "mae": mae, "sessions_held": len(bars)}


def evaluate_pick_follow(pick: dict, bars: list[Bar], state_at) -> dict:
    """Plan exits plus 'follow the money': if flow health turns EXITED/FLOW_REVERSED (known on the morning
    of a session), exit at that session's open. `state_at(d)` returns the state known before d's open."""
    from .flow_health import EXIT_STATES
    entry_day = date.fromisoformat(pick["entry_session"])
    bars = [b for b in bars if b.date >= entry_day]
    base = {"pick_id": pick["pick_id"], "weights_version": pick["weights_version"], "kind": pick["kind"]}
    if not bars:
        return {**base, "status": "pending", "return": None}
    d, plan = pick["direction"], pick["plan"]
    inv, tgt, stop_n = plan["invalidation"], plan["target"], plan["time_stop_sessions"]
    entry = bars[0].open
    ret = lambda px: (px / entry - 1) * d  # noqa: E731
    for i, b in enumerate(bars, start=1):
        if (b.low <= inv) if d > 0 else (b.high >= inv):
            px = min(b.open, inv) if d > 0 else max(b.open, inv)
            return {**base, "status": "invalidated", "exit_date": b.date.isoformat(), "return": ret(px)}
        if (b.high >= tgt) if d > 0 else (b.low <= tgt):
            return {**base, "status": "target", "exit_date": b.date.isoformat(), "return": ret(tgt)}
        if i >= stop_n:
            return {**base, "status": "time_stop", "exit_date": b.date.isoformat(), "return": ret(b.close)}
        if i < len(bars) and state_at(bars[i].date) in EXIT_STATES:
            nb = bars[i]
            return {**base, "status": "money_left", "exit_date": nb.date.isoformat(), "return": ret(nb.open)}
    return {**base, "status": "open", "exit_date": None, "return": ret(bars[-1].close)}


def track_picks(store: Store, picks: list[dict]) -> list[dict]:
    out = []
    for p in picks:
        start = date.fromisoformat(p["entry_session"])
        o = evaluate_pick(p, store.get_ohlc(p["ticker"], start, start + timedelta(days=30)))
        o["ticker"] = p["ticker"]
        store.conn.execute("INSERT OR REPLACE INTO pick_outcome VALUES (?,?,?)",
                           (p["pick_id"], datetime.now(timezone.utc).isoformat(), json.dumps(o)))
        out.append(o)
    store.conn.commit()
    return out


def after_open_fills(records: list[dict]) -> dict[str, dict]:
    """Latest 9:45 'still worth buying?' decision per pick; a fill_void cancels fills written before it."""
    out: dict[str, dict] = {}
    for r in records:
        if r.get("kind") == "fill":
            out[r["pick_id"]] = r
        elif r.get("kind") == "fill_void":
            out.pop(r["pick_id"], None)
    return out


def after_open_group(fills: dict[str, dict], pick_id: str) -> str:
    """bought / skipped at 9:45 / no 9:45 check (picks entered before the check existed, or intraday)."""
    f = fills.get(pick_id)
    if not f:
        return "no 9:45 check"
    return "bought" if f.get("decision") == "still a buy" else "skipped at 9:45"


def scorecard(outcomes: list[dict], fills: dict[str, dict] | None = None) -> dict:
    """'overall' = every pick (pre-registered); 'by_after_open' splits bought vs skipped at 9:45 (Amendment 14)."""
    fills = fills or {}
    scored = [o for o in outcomes if o.get("return") is not None]
    by_v, by_k, by_a = defaultdict(list), defaultdict(list), defaultdict(list)
    for o in scored:
        by_v[o["weights_version"]].append(o["return"])
        by_k[o["kind"]].append(o["return"])
        by_a[after_open_group(fills, o.get("pick_id", ""))].append(o["return"])
    return {"overall": summarize_returns([o["return"] for o in scored]),
            "by_version": {k: summarize_returns(v) for k, v in sorted(by_v.items())},
            "by_kind": {k: summarize_returns(v) for k, v in sorted(by_k.items())},
            "by_after_open": {k: summarize_returns(v) for k, v in sorted(by_a.items())},
            "closed_count": sum(o["status"] in CLOSED for o in outcomes),
            "open_count": sum(o["status"] == "open" for o in outcomes)}
