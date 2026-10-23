"""Daily real option marks for every open pick, entry day → cut-off (last day we hold the contract).
10:00 ET 'open' capture on the entry day also journals the after-open decision (no raw quotes in git);
15:55 ET 'close' capture marks the day; the cut-off day's close is the real exit."""
import json
from datetime import datetime

from whaleproof import market_calendar as mc
from whaleproof.commands import marks
from whaleproof.core.journal.chain import append_pick, read_picks

PLAN = {"entry_ref": 100.0, "invalidation": 95.0, "target": 110.0, "time_stop_sessions": 5, "structure": "long call"}


class FakeUW:
    """Answers stock-state and per-expiry chains; counts calls."""
    def __init__(self, last=101.0, oi=None):
        self.calls, self.last = [], last
        self.oi = oi or {}                                     # strike*1000 → open interest (default 500)

    def get(self, path, params=None):
        self.calls.append((path, dict(params or {})))
        if path.endswith("/stock-state"):
            return {"data": {"close": str(self.last), "open": "100.5", "prev_close": "100", "market_time": "r"}}
        exp = params["expiry"].replace("-", "")[2:]
        t = path.split("/")[3]
        return {"data": [{"option_symbol": f"{t}{exp}C{k:08d}", "nbbo_bid": "2.00", "nbbo_ask": "2.10",
                          "last_price": "2.05", "implied_volatility": "0.4", "delta": 0.5,
                          "open_interest": self.oi.get(k, 500)}
                         for k in (95000, 100000, 105000)]}


def setup(tmp_path):
    j = tmp_path / "picks.jsonl"
    append_pick(j, {"pick_id": "p1", "kind": "official", "ticker": "NVDA", "direction": 1, "session_date": "2026-09-25",
                    "entry_session": "2026-09-28", "contract": "NVDA261016C00105000", "plan": PLAN,
                    "weights_version": "v0.6"})
    append_pick(j, {"pick_id": "old", "kind": "official", "ticker": "OLD", "direction": 1, "session_date": "2026-09-10",
                    "entry_session": "2026-09-11", "contract": "OLD261016C00105000", "plan": PLAN,
                    "weights_version": "v0"})                                         # cut-off long past → not tracked
    return j


def at(day: str, hh: int, mm: int) -> datetime:
    return datetime.fromisoformat(f"{day}T{hh:02d}:{mm:02d}:00").replace(tzinfo=mc.NY)


def test_open_capture_marks_and_journals_decision(store, tmp_path):
    j = setup(tmp_path)
    uw = FakeUW(last=101.0)
    res = marks.run_marks(uw, store, [j], at("2026-09-28", 10, 0), "open")
    assert res["tracked"] == 1 and res["decisions"] == 1
    m = store.marks("p1")
    assert m[0]["tag"] == "open" and m[0]["day"] == "2026-09-28"
    assert m[0]["ours"]["symbol"].startswith("NVDA") and m[0]["ours"]["ask"] == 2.10 and m[0]["stock"]["last"] == 101.0
    fill = [r for r in read_picks(j) if r.get("kind") == "fill"]
    assert fill[0]["pick_id"] == "p1" and fill[0]["decision"] in {"still a buy", "skip: price ran"}
    assert "bid" not in json.dumps(fill[0]) and "ask" not in json.dumps(fill[0])      # no raw UW quotes in git
    marks.run_marks(uw, store, [j], at("2026-09-28", 10, 5), "open")                  # second run: no duplicate
    assert len([r for r in read_picks(j) if r.get("kind") == "fill"]) == 1


def test_close_capture_until_cutoff_and_budget_small(store, tmp_path):
    j = setup(tmp_path)
    uw = FakeUW()
    marks.run_marks(uw, store, [j], at("2026-10-02", 15, 55), "close")      # day 5 = cut-off (entry Mon = day 1)
    assert [m["tag"] for m in store.marks("p1")] == ["close"]
    assert len(uw.calls) <= 3                                                # 1 stock state + ≤2 chains per stock
    uw.calls.clear()
    res = marks.run_marks(uw, store, [j], at("2026-10-05", 15, 55), "close")    # after the cut-off
    assert res["tracked"] == 0 and uw.calls == []


def test_skips_non_trading_days(store, tmp_path):
    j = setup(tmp_path)
    assert marks.run_marks(FakeUW(), store, [j], at("2026-10-03", 10, 0), "open")["tracked"] == 0   # Saturday


