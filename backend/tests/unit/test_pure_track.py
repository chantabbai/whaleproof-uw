"""Live 'pure buys' forward track: every gate passer at the scan → separate hash-chained journal, 5-session hold."""
from datetime import date, datetime

from tests.conftest import raw_alert
from whaleproof import market_calendar as mc
from whaleproof.core.data_layer.models import Bar, alert_to_row, parse_alert
from whaleproof.core.journal.chain import read_picks, verify_chain
from whaleproof.core.backtest.runner import COST
from whaleproof.core.journal.pure import evaluate_hold, pure_records, pure_scorecard, write_pure

D = date(2026, 9, 22)   # Tue → entry Wed 09-23
SCAN_TIME = datetime(2026, 9, 22, 16, 35, tzinfo=mc.NY)


def put_alert(store, **over):
    r = raw_alert(**over)
    store.upsert_alerts([alert_to_row(parse_alert(r), r)])


def seed(store):
    put_alert(store, id="a", ticker="NVDA", created_at="2026-09-22T15:00:00Z", expiry="2026-10-16")
    put_alert(store, id="far", ticker="AMD", created_at="2026-09-22T15:00:00Z", underlying_price="100",
              strike="125", expiry="2026-10-16", option_chain="AMD261016C00125000")
    put_alert(store, id="sold", ticker="S", created_at="2026-09-22T15:00:00Z", total_ask_side_prem="50000",
              total_bid_side_prem="450000", option_chain="S261016C00200000")


def test_records_are_gate_passers_with_setup_and_entry(store):
    seed(store)
    recs = pure_records(store, D, SCAN_TIME, official_tickers={"NVDA"})
    by = {r["ticker"]: r for r in recs}
    assert set(by) == {"NVDA", "AMD"}                                       # sold call excluded
    assert by["AMD"]["setup"] == "far_otm" and by["NVDA"]["setup"] == "sweep"
    n = by["NVDA"]
    assert n["kind"] == "pure" and n["entry_session"] == "2026-09-23" and n["direction"] == 1
    assert n["also_official"] is True and by["AMD"]["also_official"] is False
    assert n["reconstructed"] is False and n["contract"] == "NVDA261016C00200000" and n["premium"] == 500000


def test_reconstructed_when_written_after_entry_open(store):
    seed(store)
    late = datetime(2026, 9, 23, 10, 0, tzinfo=mc.NY)
    assert all(r["reconstructed"] for r in pure_records(store, D, late))


def test_write_is_append_only_and_idempotent(store, tmp_path):
    seed(store)
    path = tmp_path / "pure.jsonl"
    recs = pure_records(store, D, SCAN_TIME)
    assert write_pure(path, recs) == 2 and write_pure(path, recs) == 0
    assert len(read_picks(path)) == 2 and verify_chain(path)


def bars(start_px, step, n=8, day0=date(2026, 9, 23)):
    days = [day0]
    while len(days) < n:
        days.append(mc.next_session(days[-1]))
    return [Bar(d, start_px + step * i, start_px + step * i + 1, start_px + step * i - 1,
                start_px + step * i + 0.5, 1) for i, d in enumerate(days)]


def test_evaluate_hold_five_sessions():
    pick = {"pick_id": "p", "ticker": "X", "direction": -1, "entry_session": "2026-09-23", "setup": "sweep"}
    assert evaluate_hold(pick, [])["status"] == "pending"
    b = bars(100, -1)                                    # falling → short wins
    o3 = evaluate_hold(pick, b[:3])
    assert o3["status"] == "open" and o3["sessions_held"] == 3
    o = evaluate_hold(pick, b)
    assert o["status"] == "closed" and o["exit_date"] == b[4].date.isoformat()
    assert abs(o["return"] - (-(b[4].close / b[0].open - 1) - COST)) < 1e-12 and o["return"] > 0


def test_scorecard_by_setup_excludes_reconstructed():
    picks = [{"pick_id": "1", "setup": "sweep", "reconstructed": False},
             {"pick_id": "2", "setup": "sweep", "reconstructed": False},
             {"pick_id": "3", "setup": "sweep", "reconstructed": True},
             {"pick_id": "4", "setup": "far_otm", "reconstructed": False}]
    outs = [{"pick_id": "1", "status": "closed", "return": 0.04}, {"pick_id": "2", "status": "closed", "return": -0.02},
            {"pick_id": "3", "status": "closed", "return": 0.5}, {"pick_id": "4", "status": "open", "return": 0.01}]
    card = pure_scorecard(picks, outs)
    sw = card["by_setup"]["sweep"]
    assert sw["closed"] == 2 and abs(sw["mean"] - 0.01) < 1e-12 and sw["win_rate"] == 0.5
    assert abs(sw["profit_factor"] - 2.0) < 1e-12
    assert card["by_setup"]["far_otm"] == {"closed": 0, "open": 1, "win_rate": None, "mean": None,
                                            "profit_factor": None}
    assert card["reconstructed_excluded"] == 1


def test_refresh_pure_fetches_prices_for_unclosed_and_writes_scorecard(store, tmp_path):
    import json
    from whaleproof.core.journal.pure import refresh_pure
    seed(store)
    path = tmp_path / "pure.jsonl"
    write_pure(path, pure_records(store, D, SCAN_TIME))

    class F:
        calls = []

        def get(self, p, params=None):
            self.calls.append(p)
            if p.endswith("/ohlc/1d"):
                return {"data": [{"date": b.date.isoformat(), "open": b.open, "high": b.high, "low": b.low,
                                  "close": b.close, "volume": 1, "market_time": "r"} for b in bars(100, 1)]}
            return {"data": []}
    f = F()
    card = refresh_pure(f, store, path, date(2026, 10, 5))
    assert sorted(c for c in f.calls if c.endswith("ohlc/1d")) == ["/api/stock/AMD/ohlc/1d", "/api/stock/NVDA/ohlc/1d"]
    saved = json.loads((tmp_path / "pure-scorecard.json").read_text())
    assert saved["card"] == card and set(saved["outcomes"]) == {r["pick_id"] for r in read_picks(path)}
    assert card["all"]["closed"] == 2 and card["all"]["win_rate"] == 1.0
    f.calls.clear()
    refresh_pure(f, store, path, date(2026, 10, 6))
    assert f.calls == []                                                    # all closed → no more fetching


