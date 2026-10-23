from __future__ import annotations

import argparse
from datetime import date, datetime

from whaleproof import market_calendar as mc
from whaleproof.config import load_settings
from whaleproof.core.data_layer.store import Store
from whaleproof.core.journal.chain import read_picks
from whaleproof.core.journal.pure import pure_records, write_pure


def main(argv: list[str]) -> int:
    """Write the pure-buys list for a stored session (no API calls). Written after the entry open → flagged
    'reconstructed' and excluded from forward stats."""
    p = argparse.ArgumentParser(prog="whaleproof pure")
    p.add_argument("--date", type=date.fromisoformat, required=True)
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args(argv)
    s = load_settings()
    official = {r["ticker"] for r in read_picks(s.journal_path)
                if r.get("kind") == "official" and r.get("session_date") == args.date.isoformat()}
    recs = pure_records(Store(s.db_path), args.date, datetime.now(mc.NY), official_tickers=official)
    for r in recs:
        print(f"{r['setup']:13} {'▲' if r['direction'] > 0 else '▼'} {r['ticker']:6} {r['contract']:22} "
              f"${r['premium'] / 1e6:.2f}M{' · official' if r['also_official'] else ''}")
    if args.dry_run:
        return 0
    n = write_pure(s.journal_path.parent / "pure.jsonl", recs)
    print(f"{len(recs)} pure buys, {n} new{' (reconstructed)' if recs and recs[0]['reconstructed'] else ''}")
    return 0
