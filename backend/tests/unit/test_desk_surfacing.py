"""Surfacing (owner 10-07): today's signals while the day is still forming, and the ones that went back under."""
from datetime import UTC, datetime

from whaleproof.desk import surfacing as S

T1 = datetime(2026, 10, 7, 15, 0, tzinfo=UTC)
T2 = datetime(2026, 10, 7, 17, 10, tzinfo=UTC)
T3 = datetime(2026, 10, 7, 18, 0, tzinfo=UTC)


def sig(t, d=1, premium=1e6, tier="whale"):
    return {"ticker": t, "direction": d, "premium": premium, "tier": tier, "label": "Whale"}


def bet(t, d=1, verdict="signal", reason=""):
    return {"ticker": t, "direction": d, "verdict": verdict, "reason": reason, "premium": 1e6}


def test_a_signal_that_stops_passing_went_back_under_with_its_reason():
    log = S.update(S.empty("2026-10-07"), [sig("HPE"), sig("NVDA")], [bet("HPE"), bet("NVDA")], T1)
    log = S.update(log, [sig("NVDA")], [bet("HPE", verdict="gate", reason="paired with a sell"), bet("NVDA")], T2)
    under = S.went_under(log)
    assert [u["ticker"] for u in under] == ["HPE"]
    assert under[0]["reason"] == "paired with a sell" and under[0]["went_under"] == T2.isoformat()
    assert under[0]["first_seen"] == T1.isoformat()


def test_a_bet_that_vanished_from_the_flow_and_one_that_resurfaced():
    log = S.update(S.empty("2026-10-07"), [sig("HPE"), sig("AMD")], [], T1)
    log = S.update(log, [], [], T2)
    assert {u["reason"] for u in S.went_under(log)} == {"no longer in today's flow"}
    log = S.update(log, [sig("AMD", premium=2e6)], [], T3)          # back above water: off the list, first_seen kept
    assert [u["ticker"] for u in S.went_under(log)] == ["HPE"]
    assert log["seen"]["AMD:1"]["first_seen"] == T1.isoformat() and log["seen"]["AMD:1"]["premium"] == 2e6


def test_newest_first_and_round_trips_through_a_file(tmp_path):
    log = S.update(S.empty("2026-10-07"), [sig("A"), sig("B")], [], T1)
    log = S.update(log, [sig("B")], [], T2)
    log = S.update(log, [], [], T3)
    assert [u["ticker"] for u in S.went_under(log)] == ["B", "A"]
    p = tmp_path / "surfacing-2026-10-07.json"
    S.save(p, log)
    assert S.load(p, "2026-10-07") == log and S.load(tmp_path / "nope.json", "2026-10-08") == S.empty("2026-10-08")
