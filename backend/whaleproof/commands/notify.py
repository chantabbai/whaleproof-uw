"""Post the latest official picks + journal chain head to a Discord webhook (public timestamp proof).

Only derived output is posted (tickers, direction, score, plan levels) — never raw UW data.
"""
from __future__ import annotations

import os

import httpx

from whaleproof.config import load_settings
from whaleproof.core.journal.chain import read_picks

DISCLAIMER = "_Not investment advice. Educational project._"


def build_message(picks: list[dict]) -> str:
    official = [p for p in picks if p.get("kind") == "official"]
    if not official:
        return f"🐋 **WhaleProof** — No official picks yet.\n{DISCLAIMER}"
    session = max(p["session_date"] for p in official)
    today = [p for p in official if p["session_date"] == session]
    lines = [f"🐋 **WhaleProof official picks** — from {session} flow, entry at {today[0]['entry_session']} open "
             f"(weights {today[0]['weights_version']})"]
    for p in today:
        arrow = "🟢 LONG" if p["direction"] > 0 else "🔴 SHORT"
        plan = p["plan"]
        lines.append(f"{arrow} **{p['ticker']}** · score {p['score']:.1f} · `{p['contract']}` · "
                     f"target {plan['target']} · invalidation {plan['invalidation']} · "
                     f"max {plan['time_stop_sessions']} sessions")
    lines.append(f"Journal chain head: `{picks[-1]['hash'][:16]}` ({len(picks)} picks total)")
    lines.append(DISCLAIMER)
    return "\n".join(lines)[:2000]


def post(url: str, content: str) -> bool:
    if not url:
        return False
    r = httpx.post(url, json={"content": content}, timeout=15)
    return r.status_code in (200, 204)


def main(argv: list[str]) -> int:
    s = load_settings()
    msg = build_message(read_picks(s.journal_path))
    ok = post(os.environ.get("DISCORD_WEBHOOK_URL", "").strip(), msg)
    print(msg if not ok else "posted to Discord")
    return 0
