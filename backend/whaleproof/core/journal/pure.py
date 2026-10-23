"""Live forward track of pure-directional buys (pre-registration Amendment 5). Separate journal from official picks:
every gate passer at the scan, tagged by setup, held next open → close of the 5th session (same as backtest r5)."""
from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, time, timedelta
from pathlib import Path

from whaleproof import market_calendar as mc
from whaleproof.core.backtest.runner import COST, repeat_count
from whaleproof.core.backtest.simple import AS_OF_DELAY, day_trades
from whaleproof.core.data_layer.client import UWBudgetExceeded
from whaleproof.core.data_layer.ingest import KIND_EARN, ingest_bars, ingest_earnings
from whaleproof.core.data_layer.models import Bar
from whaleproof.core.data_layer.store import Store
from whaleproof.core.verdict.setups import setup_for

from .chain import append_pick, read_picks
from .tracker import after_open_fills, after_open_group

HOLD = 5
OPEN = time(9, 30)


def pure_records(store: Store, d: date, now: datetime, official_tickers: set[str] = frozenset()) -> list[dict]:
    entry = mc.next_session(d)
    reconstructed = now.astimezone(mc.NY) >= datetime.combine(entry, OPEN, tzinfo=mc.NY)
    as_of = mc.session_close(d) + AS_OF_DELAY
    out = []
    for a, fails, _ in day_trades(store, d):
        if fails:
            continue
        earnings = [date.fromisoformat(x) for x in store.get_metric(a.ticker, "all", "earnings") or []]
        out.append({
            "pick_id": hashlib.sha1(f"{d}|{a.ticker}|{a.direction}|pure".encode()).hexdigest()[:12],
            "kind": "pure", "session_date": d.isoformat(), "entry_session": entry.isoformat(),
            "created_at": now.isoformat(), "reconstructed": reconstructed,
            "ticker": a.ticker, "direction": a.direction, "setup": setup_for(a, earnings, repeat_count(store, a, as_of)),
            "contract": a.option_chain, "premium": a.total_premium, "dte": a.dte, "otm_pct": round(a.otm_pct, 4),
            "sweep": a.has_sweep, "ask_share": round(a.ask_share, 3), "source_alert_id": a.id,
            "alert_time": a.created_at.isoformat(), "also_official": a.ticker in official_tickers,
        })
    return out


def write_pure(path: Path, records: list[dict]) -> int:
    """Append records not yet in the journal. Returns how many were written."""
    have = {r["pick_id"] for r in read_picks(path)}
    n = 0
    for r in records:
        if r["pick_id"] not in have:
            append_pick(path, r)
            n += 1
    return n


def evaluate_hold(pick: dict, bars: list[Bar]) -> dict:
    entry_day = date.fromisoformat(pick["entry_session"])
    bars = [b for b in bars if b.date >= entry_day][:HOLD]
    base = {"pick_id": pick["pick_id"], "ticker": pick["ticker"], "setup": pick.get("setup")}
    if not bars:
        return {**base, "status": "pending", "return": None}
    d, entry = pick["direction"], bars[0].open
    ret = lambda px: (px / entry - 1) * d - COST  # noqa: E731  net of 5 bps/side, same as backtest r5
    mfe = max(ret(b.high if d > 0 else b.low) for b in bars)
    mae = min(ret(b.low if d > 0 else b.high) for b in bars)
    closed = len(bars) == HOLD
    return {**base, "status": "closed" if closed else "open", "entry": entry, "entry_date": entry_day.isoformat(),
            "exit_date": bars[-1].date.isoformat() if closed else None, "return": ret(bars[-1].close),
            "mfe": mfe, "mae": mae, "sessions_held": len(bars)}


def track_pure(store: Store, picks: list[dict]) -> list[dict]:
    out = []
    for p in picks:
        start = date.fromisoformat(p["entry_session"])
        out.append(evaluate_hold(p, store.get_ohlc(p["ticker"], start, start + timedelta(days=14))))
    return out


def _stats(rets: list[float]) -> dict:
    gains, losses = sum(r for r in rets if r > 0), -sum(r for r in rets if r < 0)
    return {"win_rate": sum(r > 0 for r in rets) / len(rets) if rets else None,
            "mean": sum(rets) / len(rets) if rets else None,
            "profit_factor": gains / losses if losses else None}


def _group(live: dict, outcomes: list[dict], key) -> dict:
    by: dict[str, dict] = {}
    for o in outcomes:
        p = live.get(o["pick_id"])
        if not p:
            continue
        g = by.setdefault(key(p), {"closed": [], "open": 0})
        if o["status"] == "closed":
            g["closed"].append(o["return"])
        elif o["status"] == "open":
            g["open"] += 1
    return {k: {"closed": len(v["closed"]), "open": v["open"], **_stats(v["closed"])} for k, v in sorted(by.items())}


def pure_scorecard(picks: list[dict], outcomes: list[dict], confirms: dict[str, str] | None = None,
                   fills: dict[str, dict] | None = None) -> dict:
    """Forward stats on closed 5-session holds, by setup and by next-morning OI status; reconstructed days excluded."""
    confirms = confirms or {}
    live = {p["pick_id"]: p for p in picks if not p.get("reconstructed")}
    every = [o["return"] for o in outcomes if o["pick_id"] in live and o["status"] == "closed"]
    return {"by_setup": _group(live, outcomes, lambda p: p["setup"]),
            "by_confirmation": _group(live, outcomes, lambda p: confirms.get(p["pick_id"], "unknown")),
            "by_after_open": _group(live, outcomes, lambda p: after_open_group(fills or {}, p["pick_id"])),
            "all": {"closed": len(every), **_stats(every)},
            "reconstructed_excluded": sum(1 for p in picks if p.get("reconstructed"))}


def refresh_pure(client, store: Store, path: Path, today: date) -> dict:
    """Re-score holds that have started and aren't closed: 1 bars call per ticker per day (earnings once per ticker).
    Stops cleanly at the API budget and saves partial outcomes."""
    recs = read_picks(path)
    picks = [r for r in recs if r.get("kind") == "pure"]
    confirms = {r["pick_id"]: r["status"] for r in recs if r.get("kind") == "confirmation"}
    sc_path = Path(path).parent / "pure-scorecard.json"
    prev = json.loads(sc_path.read_text()).get("outcomes", {}) if sc_path.exists() else {}
    live = [p for p in picks if prev.get(p["pick_id"], {}).get("status") != "closed"
            and date.fromisoformat(p["entry_session"]) <= today]
    stopped = False
    for t in sorted({p["ticker"] for p in live}):
        mark = f"bars:{t}"
        if store.get_checkpoint(mark) == today.isoformat():
            continue
        try:
            ingest_bars(client, store, t, _FRESH)
            if store.get_metric(t, "all", KIND_EARN) is None:
                ingest_earnings(client, store, t, None)
        except UWBudgetExceeded:
            stopped = True
            break
        store.set_checkpoint(mark, today.isoformat())
    outs = {**prev, **{o["pick_id"]: o for o in track_pure(store, live)}}
    card = pure_scorecard(picks, list(outs.values()), confirms, after_open_fills(recs)) | {"budget_stopped": stopped}
    sc_path.write_text(json.dumps({"card": card, "outcomes": outs}, indent=2, sort_keys=True, default=str))
    return card


_FRESH = 6 * 3600   # bars cache: refetch if older than 6h (track runs once after the close)
