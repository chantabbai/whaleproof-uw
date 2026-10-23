"""Flow health: is the money behind each pick still there?"""
from datetime import date, timedelta

from tests.conftest import raw_alert
from whaleproof.core.data_layer.models import Bar, alert_to_row, parse_alert
from whaleproof.core.journal.flow_health import flow_health
from whaleproof.core.journal.tracker import evaluate_pick_follow

D = date(2026, 9, 22)          # whale day (Tue); entry Wed 9/23
CH = "NVDA261016C00200000"


def seed(store, size=2000, **kw):
    r = raw_alert(id="w", created_at="2026-09-22T15:00:00Z", option_chain=CH, total_size=size, **kw)
    a = parse_alert(r)
    store.upsert_alerts([alert_to_row(a, r)])
    return {"pick_id": "p", "kind": "official", "session_date": "2026-09-22", "entry_session": "2026-09-23",
            "ticker": "NVDA", "direction": a.direction, "contract": CH, "source_alert_id": "w",
            "weights_version": "v0.5", "plan": {"invalidation": 180.0, "target": 210.0, "time_stop_sessions": 10}}


def oi(store, **by_day):
    for d, v in by_day.items():
        store.put_metric(CH, d.replace("_", "-"), "oi", v)


def alert(store, rid, day, chain=CH, ask="0", bid="490000", size=1500, typ="call"):
    r = raw_alert(id=rid, created_at=f"{day}T15:00:00Z", option_chain=chain, total_size=size, type=typ,
                  total_premium="500000", total_ask_side_prem=ask, total_bid_side_prem=bid)
    store.upsert_alerts([alert_to_row(parse_alert(r), r)])


def test_holding(store):
    p = seed(store)
    oi(store, **{"2026_09_22": 1000, "2026_09_23": 3000, "2026_09_24": 3100})
    h = flow_health(store, p, date(2026, 9, 24))
    assert h["state"] == "HOLDING" and h["oi_peak"] == 3100 and h["closed_pct"] == 0


def test_holding_is_early_with_one_reading_and_no_later_flow(store):
    p = seed(store)
    oi(store, **{"2026_09_23": 3000})                              # only the morning after the whale
    h = flow_health(store, p, date(2026, 9, 23), alerts_through=D)
    assert h["state"] == "HOLDING" and h["early"] is True and "no exit seen yet" in h["reason"]
    oi(store, **{"2026_09_24": 3050})                              # second reading → real holding
    h = flow_health(store, p, date(2026, 9, 24))
    assert h["state"] == "HOLDING" and h["early"] is False


def test_exited_by_oi(store):
    p = seed(store)
    oi(store, **{"2026_09_23": 3000, "2026_09_24": 3000, "2026_09_25": 1800})   # −1200 of 2000 size = 60%
    h = flow_health(store, p, date(2026, 9, 25))
    assert h["state"] == "EXITED" and round(h["closed_pct"], 2) == 0.6


def test_reducing_by_oi_or_selling(store):
    p = seed(store)
    oi(store, **{"2026_09_23": 3000, "2026_09_24": 2400})                         # 30% closed
    assert flow_health(store, p, date(2026, 9, 24))["state"] == "REDUCING"
    oi(store, **{"2026_09_24": 3000})
    alert(store, "s1", "2026-09-24", size=600)                                    # bid-side on same contract 30%
    h = flow_health(store, p, date(2026, 9, 24))
    assert h["state"] == "REDUCING" and round(h["selling_pct"], 2) == 0.3


def test_rolled_not_exited(store):
    p = seed(store)
    oi(store, **{"2026_09_23": 3000, "2026_09_25": 1000})
    alert(store, "r1", "2026-09-24", chain="NVDA261218C00210000", ask="490000", bid="0", size=1800)
    h = flow_health(store, p, date(2026, 9, 25))
    assert h["state"] == "ROLLED" and h["rolled_to"] == "NVDA261218C00210000"


def test_flow_reversed(store):
    p = seed(store)
    oi(store, **{"2026_09_23": 3000, "2026_09_24": 3000, "2026_09_25": 3000})
    for d in ("2026-09-24", "2026-09-25"):
        store.put_metric("NVDA", d, "net_prem", {"call": -8e6, "put": 2e6, "gross": 12e6})
    assert flow_health(store, p, date(2026, 9, 25))["state"] == "FLOW_REVERSED"


def test_point_in_time_ignores_future(store):
    p = seed(store)
    oi(store, **{"2026_09_23": 3000, "2026_09_24": 3000, "2026_09_28": 100})
    assert flow_health(store, p, date(2026, 9, 24))["state"] == "HOLDING"


