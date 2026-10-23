import json
from datetime import datetime, timezone

from whaleproof.core.data_layer.context import AlertContext
from whaleproof.core.data_layer.models import GexLevels
from whaleproof.core.journal.chain import append_pick, read_picks, verify_chain
from whaleproof.core.verdict.scan import pick_record
from whaleproof.core.verdict.verdict import evaluate


def test_chain_appends_links_and_verifies(tmp_path):
    p = tmp_path / "picks.jsonl"
    a = append_pick(p, {"pick_id": "1", "ticker": "NVDA"})
    b = append_pick(p, {"pick_id": "2", "ticker": "AMD"})
    assert a["prev_hash"] == "GENESIS" and b["prev_hash"] == a["hash"]
    assert [r["pick_id"] for r in read_picks(p)] == ["1", "2"] and verify_chain(p)


def test_tampering_breaks_chain(tmp_path):
    p = tmp_path / "picks.jsonl"
    append_pick(p, {"pick_id": "1", "ticker": "NVDA"})
    append_pick(p, {"pick_id": "2", "ticker": "AMD"})
    lines = p.read_text().splitlines()
    rec = json.loads(lines[0]); rec["ticker"] = "TSLA"; lines[0] = json.dumps(rec)
    p.write_text("\n".join(lines) + "\n")
    assert not verify_chain(p)


def test_truncated_last_line_is_detected_and_earlier_lines_intact(tmp_path):
    p = tmp_path / "picks.jsonl"
    append_pick(p, {"pick_id": "1"})
    with p.open("a") as f:
        f.write('{"pick_id": "2", "trunc')
    assert not verify_chain(p)
    assert [r["pick_id"] for r in read_picks(p)] == ["1"]


def test_pick_record_shape(make_alert):
    a = make_alert(total_premium="2000000", total_ask_side_prem="1950000", total_bid_side_prem="50000",
                   underlying_price="100", strike="105", iv="0.5", expiry="2026-10-16")
    c = AlertContext(a, datetime(2026, 9, 25, 20, 15, tzinfo=timezone.utc), GexLevels(125, 90, 95, 100),
                     [(98.0, 9000)], 15, 95, 6e8, [], 3, 100.0)
    rec = pick_record(evaluate(c), "official")
    assert rec["entry_session"] == "2026-09-28" and rec["kind"] == "official"
    assert rec["checks"]["flow_quality"]["available"] is True
    assert rec["score_parity"] != rec["score"]  # unusualness (live-only) excluded from parity
    json.dumps(rec)


def test_needs_catch_up_only_when_no_official_snapshot_for_session(store):
    from datetime import date
    from whaleproof.commands.scan import needs_catch_up
    d = date(2026, 9, 28)
    assert needs_catch_up(store, d) is True
    store.put_scan("2026-09-25", "official", "2026-09-25T16:35:00-04:00", "v0", [])
    assert needs_catch_up(store, d) is True                                 # yesterday's snapshot doesn't count
    store.put_scan("2026-09-28", "intraday", "2026-09-28T15:30:00-04:00", "v0.5", [])
    assert needs_catch_up(store, d) is True                                 # intraday doesn't count
    store.put_scan("2026-09-28", "official", "2026-09-28T16:36:00-04:00", "v0.5", [])
    assert needs_catch_up(store, d) is False


def test_live_candidates_are_gated(store):
    from datetime import date, timedelta
    from tests.conftest import raw_alert
    from whaleproof import market_calendar as mc
    from whaleproof.core.data_layer.models import alert_to_row, parse_alert
    from whaleproof.core.verdict.scan import live_candidates
    for rid, tkr, ask, bid in (("b", "NVDA", "450000", "50000"), ("s", "AMD", "20000", "480000")):
        r = raw_alert(id=rid, ticker=tkr, created_at="2026-09-25T15:00:00Z", total_ask_side_prem=ask,
                      total_bid_side_prem=bid, option_chain=f"{tkr}261016C00200000")
        store.upsert_alerts([alert_to_row(parse_alert(r), r)])
    d = date(2026, 9, 25)
    as_of = mc.session_close(d) + timedelta(minutes=15)
    assert [a.id for a in live_candidates(store, d, as_of)] == ["b"]


def test_current_weights_are_v06_same_as_v05():
    from whaleproof.core.verdict.weights import CURRENT, V05
    assert CURRENT.version == "v0.6" and V05.version == "v0.5" and CURRENT.w == V05.w


def test_gate_runs_before_biggest_per_ticker_pick(store):
    """A bigger sold put (bullish by side) must not evict a smaller clean call buy on the same ticker+direction."""
    from datetime import date, timedelta
    from tests.conftest import raw_alert
    from whaleproof import market_calendar as mc
    from whaleproof.core.data_layer.models import alert_to_row, parse_alert
    from whaleproof.core.verdict.scan import live_candidates
    buy = raw_alert(id="b", created_at="2026-09-25T15:00:00Z", total_premium="300000",
                    total_ask_side_prem="280000", total_bid_side_prem="20000")
    sold = raw_alert(id="s", created_at="2026-09-25T16:00:00Z", type="put", strike="180",
                     option_chain="NVDA261016P00180000", total_premium="900000",
                     total_ask_side_prem="20000", total_bid_side_prem="880000")
    for r in (buy, sold):
        store.upsert_alerts([alert_to_row(parse_alert(r), r)])
    d = date(2026, 9, 25)
    assert [a.id for a in live_candidates(store, d, mc.session_close(d) + timedelta(minutes=15))] == ["b"]
