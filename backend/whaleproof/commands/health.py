"""Refresh flow health for every open pick (08:30 after OI publishes, 17:00 after the day's flow)."""
from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path

from whaleproof import market_calendar as mc
from whaleproof.config import load_settings
from whaleproof.core.data_layer.client import UWClient
from whaleproof.core.data_layer.ingest import ingest_contract_oi, ingest_net_prem
from whaleproof.core.data_layer.store import Store
from whaleproof.core.journal.chain import read_picks
from whaleproof.core.journal.flow_health import flow_health, source_alert
from whaleproof.core.journal.tracker import CLOSED, tradable

MAX_AGE_SESSIONS = 15


def update_health(client, store: Store, journal: Path, today: date, fetch: bool = True,
                  premarket: bool = False, pure_journal: Path | None = None) -> list[dict]:
    """Official picks until closed; pure / finalist buys from entry until their 5-session cut-off (OI only)."""
    from whaleproof.commands.marks import cutoff
    outs = {pid: json.loads(p) for pid, p in store.conn.execute("SELECT pick_id, payload FROM pick_outcome")}
    recent = mc.sessions(today.replace(year=today.year - 1), today)[-MAX_AGE_SESSIONS:]
    out = []
    todo = [(p, True) for p in tradable(read_picks(journal))] if Path(journal).exists() else []
    if pure_journal is not None and Path(pure_journal).exists():
        todo += [(p, False) for p in read_picks(pure_journal) if p.get("kind") == "pure"
                 and date.fromisoformat(p["entry_session"]) <= today <= cutoff(p)]
    for p, official in todo:
        if official and (outs.get(p["pick_id"], {}).get("status") in CLOSED
                         or date.fromisoformat(p["session_date"]) < recent[0]):
            continue
        whale = source_alert(store, p)
        if whale is None:
            continue
        if fetch:
            ingest_contract_oi(client, store, whale.option_chain, ttl=3600)
            if not premarket and official:
                ingest_net_prem(client, store, whale.ticker, today, live=True)
        through = mc.previous_session(today) if premarket else today
        h = flow_health(store, p, today, whale=whale, alerts_through=through)
        prev = store.conn.execute("SELECT payload FROM pick_health WHERE pick_id=?", (p["pick_id"],)).fetchone()
        store.conn.execute("INSERT OR REPLACE INTO pick_health VALUES (?,?,?)",
                           (p["pick_id"], h["as_of"], json.dumps(h)))
        if prev is None or json.loads(prev[0]).get("state") != h["state"]:
            store.conn.execute("INSERT OR REPLACE INTO pick_health_log VALUES (?,?,?,?)",
                               (p["pick_id"], datetime.now(mc.NY).isoformat(), h["state"], h["reason"]))
        out.append(h)
    store.conn.commit()
    return out


def main(argv: list[str]) -> int:
    s = load_settings()
    now = datetime.now(mc.NY)
    premarket = now.hour < 9 or (now.hour == 9 and now.minute < 30)
    out = update_health(UWClient(s.uw_api_key, s.live_request_cap), Store(s.db_path), s.journal_path,
                        now.date(), premarket=premarket, pure_journal=s.journal_path.parent / "pure.jsonl")
    for h in out:
        print(f"{h['pick_id']} {h['state']:14} {h['reason']}")
    print(f"{len(out)} picks checked")
    return 0
