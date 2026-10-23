"""Amendment 16: the Take list — ≤3 new per finalist per day, ≤10 open, 9:45 skips free the slot."""
from whaleproof.core.journal.take import MAX_OPEN, PER_FINALIST, take_plan


def c(pid, day, fids, prem, ticker=None, exit_by="2026-10-02", d=1):
    return {"pick_id": pid, "ticker": ticker or pid, "direction": d, "entry_session": day, "exit_by": exit_by,
            "finalists": fids, "premium": prem}


def test_ranking_per_finalist_cap_and_overlap_first():
    cands = [c("a", "2026-09-28", ["F.1"], 5e5), c("b", "2026-09-28", ["F.1"], 9e5), c("x", "2026-09-28", ["F.1"], 7e5),
             c("y", "2026-09-28", ["F.1"], 6e5), c("o", "2026-09-28", ["F.1", "F.2"], 1e5)]
    plan = take_plan(cands, fills={})
    assert PER_FINALIST == 3 and MAX_OPEN == 10
    # overlap first (o counts for F1), then b, x → F1 full; y and a over cap
    assert [p for p in ("o", "b", "x") if plan[p] == "take"] == ["o", "b", "x"]
    assert plan["y"] == "over cap" and plan["a"] == "over cap"


def test_overflow_goes_to_next_finalist_with_room():
    cands = [c(f"f{i}", "2026-09-28", ["F.1", "F.2"], 1e6 - i) for i in range(5)]
    plan = take_plan(cands, fills={})
    assert sum(v == "take" for v in plan.values()) == 5          # 3 counted on F1, 2 on F2


def test_one_per_stock_biggest_bet_wins():
    cands = [c("l", "2026-09-28", ["F.2"], 5e5, ticker="NVDA"), c("s", "2026-09-28", ["F.1"], 9e5, ticker="NVDA", d=-1)]
    plan = take_plan(cands, fills={})
    assert plan["s"] == "take" and plan["l"] == "same stock"


def test_945_skip_frees_the_slot_and_open_cap_carries_over():
    day1 = [c(f"d{i}", "2026-09-28", ["F.1", "F.2", "F.3"], 1e6 - i) for i in range(9)]
    day2 = [c("n1", "2026-09-29", ["F.1"], 9e5), c("n2", "2026-09-29", ["F.1"], 8e5), c("n3", "2026-09-29", ["F.1"], 7e5)]
    fills = {"n1": {"decision": "skip: wide spread"}, "n2": {"decision": "still a buy"}, "n3": {"decision": "still a buy"}}
    plan = take_plan(day1 + day2, fills)
    assert sum(plan[f"d{i}"] == "take" for i in range(9)) == 9       # 3 per finalist on day 1
    assert plan["n1"] == "skipped at 9:45" and plan["n2"] == "take"  # 9 open + n2 = 10
    assert plan["n3"] == "open limit"                               # would be the 11th open trade


def test_closed_trades_free_open_slots():
    old = [c(f"o{i}", "2026-09-21", ["F.1", "F.2", "F.3", "F.4"], 1e6 - i, exit_by="2026-09-25") for i in range(10)]
    plan = take_plan(old + [c("new", "2026-09-28", ["F.1"], 1e5)], fills={})
    assert plan["new"] == "take"
