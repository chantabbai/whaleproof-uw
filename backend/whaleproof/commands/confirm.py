"""Pre-open stage (08:30 ET): record whether each official (and pure-buy) pick's position stayed open overnight.

UW publishes daily OI ~6:45 AM ET. The confirmation is appended to the hash-chained journal before the
09:30 open, so it is timestamped evidence — the 16:30 decision itself never used this information.
"""
from __future__ import annotations

from datetime import datetime, time, timezone
from pathlib import Path

from whaleproof import market_calendar as mc
from whaleproof.config import load_settings
from whaleproof.core.checks.confluence import oi_confirm
from whaleproof.core.data_layer.client import UWClient
from whaleproof.core.data_layer.context import build_context
from whaleproof.core.data_layer.ingest import ingest_contract_oi
from whaleproof.core.data_layer.models import row_to_alert
from whaleproof.core.data_layer.store import Store
from whaleproof.core.journal.chain import append_pick, read_picks

OPEN = time(9, 30)
CONFIRMED = 0.5


def _status(ratio: float | None) -> str:
    if ratio is None:
        return "unavailable"
    return "confirmed" if ratio >= CONFIRMED else "unconfirmed" if ratio >= 0 else "closed"


def confirm_picks(client, store: Store, journal: Path, now: datetime, fetch: bool = True,
                  kind: str = "official") -> list[dict]:
    local = now.astimezone(mc.NY)
    today = local.date()
    if local.time() >= OPEN or not mc.is_session(today):
        return []
    recs = read_picks(journal)
    done = {r["pick_id"] for r in recs if r.get("kind") == "confirmation"}
    out = []
    for p in recs:
        if p.get("kind") != kind or p.get("entry_session") != today.isoformat() or p["pick_id"] in done:
            continue
        sd = datetime.fromisoformat(p["session_date"]).date()
        rows = store.alerts_between(sd, sd, p["ticker"])
        match = [r for r in rows if r["id"] == p.get("source_alert_id")] or \
                sorted((r for r in rows if r.get("option_chain") == p.get("contract")),   # legacy v0 picks
                       key=lambda r: -(float(r.get("total_premium") or 0)))
        alert = row_to_alert(match[0]) if match else None
        if alert is None:
            continue
        if fetch:
            ingest_contract_oi(client, store, alert.option_chain, ttl=0)
        c = oi_confirm(build_context(store, alert, now))
        before, after = build_context(store, alert, now).oi_next or (None, None)
        ratio = round(c.score, 4) if c.available else None
        rec = {"pick_id": p["pick_id"], "kind": "confirmation", "created_at": datetime.now(timezone.utc).isoformat(),
               "ticker": p["ticker"], "oi_before": before, "oi_after": after, "ratio": ratio,
               "status": _status(ratio), "reason": c.reason}
        out.append(append_pick(journal, rec))
    return out


def main(argv: list[str]) -> int:
    s = load_settings()
    client = UWClient(s.uw_api_key, s.live_request_cap)
    store, now = Store(s.db_path), datetime.now(timezone.utc)
    out = confirm_picks(client, store, s.journal_path, now)
    for r in out:
        print(f"{r['ticker']:6} {r['status']:12} {r['reason']}")
    print(f"{len(out)} confirmation(s) appended")
    pure = s.journal_path.parent / "pure.jsonl"           # research track: ~1 OI call per pure buy
    if pure.exists():
        po = confirm_picks(client, store, pure, now, kind="pure")
        counts = {st: sum(r["status"] == st for r in po) for st in ("confirmed", "unconfirmed", "closed", "unavailable")}
        print(f"pure buys: {len(po)} confirmation(s) {counts}")
    return 0
