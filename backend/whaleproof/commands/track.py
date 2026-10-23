from __future__ import annotations

import json
from datetime import datetime

from whaleproof.config import REPO_ROOT, load_settings
from whaleproof.core.data_layer.client import UWClient
from whaleproof.core.data_layer.ingest import ingest_series
from whaleproof.core.data_layer.store import Store
from whaleproof.core.journal.chain import read_picks, verify_chain
from whaleproof.core.journal.pure import refresh_pure
from whaleproof.core.journal.tracker import after_open_fills, scorecard, track_picks, tradable


def main(argv: list[str]) -> int:
    s = load_settings()
    store = Store(s.db_path)
    recs = read_picks(s.journal_path)
    picks = tradable(recs)
    client = UWClient(s.uw_api_key, s.live_request_cap)
    today = datetime.now().date()
    for t in sorted({p["ticker"] for p in picks}):
        ingest_series(client, store, t, today, force=True)  # bypass checkpoint + cache for fresh OHLC
    outs = track_picks(store, picks)
    card = {"chain_valid": verify_chain(s.journal_path), **scorecard(outs, after_open_fills(recs))}
    (REPO_ROOT / "journal" / "scorecard.json").write_text(json.dumps(card, indent=2, sort_keys=True, default=str))
    print(json.dumps({k: card[k] for k in ("chain_valid", "closed_count", "open_count")}), card["overall"])
    pure_path = s.journal_path.parent / "pure.jsonl"
    if pure_path.exists():
        pc = refresh_pure(client, store, pure_path, today)
        print(f"pure buys (forward, live only): {pc['all']}")
    return 0