class BarsFake:
    def __init__(self, raise_after=None):
        self.calls, self.raise_after = [], raise_after

    def get(self, p, params=None):
        from whaleproof.core.data_layer.client import UWBudgetExceeded
        if self.raise_after is not None and len(self.calls) >= self.raise_after:
            raise UWBudgetExceeded("cap")
        self.calls.append(p)
        if p.endswith("/ohlc/1d"):
            return {"data": [{"date": b.date.isoformat(), "open": b.open, "high": b.high, "low": b.low,
                              "close": b.close, "volume": 1, "market_time": "r"} for b in bars(100, 1)]}
        return {"data": []}


def test_refresh_skips_not_yet_entered_and_fetches_earnings_once(store, tmp_path):
    from whaleproof.core.journal.pure import refresh_pure
    seed(store)
    path = tmp_path / "pure.jsonl"
    write_pure(path, pure_records(store, D, SCAN_TIME))
    f = BarsFake()
    refresh_pure(f, store, path, D)                                         # scan evening: entry is tomorrow
    assert f.calls == []
    refresh_pure(f, store, path, date(2026, 9, 24))
    assert sum(c.endswith("ohlc/1d") for c in f.calls) == 2 and sum("earnings" in c for c in f.calls) == 2
    f.calls.clear()
    refresh_pure(f, store, path, date(2026, 9, 25))
    assert not any("earnings" in c for c in f.calls)                        # earnings not re-pulled


def test_refresh_stops_cleanly_on_budget(store, tmp_path):
    from whaleproof.core.journal.pure import refresh_pure
    seed(store)
    path = tmp_path / "pure.jsonl"
    write_pure(path, pure_records(store, D, SCAN_TIME))
    card = refresh_pure(BarsFake(raise_after=1), store, path, date(2026, 10, 5))
    assert card["budget_stopped"] is True


def test_hold_return_is_net_of_cost():
    from whaleproof.core.backtest.runner import COST
    pick = {"pick_id": "p", "ticker": "X", "direction": 1, "entry_session": "2026-09-23", "setup": "sweep"}
    b = bars(100, 1)
    assert abs(evaluate_hold(pick, b)["return"] - ((b[4].close / b[0].open - 1) - COST)) < 1e-12


# ---------- next-morning OI confirmation for pure buys ----------
def test_confirm_pure_buys_preopen(store, tmp_path):
    from datetime import timezone
    from whaleproof.commands.confirm import confirm_picks
    seed(store)
    path = tmp_path / "pure.jsonl"
    write_pure(path, pure_records(store, D, SCAN_TIME))
    nv = next(r for r in read_picks(path) if r["ticker"] == "NVDA")
    store.put_metric(nv["contract"], D, "oi", 1000)
    store.put_metric(nv["contract"], date(2026, 9, 23), "oi", 2600)       # +1600 on 2000 traded → 0.8
    now = datetime(2026, 9, 23, 12, 30, tzinfo=timezone.utc)                # 08:30 ET on entry day
    out = confirm_picks(None, store, path, now, fetch=False, kind="pure")
    by = {r["ticker"]: r for r in out}
    assert by["NVDA"]["status"] == "confirmed" and by["AMD"]["status"] == "unavailable"
    assert confirm_picks(None, store, path, now, fetch=False, kind="pure") == []   # once only
    assert verify_chain(path)
    # confirmation records never count as picks
    assert write_pure(path, pure_records(store, D, SCAN_TIME)) == 0


def test_refresh_and_scorecard_ignore_confirmations_and_split_by_oi(store, tmp_path):
    from whaleproof.core.journal.chain import append_pick
    from whaleproof.core.journal.pure import refresh_pure
    seed(store)
    path = tmp_path / "pure.jsonl"
    write_pure(path, pure_records(store, D, SCAN_TIME))
    nv = next(r for r in read_picks(path) if r["ticker"] == "NVDA")
    append_pick(path, {"pick_id": nv["pick_id"], "kind": "confirmation", "ticker": "NVDA", "status": "confirmed",
                       "ratio": 0.8})
    card = refresh_pure(BarsFake(), store, path, date(2026, 10, 5))
    assert card["all"]["closed"] == 2
    assert card["by_confirmation"]["confirmed"]["closed"] == 1
    assert card["by_confirmation"]["unknown"]["closed"] == 1                # AMD: never confirmed


def test_pure_scorecard_split_by_after_open_check():
    picks = [{"pick_id": "1", "setup": "sweep"}, {"pick_id": "2", "setup": "sweep"}]
    outs = [{"pick_id": "1", "status": "closed", "return": 0.04}, {"pick_id": "2", "status": "closed", "return": -0.02}]
    fills = {"1": {"decision": "still a buy"}, "2": {"decision": "already moved"}}
    card = pure_scorecard(picks, outs, fills=fills)
    assert card["by_after_open"]["bought"]["closed"] == 1 and card["by_after_open"]["skipped at 9:45"]["closed"] == 1
    assert card["all"]["closed"] == 2
