from __future__ import annotations

from datetime import datetime, timezone

from whaleproof.commands.backfill import backfill_complete
from whaleproof.config import load_settings
from whaleproof.core.budget import intraday_enabled
from whaleproof.core.data_layer.client import UWClient
from whaleproof.core.data_layer.store import Store
from whaleproof.core.journal.chain import append_pick, read_picks
from whaleproof.core.verdict.intraday import in_intraday_window, run_intraday
from whaleproof.core.verdict.scan import pick_record
from whaleproof.core.verdict.weights import CURRENT


def new_intraday(rows: list[dict], vs: list, journal: list[dict]) -> list[dict]:
    """GO rows not yet journaled, one per ticker per session (Amendment 10): best score wins, and a ticker that
    already has an intraday pick this session is skipped."""
    already = {r["pick_id"] for r in journal}
    taken = {(r["ticker"], r["session_date"]) for r in journal if r.get("kind") == "intraday"}
    out = []
    for r, v in sorted(zip(rows, vs), key=lambda t: (-t[1].score_parity, t[1].ticker)):
        key = (r["ticker"], r["session_date"])
        if v.label == "GO" and r["pick_id"] not in already and key not in taken:
            taken.add(key)
            out.append(r)
    return out


def main(argv: list[str]) -> int:
    now = datetime.now(timezone.utc)
    if not in_intraday_window(now):
        print("outside intraday window (09:45–15:30 ET on trading days)")
        return 0
    s = load_settings()
    store = Store(s.db_path)
    if not intraday_enabled(backfill_complete(store)):
        print("intraday feed paused: history backfill has priority until complete (WHALEPROOF_INTRADAY=on to force)")
        return 0
    vs = run_intraday(UWClient(s.uw_api_key, s.live_request_cap), store, now, CURRENT)
    rows = [pick_record(v, "intraday") | {"label": v.label} for v in vs]
    if vs:
        store.put_scan(vs[0].session_date.isoformat(), "intraday", now.isoformat(), CURRENT.version, rows)
    new = new_intraday(rows, vs, read_picks(s.journal_path))
    for r in new:
        r.pop("label", None)
        append_pick(s.journal_path, r)
    print(f"intraday {now.isoformat()} · {len(vs)} scored · {len(new)} new GO")  # small counts
    return 0
