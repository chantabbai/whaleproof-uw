from __future__ import annotations

import argparse
from datetime import date, datetime, time

from whaleproof import market_calendar as mc
from whaleproof.config import load_settings
from whaleproof.core.checks.base import human
from whaleproof.core.data_layer.client import UWClient
from whaleproof.core.data_layer.store import Store
from whaleproof.core.journal.chain import append_pick, read_picks
from whaleproof.core.journal.pure import pure_records, write_pure
from whaleproof.core.verdict.scan import pick_record, run_scan, select_go
from whaleproof.core.verdict.weights import CURRENT, load_weights


OPEN = time(9, 30)


def official_allowed(d: date, now: datetime) -> bool:
    """Official picks only for the last completed session, and only before the next session's open."""
    entry_open = datetime.combine(mc.next_session(d), OPEN, tzinfo=mc.NY)
    return d == mc.last_completed_session(now) and now.astimezone(mc.NY) < entry_open


def needs_catch_up(store: Store, d: date) -> bool:
    """True when no official scan snapshot exists for session d (the 16:30 scan failed or never ran)."""
    return store.conn.execute("SELECT 1 FROM scan_result WHERE session_date=? AND kind='official'",
                              (d.isoformat(),)).fetchone() is None


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(prog="whaleproof scan")
    p.add_argument("--date", type=date.fromisoformat, default=None)
    p.add_argument("--top", type=int, default=5)
    p.add_argument("--weights", default=None)
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--catch-up", action="store_true",
                   help="20:10 ET: run only if today's 16:30 official scan left no snapshot (e.g. API limit hit)")
    args = p.parse_args(argv)
    s = load_settings()
    now = datetime.now(mc.NY)
    d = args.date or mc.last_completed_session(now)
    if args.catch_up and not needs_catch_up(Store(s.db_path), d):
        print(f"catch-up: official scan for {d} already done — nothing to do")
        return 0
    if not args.dry_run and not official_allowed(d, now):
        print(f"refusing official picks for {d}: only the last completed session, before the next open "
              f"(use --dry-run to inspect)")
        return 2
    weights = load_weights(args.weights) if args.weights else CURRENT
    client = UWClient(s.uw_api_key, s.live_request_cap)
    live_unusual = d == mc.last_completed_session(now)
    store = Store(s.db_path)
    verdicts = run_scan(client, store, d, weights, live_unusualness=live_unusual)
    if not args.dry_run:
        store.put_scan(d.isoformat(), "official", datetime.now(mc.NY).isoformat(), weights.version,
                       [pick_record(v, "official") | {"label": v.label} for v in verdicts])
    already = {r["pick_id"] for r in read_picks(s.journal_path)}
    go = select_go(verdicts, args.top)          # one per ticker, highest score (Amendment 10)
    print(f"session {d} · {len(verdicts)} evaluated · {len(go)} GO · weights {weights.version} "
          f"· requests today {human(client.usage.daily_count or 0)}")
    for v in verdicts[:15]:
        arrow = "▲" if v.direction > 0 else "▼"
        print(f"{v.label:5} {v.score:5.1f} (par {v.score_parity:5.1f}) {arrow} {v.ticker:6} {v.plan.contract:22} "
              f"cov {v.coverage:.2f} | {'; '.join(v.reasons_for[:2])}")
    if args.dry_run:
        return 0
    for v in go:
        rec = pick_record(v, "official")
        if rec["pick_id"] not in already:
            append_pick(s.journal_path, rec)
    print(f"journal: {s.journal_path}")
    # research track (separate journal): every pure-directional buy, no cap — never affects official picks
    pure = pure_records(store, d, datetime.now(mc.NY), official_tickers={v.ticker for v in go})
    n = write_pure(s.journal_path.parent / "pure.jsonl", pure)
    print(f"pure buys: {len(pure)} ({n} new) → {s.journal_path.parent / 'pure.jsonl'}")
    return 0
