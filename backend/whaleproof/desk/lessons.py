"""Lessons from the record: fixed candidate rules, applied the same way to every finished signal.

A lesson is a rule written down before the trades it is judged on. The candidates below were locked (hash + time,
`journal/lessons-frozen.json`) before any of them was backtested, and all of them are tracked forward — none dropped
for looking bad. History results are hindsight on trades the rules were picked after seeing; only signals decided
after the lock time are a fair test. Exploratory, display only: never part of the frozen signal filter.

Daily bars only, so: a level that the open already passed fills at the open; otherwise it fills exactly at the level
(optimistic, no slippage). A skipped trade counts as $0, so skip rules are scored on every trade, not just kept ones."""
from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, timedelta
from pathlib import Path

from whaleproof import market_calendar as mc
from whaleproof.core.backtest.runner import COST
from whaleproof.core.backtest.simple import AS_OF_DELAY
from whaleproof.core.data_layer.models import Bar

from .config import HOLD_SESSIONS

CANDIDATES: dict[str, dict] = {
    "take_profit_5": {"kind": "take_profit", "level": 0.05, "text": "Sell as soon as the stock is up 5%"},
    "stop_loss_5": {"kind": "stop_loss", "level": 0.05, "text": "Sell if the stock falls 5%"},
    "skip_gap_chase_2": {"kind": "skip_gap", "level": 0.02,
                         "text": "Skip it if the stock opens 2% or more past the signal-day close"},
    "exit_day_3": {"kind": "exit_day", "sessions": 3, "text": "Sell at the third day's close instead of the fifth"},
}


def candidates_hash() -> str:
    return hashlib.sha256(json.dumps(CANDIDATES, sort_keys=True).encode()).hexdigest()[:16]


def _out(exit_bar: Bar, price: float, entry: float, direction: int) -> dict:
    return {"taken": True, "net": (price / entry - 1) * direction - COST, "exit_date": exit_bar.date, "exit_price": price}


def apply(rule: str | None, bars: list[Bar], session_date: date, direction: int) -> dict | None:
    """One finished signal under `rule` (None = the signal rule itself, equal to the tracker's result).
    None when the hold isn't finished or a bar the rule needs is missing (left out of both sides)."""
    after = [b for b in bars if b.date > session_date][:HOLD_SESSIONS]
    if len(after) < HOLD_SESSIONS or not after[0].open:
        return None
    entry = after[0].open
    c = CANDIDATES[rule] if rule else {"kind": "base"}
    k = c["kind"]
    if k == "skip_gap":
        sig = next((b for b in bars if b.date == session_date), None)
        if not sig or not sig.close:
            return None
        if (entry / sig.close - 1) * direction >= c["level"]:
            return {"taken": False, "net": 0.0, "exit_date": None, "exit_price": None}
    if k in ("take_profit", "stop_loss"):
        sign = 1 if k == "take_profit" else -1                      # +: favourable level, −: adverse level
        level = entry * (1 + sign * c["level"] * direction)
        for b in after:
            o = (b.open / entry - 1) * direction * sign
            best = ((b.high if direction * sign > 0 else b.low) / entry - 1) * direction * sign
            if b is not after[0] and o >= c["level"]:
                return _out(b, b.open, entry, direction)           # gapped past the level overnight
            if best >= c["level"]:
                return _out(b, level, entry, direction)
    if k == "exit_day":
        b = after[c["sessions"] - 1]
        return _out(b, b.close, entry, direction)
    return _out(after[-1], after[-1].close, entry, direction)


def summarize(pairs: list[tuple[float, float, bool]]) -> dict:
    """pairs = (base net, rule net, rule took the trade)."""
    n = len(pairs)
    if not n:
        return {"trades": 0}
    b, r = [p[0] for p in pairs], [p[1] for p in pairs]
    return {"trades": n, "taken": sum(p[2] for p in pairs),
            "base_avg": sum(b) / n, "rule_avg": sum(r) / n, "base_1k": sum(b) * 1000, "rule_1k": sum(r) * 1000,
            "diff_1k": (sum(r) - sum(b)) * 1000, "base_won": sum(x > 0 for x in b) / n,
            "rule_won": sum(x > 0 for x in r) / n, "changed": sum(abs(p[0] - p[1]) > 1e-12 for p in pairs)}


def trade(store, row: dict) -> dict | None:
    """One finished tracker row under the signal rule and every locked rule (cached daily bars)."""
    d = date.fromisoformat(row["session_date"])
    bars = store.get_ohlc(row["ticker"], d - timedelta(days=7), d + timedelta(days=20))
    base = apply(None, bars, d, row["direction"])
    if base is None:
        return None
    return {"base": base, "rules": {k: apply(k, bars, d, row["direction"]) for k in CANDIDATES}}


def forward(store, rows: list[dict], frozen: dict) -> dict:
    """Locked rules on finished signals decided after the lock: the fair test."""
    pairs: dict[str, list] = {k: [] for k in CANDIDATES}
    for r in rows:
        if r["stock"]["status"] != "closed" or not is_forward(date.fromisoformat(r["session_date"]), frozen):
            continue
        t = trade(store, r)
        for k, x in (t["rules"] if t else {}).items():
            if x is not None:
                pairs[k].append((t["base"]["net"], x["net"], x["taken"]))
    return {k: summarize(v) for k, v in pairs.items()}


def freeze(path: Path, now: datetime, git_sha: str) -> dict:
    """Lock the candidates once. A later candidate set needs a new file with its own start time."""
    if path.exists():
        raise FileExistsError(f"{path} is already frozen — never rewrite it")
    f = {"frozen_at": now.isoformat(), "git_sha": git_sha, "hash": candidates_hash(), "candidates": CANDIDATES,
         "rule": "Forward test = signals whose decision time (session close + 15 min) is after frozen_at."}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(f, indent=2) + "\n")
    return f


def is_forward(session_date: date, frozen: dict) -> bool:
    return mc.session_close(session_date) + AS_OF_DELAY > datetime.fromisoformat(frozen["frozen_at"])