def test_open_capture_refuses_before_945_and_voided_fills_can_be_redone(store, tmp_path):
    j = setup(tmp_path)
    assert marks.run_marks(FakeUW(), store, [j], at("2026-09-28", 9, 21), "open")["stopped"] == "before 09:45 ET"
    append_pick(j, {"pick_id": "p1", "kind": "fill", "decision": "still a buy"})               # a bad early fill
    append_pick(j, {"pick_id": "p1", "kind": "fill_void", "reason": "captured before the open"})
    res = marks.run_marks(FakeUW(), store, [j], at("2026-09-28", 10, 0), "open")
    assert res["decisions"] == 1                                                             # redone after void


def test_early_mark_after_the_open_without_decision(store, tmp_path):
    j = setup(tmp_path)
    assert marks.run_marks(FakeUW(), store, [j], at("2026-09-28", 9, 29), "early")["stopped"] == "before the 09:30 open"
    res = marks.run_marks(FakeUW(), store, [j], at("2026-09-28", 9, 35), "early")
    assert res["tracked"] == 1 and res["decisions"] == 0 and store.marks("p1")[0]["tag"] == "early"


def test_dead_strike_skipped_and_contract_locked_after_decision(store, tmp_path):
    """Amendment 17: our strike needs OI ≥ 100; once decided, the contract never changes even if OI moves."""
    j = setup(tmp_path)
    marks.run_marks(FakeUW(oi={100000: 0}), store, [j], at("2026-09-28", 10, 0), "open")
    fill = [r for r in read_picks(j) if r.get("kind") == "fill"][0]
    assert fill["our_contract"] == "NVDA261120C00095000"          # 100 strike dead → nearest liquid (tie → lower call)
    marks.run_marks(FakeUW(oi={95000: 0}), store, [j], at("2026-09-28", 15, 55), "close")
    assert store.marks("p1")[-1]["ours"]["symbol"] == "NVDA261120C00095000"   # locked despite OI change


def test_no_liquid_strike_journals_skip(store, tmp_path):
    j = setup(tmp_path)
    marks.run_marks(FakeUW(oi={95000: 0, 100000: 5, 105000: 0}), store, [j], at("2026-09-28", 10, 0), "open")
    fill = [r for r in read_picks(j) if r.get("kind") == "fill"][0]
    assert fill["decision"] == "skip: no liquid strike" and fill["our_contract"] is None


def test_undecided_trade_keeps_first_marked_contract(store, tmp_path):
    j = setup(tmp_path)
    marks.run_marks(FakeUW(), store, [j], at("2026-09-28", 9, 35), "early")        # no decision yet
    first = store.marks("p1")[0]["ours"]["symbol"]
    marks.run_marks(FakeUW(oi={100000: 0}), store, [j], at("2026-09-29", 15, 55), "close")
    assert store.marks("p1")[-1]["ours"]["symbol"] == first


def test_scan_mark_prices_tomorrows_picks_at_the_close(store, tmp_path):
    """Owner 09-29: today's picks show the real closing price of the option we'd buy (tag 'scan', after 16:00)."""
    j = setup(tmp_path)                                          # p1: flow Fri 09-25, entry Mon 09-28
    assert marks.run_marks(FakeUW(), store, [j], at("2026-09-25", 15, 30), "scan")["stopped"] == "before the 16:00 close"
    uw = FakeUW()
    res = marks.run_marks(uw, store, [j], at("2026-09-25", 16, 35), "scan")
    assert res["tracked"] == 1 and res["decisions"] == 0
    m = store.marks("p1")[0]
    assert m["tag"] == "scan" and m["day"] == "2026-09-25" and m["ours"]["ask"] == 2.10
    assert not [r for r in read_picks(j) if r.get("kind") == "fill"]
    assert marks.run_marks(FakeUW(), store, [j], at("2026-09-28", 16, 35), "scan")["tracked"] == 0   # already held


def test_scan_mark_once_per_pick(store, tmp_path):
    j = setup(tmp_path)
    marks.run_marks(FakeUW(), store, [j], at("2026-09-25", 16, 35), "scan")
    uw = FakeUW()
    assert marks.run_marks(uw, store, [j], at("2026-09-25", 20, 10), "scan")["tracked"] == 0 and uw.calls == []
