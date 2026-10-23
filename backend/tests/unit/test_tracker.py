from datetime import date, timedelta

from whaleproof.core.data_layer.models import Bar
from whaleproof.core.journal.tracker import evaluate_pick, scorecard

PICK = {"pick_id": "p", "direction": 1, "entry_session": "2026-09-28", "weights_version": "v0",
        "kind": "official", "plan": {"invalidation": 95.0, "target": 110.0, "time_stop_sessions": 3}}


def bar(d, o, h, l, c):
    return Bar(d, o, h, l, c, 1)


D = date(2026, 9, 28)


def test_pending_before_entry():
    assert evaluate_pick(PICK, [])["status"] == "pending"


def test_target_hit():
    r = evaluate_pick(PICK, [bar(D, 100, 104, 99, 103), bar(D + timedelta(1), 103, 111, 102, 109)])
    assert r["status"] == "target" and round(r["return"], 3) == 0.1


def test_invalidation_checked_before_target_same_bar():
    r = evaluate_pick(PICK, [bar(D, 100, 112, 94, 100)])
    assert r["status"] == "invalidated" and round(r["return"], 3) == -0.05


def test_gap_through_invalidation_fills_at_open():
    r = evaluate_pick(PICK, [bar(D, 100, 101, 99, 100), bar(D + timedelta(1), 90, 91, 88, 89)])
    assert r["status"] == "invalidated" and round(r["return"], 3) == -0.1


def test_time_stop_and_open():
    bars = [bar(D + timedelta(i), 100, 101, 99, 100 + i) for i in range(3)]
    assert evaluate_pick(PICK, bars[:2])["status"] == "open"
    r = evaluate_pick(PICK, bars)
    assert r["status"] == "time_stop" and round(r["return"], 3) == 0.02


def test_bearish_mirrors():
    bear = {**PICK, "direction": -1, "plan": {"invalidation": 105.0, "target": 90.0, "time_stop_sessions": 5}}
    r = evaluate_pick(bear, [bar(D, 100, 101, 89, 90)])
    assert r["status"] == "target" and round(r["return"], 3) == 0.1


def test_scorecard_groups():
    outs = [{"status": "target", "return": 0.1, "weights_version": "v0", "kind": "official"},
            {"status": "invalidated", "return": -0.05, "weights_version": "v1", "kind": "official"},
            {"status": "pending", "return": None, "weights_version": "v1", "kind": "official"}]
    s = scorecard(outs)
    assert s["overall"]["n"] == 2 and s["by_version"]["v1"]["n"] == 1 and s["closed_count"] == 2


# Amendment 13: "overnight" day-1 rule — entry day only has an emergency stop at 2x the planned stop distance
OVN = {**PICK, "plan": {**PICK["plan"], "entry_ref": 100.0}}          # stop 95 → emergency 90


def test_overnight_ignores_day1_stop_and_target():
    bars = [bar(D, 100, 112, 94, 100), bar(D + timedelta(1), 100, 104, 99, 103)]
    assert evaluate_pick(OVN, bars)["status"] == "invalidated"                 # current rule: out on day 1
    r = evaluate_pick(OVN, bars, day1="overnight")
    assert r["status"] == "open" and round(r["return"], 3) == 0.03 and r["sessions_held"] == 2


def test_overnight_emergency_stop_day1_and_gap_fill():
    r = evaluate_pick(OVN, [bar(D, 100, 101, 89, 90)], day1="overnight")
    assert r["status"] == "invalidated" and round(r["return"], 3) == -0.1 and r["sessions_held"] == 1
    r = evaluate_pick(OVN, [bar(D, 85, 86, 84, 85)], day1="overnight")         # gapped through: fill at the open
    assert r["status"] == "invalidated" and round(r["return"], 3) == 0.0     # entry is that open → 0 from entry


def test_overnight_normal_rules_from_day2():
    r = evaluate_pick(OVN, [bar(D, 100, 101, 99, 100), bar(D + timedelta(1), 100, 111, 99, 109)], day1="overnight")
    assert r["status"] == "target" and r["sessions_held"] == 2
    bear = {**OVN, "direction": -1, "plan": {"invalidation": 105.0, "target": 90.0, "time_stop_sessions": 5,
                                             "entry_ref": 100.0}}              # emergency 110
    r = evaluate_pick(bear, [bar(D, 100, 108, 89, 100)], day1="overnight")
    assert r["status"] == "open"
    r = evaluate_pick(bear, [bar(D, 100, 111, 99, 110)], day1="overnight")
    assert r["status"] == "invalidated" and round(r["return"], 3) == -0.1


def test_after_open_groups_and_scorecard_split():
    """Amendment 14: bought vs skipped at 9:45 (and older picks with no check); 'overall' stays all picks."""
    from whaleproof.core.journal.tracker import after_open_group, after_open_fills
    recs = [{"pick_id": "a", "kind": "fill", "decision": "skip: price ran"},
            {"pick_id": "a", "kind": "fill_void"},
            {"pick_id": "a", "kind": "fill", "decision": "still a buy"},
            {"pick_id": "b", "kind": "fill", "decision": "skip: wide spread"}]
    fills = after_open_fills(recs)
    assert after_open_group(fills, "a") == "bought" and after_open_group(fills, "b") == "skipped at 9:45"
    assert after_open_group(fills, "c") == "no 9:45 check"
    outs = [{"pick_id": "a", "status": "target", "return": 0.1, "weights_version": "v0", "kind": "official"},
            {"pick_id": "b", "status": "invalidated", "return": -0.05, "weights_version": "v0", "kind": "official"},
            {"pick_id": "c", "status": "open", "return": 0.01, "weights_version": "v0", "kind": "official"}]
    s = scorecard(outs, fills)
    assert s["overall"]["n"] == 3
    assert s["by_after_open"]["bought"]["n"] == 1 and s["by_after_open"]["skipped at 9:45"]["n"] == 1
    assert scorecard(outs)["by_after_open"]["no 9:45 check"]["n"] == 3