def test_unknown_without_data(store):
    p = seed(store)
    assert flow_health(store, p, date(2026, 9, 24))["state"] == "UNKNOWN"


def test_follow_exit_rule_exits_next_open_after_signal():
    pick = {"pick_id": "p", "direction": 1, "entry_session": "2026-09-23", "weights_version": "v", "kind": "official",
            "plan": {"invalidation": 90.0, "target": 130.0, "time_stop_sessions": 10}}
    d0 = date(2026, 9, 23)
    bars = [Bar(d0 + timedelta(i), 100 + i, 101 + i, 99 + i, 100.5 + i, 1) for i in range(6)]
    states = {d0 + timedelta(2): "EXITED"}        # known on the morning of day index 2 → exit at that open
    r = evaluate_pick_follow(pick, bars, lambda d: states.get(d, "HOLDING"))
    assert r["status"] == "money_left" and r["exit_date"] == (d0 + timedelta(2)).isoformat()
    assert round(r["return"], 4) == round(102 / 100 - 1, 4)


def test_premarket_view_excludes_same_day_alerts(store):
    p = seed(store)
    oi(store, **{"2026_09_23": 3000, "2026_09_24": 3000})
    alert(store, "s1", "2026-09-24", size=1200)                       # sold during 9/24 session
    pre = flow_health(store, p, date(2026, 9, 24), alerts_through=date(2026, 9, 23))
    post = flow_health(store, p, date(2026, 9, 24))
    assert pre["state"] == "HOLDING" and post["state"] == "REDUCING"


def test_backtest_reports_follow_exit(store):
    from whaleproof.core.backtest.runner import render_report, run_backtest, summarize
    seed(store)
    store.put_ohlc("NVDA", [Bar(D + timedelta(days=k), 190, 191, 189, 190 + 0.1 * k, 1) for k in range(30)])
    oi(store, **{"2026_09_23": 3000, "2026_09_24": 800})
    rows, _ = run_backtest(store, D, D)
    assert rows[0].plan_follow_return is not None and rows[0].follow_status == "money_left"
    md = render_report(summarize(rows, 0), {"start": "a", "end": "b", "weights": "v"})
    assert "Exit rule comparison" in md


def test_health_command_and_api(store, tmp_path):
    from fastapi.testclient import TestClient
    from whaleproof.api.app import create_app
    from whaleproof.commands.health import update_health
    from whaleproof.core.journal.chain import append_pick
    p = seed(store)
    j = tmp_path / "picks.jsonl"
    append_pick(j, p)
    oi(store, **{"2026_09_23": 3000, "2026_09_25": 1500})
    out = update_health(None, store, j, date(2026, 9, 25), fetch=False)
    assert out[0]["state"] == "EXITED"
    c = TestClient(create_app(journal_path=j, db_path=store.path, log_path=tmp_path / "l"))
    assert c.get("/api/picks").json()["picks"][0]["health"]["state"] == "EXITED"
    moved = c.get("/api/money-moved").json()
    assert [m["ticker"] for m in moved] == ["NVDA"] and moved[0]["state"] == "EXITED"


def test_pure_buys_get_daily_health_until_cutoff(store, tmp_path):
    """OI fix 2: pure / finalist buys get the same daily 'is the money still in?' check, entry → 5th session."""
    from whaleproof.commands.health import update_health
    from whaleproof.core.journal.chain import append_pick
    p = seed(store)
    pure = tmp_path / "pure.jsonl"
    append_pick(pure, {k: v for k, v in p.items() if k != "plan"} | {"pick_id": "pp", "kind": "pure", "setup": "sweep"})
    oi(store, **{"2026_09_23": 3000, "2026_09_25": 1500})
    out = update_health(None, store, tmp_path / "none.jsonl", date(2026, 9, 25), fetch=False, pure_journal=pure)
    assert [(h["pick_id"], h["state"]) for h in out] == [("pp", "EXITED")]
    # after the 5-session cut-off (entry 9/23 → cut-off 9/29) it is no longer checked
    assert update_health(None, store, tmp_path / "none.jsonl", date(2026, 9, 30), fetch=False, pure_journal=pure) == []


def test_oi_trail_from_the_whale_day(store):
    """OI fix 1: the whale contract's open interest day by day, for the dashboard trail."""
    from whaleproof.core.journal.flow_health import oi_trail
    p = seed(store)
    oi(store, **{"2026_09_22": 1000, "2026_09_23": 3000, "2026_09_24": 3050, "2026_09_21": 5})
    assert oi_trail(store, p) == [{"date": "2026-09-22", "oi": 1000}, {"date": "2026-09-23", "oi": 3000},
                                  {"date": "2026-09-24", "oi": 3050}]
