"""`whaleproof quickstart`: fill an empty cache with the last few sessions (new install / fresh-key setup)."""
from __future__ import annotations

import argparse
from datetime import UTC, datetime

from whaleproof.config import load_settings
from whaleproof.core.data_layer.client import UWAuthError, UWBlocked, UWClient
from whaleproof.core.data_layer.store import Store
from whaleproof.desk.config import DAILY_LIMIT, LIVE_RESERVE
from whaleproof.desk.quickstart import last_sessions, run
from whaleproof.launcher import safe_console


def main(argv: list[str]) -> int:
    safe_console()   # '→' below must not crash a cp1252 Windows console
    p = argparse.ArgumentParser(prog="whaleproof quickstart",
                                description="Backfill the last few sessions so the dashboard and MCP tools have data.")
    p.add_argument("--sessions", type=int, default=5, help="completed sessions to fetch (default 5)")
    p.add_argument("--max-calls", type=int, default=None, help="hard cap on UW calls for this run (default: no cap)")
    args = p.parse_args(argv)
    s = load_settings()
    if not s.uw_api_key:
        print("No UW_API_KEY found: copy .env.example to .env and add your key, then rerun.")
        return 1
    s.db_path.parent.mkdir(parents=True, exist_ok=True)
    days = last_sessions(datetime.now(UTC), args.sessions)
    cap = f"at most {args.max_calls} UW calls" if args.max_calls is not None else "no UW call cap"
    print(f"Quick-start: {len(days)} sessions {days[-1]} → {days[0]}, {cap}", flush=True)
    client = UWClient(s.uw_api_key, daily_cap=DAILY_LIMIT - LIVE_RESERVE)
    try:
        res = run(client, Store(s.db_path), days, args.max_calls, log=lambda m: print(m, flush=True))
    except UWAuthError as e:
        print(f"UW refused the key: {e}")
        return 1
    except UWBlocked as e:
        print(f"Network blocked before UW (proxy/VPN?): {e}")
        return 1
    n = client.usage.daily_count
    print(f"Done: {res['calls']} UW calls this run" + (f" (key's count today: {n})" if n is not None else ""))
    if res["stopped"]:
        print(f"Stopped early: {res['stopped']}. Rerun the same command to resume (cached calls are free).")
    print("Next: scripts/desk.sh up  →  http://127.0.0.1:3100")
    return 0
