import json

import httpx
import respx

from whaleproof.commands.notify import build_message, post
from whaleproof.core.journal.chain import append_pick, read_picks

HOOK = "https://discord.com/api/webhooks/1/abc"


def _pick(t, sess="2026-09-25", d=1):
    return {"pick_id": t, "kind": "official", "session_date": sess, "entry_session": "2026-09-28",
            "ticker": t, "direction": d, "score": 80.1, "contract": f"{t}261016C00100000", "weights_version": "v0",
            "plan": {"invalidation": 95.0, "target": 110.0, "time_stop_sessions": 10, "structure": "long call"},
            "reasons_for": ["big ask-side calls"]}


def test_message_lists_latest_session_picks_and_chain_head(tmp_path):
    p = tmp_path / "picks.jsonl"
    append_pick(p, _pick("OLD", sess="2026-09-24"))
    append_pick(p, _pick("NVDA"))
    last = append_pick(p, _pick("PLTR", d=-1))
    msg = build_message(read_picks(p))
    assert "NVDA" in msg and "PLTR" in msg and "OLD" not in msg
    assert last["hash"][:16] in msg and "Not investment advice" in msg and len(msg) <= 2000


def test_message_when_no_picks():
    assert "No official picks" in build_message([])


@respx.mock
def test_post_sends_content_and_skips_without_url():
    route = respx.post(HOOK).mock(return_value=httpx.Response(204))
    assert post(HOOK, "hi") is True
    assert json.loads(route.calls.last.request.content) == {"content": "hi"}
    assert post("", "hi") is False
