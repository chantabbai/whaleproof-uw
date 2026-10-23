import json

from fastapi.testclient import TestClient

from whaleproof.api.app import create_app
from whaleproof.core.data_layer.store import Store
from whaleproof.core.journal.chain import append_pick


def _pick(pid, sess, ticker, d=1):
    return {"pick_id": pid, "kind": "official", "session_date": sess, "entry_session": "2026-09-28",
            "ticker": ticker, "direction": d, "score": 80.0, "score_parity": 79.0, "contract": f"{ticker}261016C00100000",
            "weights_version": "v0", "plan": {"entry_ref": 100.0, "invalidation": 95.0, "target": 110.0,
                                              "time_stop_sessions": 10, "structure": "long call"},
            "reasons_for": ["x"], "reasons_against": [], "checks": {"flow_quality": {"score": 0.9, "available": True}}}


def client(tmp_path):
    j, db, log = tmp_path / "picks.jsonl", tmp_path / "db.sqlite", tmp_path / "backfill.log"
    append_pick(j, _pick("old", "2026-09-24", "OLD"))
    append_pick(j, _pick("a", "2026-09-25", "NVDA"))
    append_pick(j, _pick("b", "2026-09-25", "PLTR", -1))
    append_pick(j, {"pick_id": "a", "kind": "confirmation", "status": "confirmed", "ratio": 0.8, "ticker": "NVDA"})
    st = Store(db)
    st.conn.execute("INSERT INTO pick_outcome VALUES (?,?,?)",
                    ("a", "t", json.dumps({"pick_id": "a", "status": "open", "return": 0.02,
                                           "weights_version": "v0", "kind": "official"})))
    st.conn.commit()
    st.set_checkpoint("day:2026-09-25", "done-v3")
    st.set_checkpoint("day:2026-09-24", "done-v2")
    log.write_text("2026-09-25: done (40 candidates) — requests today 1234\n")
    return TestClient(create_app(journal_path=j, db_path=db, log_path=log))


def test_latest_official_picks_with_confirmation_and_outcome(tmp_path):
    r = client(tmp_path).get("/api/picks").json()
    assert r["session_date"] == "2026-09-25" and [p["ticker"] for p in r["picks"]] == ["NVDA", "PLTR"]
    nv = r["picks"][0]
    assert nv["confirmation"]["status"] == "confirmed" and nv["outcome"]["return"] == 0.02
    assert r["picks"][1]["confirmation"] is None and r["picks"][1]["outcome"] is None


def test_scorecard_and_status(tmp_path):
    c = client(tmp_path)
    sc = c.get("/api/scorecard").json()
    assert sc["chain_valid"] is True and sc["overall"]["n"] == 1 and sc["picks_total"] == 3
    st = c.get("/api/status").json()
    assert st["backfill_days_done"] == 1 and st["backfill_last_line"].startswith("2026-09-25")
    assert st["requests_today"] == 1234
    assert st["backfill_start"] == "2024-10-01" and st["backfill_sessions_total"] > 490   # 2y of sessions


def test_empty_journal(tmp_path):
    c = TestClient(create_app(journal_path=tmp_path / "none.jsonl", db_path=tmp_path / "d.sqlite",
                              log_path=tmp_path / "none.log"))
    assert c.get("/api/picks").json() == {"session_date": None, "entry_session": None, "picks": []}
    assert c.get("/api/status").json()["requests_today"] is None


def _pure(pid, sess, ticker, setup, entry, recon=False):
    return {"pick_id": pid, "kind": "pure", "session_date": sess, "entry_session": entry, "ticker": ticker,
            "direction": 1, "setup": setup, "contract": f"{ticker}261016C00100000", "premium": 600000.0,
            "reconstructed": recon, "also_official": ticker == "NVDA"}


def test_pure_latest_session_grouped_with_outcomes_and_open_holds(tmp_path):
    j = tmp_path / "picks.jsonl"
    c = client(tmp_path)
    pure = tmp_path / "pure.jsonl"
    append_pick(pure, _pure("p0", "2026-09-24", "OLD", "sweep", "2026-09-25"))
    append_pick(pure, _pure("p1", "2026-09-25", "NVDA", "sweep", "2026-09-28"))
    append_pick(pure, _pure("p2", "2026-09-25", "AMD", "far_otm", "2026-09-28"))
    (tmp_path / "pure-scorecard.json").write_text(json.dumps({
        "card": {"by_setup": {"sweep": {"closed": 0, "open": 1}}, "all": {"closed": 0}},
        "outcomes": {"p0": {"pick_id": "p0", "status": "open", "return": 0.03},
                     "p1": {"pick_id": "p1", "status": "pending", "return": None}}}))
    r = c.get("/api/pure").json()
    assert j.exists() and r["session_date"] == "2026-09-25" and r["entry_session"] == "2026-09-28"
    assert set(r["by_setup"]) == {"sweep", "far_otm"}
    nv = r["by_setup"]["sweep"][0]
    assert nv["ticker"] == "NVDA" and nv["also_official"] and nv["outcome"]["status"] == "pending"
    assert [h["ticker"] for h in r["tracking"]] == ["OLD"]                 # earlier sessions still open
    assert r["scorecard"]["by_setup"]["sweep"]["open"] == 1 and r["count"] == 2


def test_pure_empty(tmp_path):
    r = client(tmp_path).get("/api/pure").json()
    assert r == {"session_date": None, "entry_session": None, "by_setup": {}, "tracking": [], "scorecard": None,
                 "count": 0}


def test_requests_today_uses_newest_log(tmp_path):
    import os
    import time as _t
    c = client(tmp_path)                                                    # backfill.log says 1234
    sched = tmp_path / "scheduler.log"
    sched.write_text("2026-05-19: done (40 candidates) — requests today 34724\n")
    later = _t.time() + 60
    os.utime(sched, (later, later))
    assert c.get("/api/status").json()["requests_today"] == 34724


def test_pure_rows_carry_oi_confirmation(tmp_path):
    c = client(tmp_path)
    pure = tmp_path / "pure.jsonl"
    append_pick(pure, _pure("p1", "2026-09-25", "NVDA", "sweep", "2026-09-28"))
    append_pick(pure, {"pick_id": "p1", "kind": "confirmation", "ticker": "NVDA", "status": "confirmed", "ratio": 0.9})
    r = c.get("/api/pure").json()
    assert r["count"] == 1 and r["by_setup"]["sweep"][0]["confirmation"]["status"] == "confirmed"


# ---------- Plan 2b task 1: option P&L, setups, analysis, check-a-ticker ----------
def _seed_alert(tmp_path, aid="al1", ticker="NVDA", chain="NVDA261016C00200000"):
    from tests.conftest import raw_alert
    from whaleproof.core.data_layer.models import alert_to_row, parse_alert
    st = Store(tmp_path / "db.sqlite")
    r = raw_alert(id=aid, ticker=ticker, option_chain=chain, created_at="2026-09-25T15:00:00Z")
    st.upsert_alerts([alert_to_row(parse_alert(r), r)])
    return st


def test_pure_rows_carry_option_pnl_estimate(tmp_path):
    c = client(tmp_path)
    _seed_alert(tmp_path)
    append_pick(tmp_path / "pure.jsonl", _pure("p1", "2026-09-25", "NVDA", "sweep", "2026-09-28")
                | {"contract": "NVDA261016C00200000", "source_alert_id": "al1"})
    row = c.get("/api/pure").json()["by_setup"]["sweep"][0]
    assert row["pnl"]["structure"] == "long call" and row["pnl"]["ret_target"] > 0 > row["pnl"]["ret_stop"]


def test_official_pick_pnl_fails_soft_without_alert(tmp_path):
    r = client(tmp_path).get("/api/picks").json()
    assert all(p["pnl"] is None for p in r["picks"])


def test_setups_and_analysis_endpoints(tmp_path):
    c = client(tmp_path)
    assert c.get("/api/analysis/holdout").status_code == 404
    assert c.get("/api/analysis/bogus").status_code == 404
    (tmp_path / "analysis-train.json").write_text(json.dumps(
        {"meta": {"phase": "train"}, "results": {"S.sweep": {"mean": 0.004, "tradeable": False, "status": "tested"}}}))
    (tmp_path / "backtest-simple.json").write_text(json.dumps(
        {"meta": {"start": "a"}, "summary": {"by_setup": {"sweep": {"n": 10, "win_rate": 0.6}}}}))
    assert c.get("/api/analysis/train").json()["results"]["S.sweep"]["mean"] == 0.004
    s = c.get("/api/setups").json()
    assert s["setups"]["sweep"]["n"] == 10 and s["verdicts"]["sweep"] == "not proven"


def test_check_a_ticker_is_cache_only(tmp_path):
    c = client(tmp_path)
    _seed_alert(tmp_path)
    r = c.get("/api/ticker/nvda").json()
    assert r["ticker"] == "NVDA" and r["alerts"][0]["option_chain"] == "NVDA261016C00200000"
    assert "bars" in r and "pure" in r
    assert c.get("/api/ticker/UNKNOWN").json()["alerts"] == []


def test_pnl_prices_our_own_contract_not_the_whales(tmp_path):
    """Bullish pick from a sold 3-week put: we buy a near-the-money call with room after the hold."""
    from whaleproof.api.app import option_pnl
    st = _seed_alert(tmp_path, chain="NVDA261016P00200000")
    rec = _pick("x", "2026-09-25", "NVDA") | {"contract": "NVDA261016P00200000", "source_alert_id": "al1"}
    rec["plan"] = rec["plan"] | {"entry_ref": 190.0, "target": 205.0, "invalidation": 183.0, "time_stop_sessions": 5}
    e = option_pnl(st, rec)
    assert e["structure"] == "long call" and e["contract"] == "NVDA261120C00190000" and e["ret_target"] > 0
    assert e["whale_contract"] == "NVDA261016P00200000" and e["option_rr"] is not None


def test_tomorrow_marks_which_go_ideas_became_picks(tmp_path):
    c = client(tmp_path)
    st = Store(tmp_path / "db.sqlite")
    rows = [{"pick_id": "a", "ticker": "NVDA", "label": "GO", "score_parity": 80},
            {"pick_id": "z", "ticker": "NVDA", "label": "GO", "score_parity": 79},
            {"pick_id": "y", "ticker": "AMD", "label": "GO", "score_parity": 71}]
    st.put_scan("2026-09-25", "official", "2026-09-25T16:30:00-04:00", "v0.6", rows)
    t = c.get("/api/tomorrow").json()
    go = {r["pick_id"]: r for r in t["go"]}
    assert go["a"]["picked"] and go["z"]["why_not"] == "another pick on this ticker ranked higher"
    assert go["y"]["why_not"] == "outside the top 5" and t["entry_session"] == "2026-09-28"


def test_option_result_so_far_and_row_extras(tmp_path):
    from whaleproof.api.app import option_mark, row_extras
    st = _seed_alert(tmp_path)
    st.put_metric("NVDA", "all", "earnings", ["2026-09-01", "2026-10-20"])
    rec = _pick("x", "2026-09-25", "NVDA") | {"contract": "NVDA261016C00200000", "source_alert_id": "al1"}
    rec["plan"] = rec["plan"] | {"entry_ref": 190.0, "time_stop_sessions": 5}
    up = option_mark(st, rec, {"entry": 190.0, "return": 0.03, "entry_date": "2026-09-28", "sessions_held": 2,
                               "exit_date": None, "status": "open"})
    assert up is not None and up > 0.03                                      # leverage: option moves more than stock
    assert option_mark(st, rec, {"status": "pending", "return": None}) is None
    x = row_extras(st, rec)
    assert x["issue_type"] == "Common Stock" and x["next_earnings"] == "2026-10-20"


def test_history_carries_contract_plan_and_confirmation(tmp_path):
    h = client(tmp_path).get("/api/history").json()
    a = next(r for r in h if r["pick_id"] == "a")
    assert a["contract"] == "NVDA261016C00100000" and a["plan"]["target"] == 110.0
    assert a["confirmation"]["status"] == "confirmed" and a["outcome"]["status"] == "open"


def test_parallel_requests_do_not_share_a_sqlite_connection(tmp_path):
    """The dashboard fetches several endpoints at once; one shared connection across threads returned garbage (500s)."""
    from concurrent.futures import ThreadPoolExecutor
    c = client(tmp_path)
    paths = ["/api/picks", "/api/history", "/api/status", "/api/scorecard"] * 60
    with ThreadPoolExecutor(16) as ex:
        codes = list(ex.map(lambda p: c.get(p).status_code, paths))
    assert set(codes) == {200}


def test_rows_carry_planned_exit_and_option_value(tmp_path):
    c = client(tmp_path)
    a = next(r for r in c.get("/api/history").json() if r["pick_id"] == "a")
    assert a["exit_by"] == "2026-10-09"                     # entry Mon 09-28 + 10-session time stop (entry = day 1)
    p = c.get("/api/picks").json()["picks"][0]
    assert p["exit_by"] == "2026-10-09" and p["value"] is None          # no cached alert → fail soft


def test_option_value_uses_contract_iv_and_trailing_rv(tmp_path):
    from whaleproof.api.app import option_value
    st = _seed_alert(tmp_path)                               # alert iv 0.45 on 2026-09-25
    st.put_metric("NVDA", "all", "vol_hist", [["2026-09-24", 0.5, 0.30, "2026-09-24"],
                                               ["2026-09-26", 0.5, 0.90, "2026-10-20"]])   # future window ignored
    rec = _pick("x", "2026-09-25", "NVDA") | {"contract": "NVDA261016C00200000", "source_alert_id": "al1"}
    v = option_value(st, rec)
    assert v["basis"] == "iv_rv" and round(v["iv_rv"], 2) == 1.5 and v["verdict"] == "rich"


def test_combos_endpoint(tmp_path):
    c = client(tmp_path)
    assert c.get("/api/combos").status_code == 404
    (tmp_path / "analysis-train-combos.json").write_text(json.dumps(
        {"ranked": [{"blocks": ["OI confirmed"], "score": 1.0}], "finalists": [], "baseline": {"n": 5}}))
    assert c.get("/api/combos").json()["ranked"][0]["blocks"] == ["OI confirmed"]


def test_finalists_endpoint_matches_todays_pure_buys(tmp_path):
    """Amendment 12 finalists applied to the live pure-buy list with the same block rules as the backtest."""
    c = client(tmp_path)
    st = _seed_alert(tmp_path)                                               # NVDA, iv 0.45, 2026-09-25
    st.put_metric("NVDA", "all", "vol_hist", [["2026-09-24", 0.5, 0.60, "2026-09-24"]])    # → option cheap
    pure = tmp_path / "pure.jsonl"
    base = {"kind": "pure", "session_date": "2026-09-25", "entry_session": "2026-09-28", "direction": 1,
            "premium": 2e6, "reconstructed": False, "also_official": False}
    append_pick(pure, base | {"pick_id": "p1", "ticker": "NVDA", "setup": "far_otm", "dte": 40, "otm_pct": 0.08,
                              "contract": "NVDA261016C00200000", "source_alert_id": "al1"})
    append_pick(pure, base | {"pick_id": "p2", "ticker": "AMD", "setup": "sweep", "dte": 40, "otm_pct": 0.09,
                              "contract": "AMD261016C00200000"})
    append_pick(pure, {"pick_id": "p1", "kind": "confirmation", "ticker": "NVDA", "status": "confirmed", "ratio": 0.8})
    f = {x["id"]: x for x in c.get("/api/finalists").json()["finalists"]}
    assert [t["ticker"] for t in f["F.1"]["trades"]] == ["NVDA"]            # confirmed + 40 days + 8% OTM
    assert [t["ticker"] for t in f["F.1"]["waiting"]] == ["AMD"]            # no 08:30 check yet → waiting
    assert [t["ticker"] for t in f["F.2"]["trades"]] == ["NVDA"]            # cheap + long (AMD value unknown)
    assert [t["ticker"] for t in f["F.3"]["trades"]] == ["NVDA"]
    assert f["F.1"]["name"] and f["F.1"]["exam"] is None


def test_finalist_lists_keep_one_trade_per_stock(tmp_path):
    c = client(tmp_path)
    pure = tmp_path / "pure.jsonl"
    base = {"kind": "pure", "session_date": "2026-09-25", "entry_session": "2026-09-28", "setup": "sweep", "dte": 40,
            "otm_pct": 0.08, "reconstructed": False, "also_official": False, "ticker": "MRVL"}
    append_pick(pure, base | {"pick_id": "up", "direction": 1, "premium": 3e6, "contract": "MRVL261016C00100000"})
    append_pick(pure, base | {"pick_id": "dn", "direction": -1, "premium": 1e6, "contract": "MRVL261016P00080000"})
    f1 = next(f for f in c.get("/api/finalists").json()["finalists"] if f["id"] == "F.1")
    assert [(t["ticker"], t["direction"]) for t in f1["waiting"]] == [("MRVL", 1)]    # bigger bet wins


def test_finalists_flag_stocks_in_more_than_one_list(tmp_path):
    c = client(tmp_path)
    st = _seed_alert(tmp_path, ticker="BE", chain="BE261016C00200000")
    st.put_metric("BE", "all", "vol_hist", [["2026-09-24", 0.5, 0.60, "2026-09-24"]])        # → option cheap
    append_pick(tmp_path / "pure.jsonl", {
        "pick_id": "b1", "kind": "pure", "ticker": "BE", "direction": 1, "setup": "far_otm", "dte": 40,
        "otm_pct": 0.2, "premium": 3e5, "session_date": "2026-09-25", "entry_session": "2026-09-28",
        "contract": "BE261016C00200000", "source_alert_id": "al1"})
    d = c.get("/api/finalists").json()
    f = {x["id"]: x for x in d["finalists"]}
    assert f["F.2"]["trades"][0]["also_in"] == ["F.1", "F.3"] and f["F.3"]["trades"][0]["also_in"] == ["F.1", "F.2"]
    assert f["F.1"]["waiting"][0]["also_in"] == ["F.2", "F.3"]
    assert d["overlap"] == [{"ticker": "BE", "direction": 1, "in": ["F.1", "F.2", "F.3"], "waiting": ["F.1"]}]


def test_rows_carry_oi_trail(tmp_path):
    c = client(tmp_path)
    st = Store(tmp_path / "db.sqlite")
    st.put_metric("NVDA261016C00100000", "2026-09-25", "oi", 1000)
    st.put_metric("NVDA261016C00100000", "2026-09-28", "oi", 2500)
    p = next(x for x in c.get("/api/picks").json()["picks"] if x["ticker"] == "NVDA")
    assert p["oi_trail"] == [{"date": "2026-09-25", "oi": 1000}, {"date": "2026-09-28", "oi": 2500}]
    h = next(x for x in c.get("/api/history").json() if x["pick_id"] == "a")
    assert h["oi_trail"][-1]["oi"] == 2500


def _mark(st, pid, day, tag, at, bid, ask, last=100.0, sym="NVDA261120C00100000"):
    st.put_mark(pid, day, tag, at, {"stock": {"last": last}, "whale": {"symbol": "W", "bid": 1.0, "ask": 1.1},
                                    "ours": {"symbol": sym, "bid": bid, "ask": ask}})


def test_live_block_after_open_decision_and_daily_marks(tmp_path):
    c = client(tmp_path)
    j, st = tmp_path / "picks.jsonl", Store(tmp_path / "db.sqlite")
    append_pick(j, {"pick_id": "a", "kind": "fill", "ticker": "NVDA", "created_at": "2026-09-28T13:45:01+00:00",
                    "decision": "skip: price ran", "reason": "voided one", "our_contract": "X"})
    append_pick(j, {"pick_id": "a", "kind": "fill_void", "created_at": "2026-09-28T13:46:00+00:00", "reason": "early"})
    append_pick(j, {"pick_id": "a", "kind": "fill", "ticker": "NVDA", "created_at": "2026-09-28T13:47:00+00:00",
                    "decision": "still a buy", "reason": "little overnight move", "our_contract": "NVDA261120C00100000"})
    _mark(st, "a", "2026-09-28", "early", "2026-09-28T13:35:00+00:00", 4.9, 5.0)      # before the 9:45 decision
    _mark(st, "a", "2026-09-28", "open", "2026-09-28T13:45:00+00:00", 5.1, 5.3)
    _mark(st, "a", "2026-09-28", "close", "2026-09-28T19:55:00+00:00", None, None)      # no quote: skipped as price
    _mark(st, "a", "2026-09-29", "close", "2026-09-29T19:55:00+00:00", 6.0, 6.2, last=104.0)
    nv = c.get("/api/picks").json()["picks"][0]
    lv = nv["live"]
    assert lv["decision"]["decision"] == "still a buy"                    # voided fill ignored, later one wins
    assert lv["contract"] == "NVDA261120C00100000"
    assert lv["paid"] == {"day": "2026-09-28", "tag": "open", "price": 5.3}    # 9:45 ask: first moment we can buy
    assert lv["paid_on_entry"] is True
    assert lv["now"] == {"day": "2026-09-29", "tag": "close", "price": 6.0, "stock": 104.0}  # bid at latest quoted
    assert abs(lv["change"] - (6.0 / 5.3 - 1)) < 1e-9
    assert round(lv["mid_first"], 6) == 5.2 and round(lv["mid_now"], 6) == 6.1                 # 9:35 capture not the baseline
    assert abs(lv["mid_change"] - (6.1 / 5.2 - 1)) < 1e-9
    assert abs(lv["spread"] - 0.2 / 6.1) < 1e-9 and lv["bought"] is True
    assert lv["hold_day"] == 2 and lv["hold_days"] == 10                    # overnight hold: day 2 of 10
    assert [m["tag"] for m in lv["marks"]] == ["early", "open", "close", "close"]
    assert c.get("/api/picks").json()["picks"][1]["live"] is None          # PLTR: no marks, no decision
    h = {r["pick_id"]: r for r in c.get("/api/history").json()}
    assert h["a"]["live"]["change"] == lv["change"]


def test_pure_rows_carry_live_block(tmp_path):
    c = client(tmp_path)
    append_pick(tmp_path / "pure.jsonl", _pure("p1", "2026-09-25", "NVDA", "sweep", "2026-09-28"))
    append_pick(tmp_path / "pure.jsonl", {"pick_id": "p1", "kind": "fill", "ticker": "NVDA",
                                          "created_at": "2026-09-28T13:45:00+00:00", "decision": "already moved",
                                          "reason": "went 70%", "our_contract": "NVDA261120C00100000"})
    _mark(Store(tmp_path / "db.sqlite"), "p1", "2026-09-28", "open", "2026-09-28T13:45:00+00:00", 2.0, 2.1)
    row = c.get("/api/pure").json()["by_setup"]["sweep"][0]
    assert row["live"]["decision"]["decision"] == "already moved" and row["live"]["paid"]["price"] == 2.1
    assert row["live"]["bought"] is False                                   # 9:45 check said don't buy
    _mark(Store(tmp_path / "db.sqlite"), "old", "2026-09-29", "early", "2026-09-29T13:35:00+00:00", 2.0, 2.1)
    old = {r["pick_id"]: r for r in c.get("/api/history").json()}["old"]
    assert old["live"]["paid_on_entry"] is False                            # marks began after entry: not a buy price


def test_holding_lists_every_open_trade_with_live_block(tmp_path):
    c = client(tmp_path)
    pure = tmp_path / "pure.jsonl"
    append_pick(pure, _pure("p1", "2026-09-25", "AMD", "far_otm", "2026-09-28") | {"dte": 45, "otm_pct": 0.2})
    append_pick(pure, _pure("p2", "2026-09-18", "OLDP", "sweep", "2026-09-21"))            # 5-day hold ended 09-25
    append_pick(pure, {"pick_id": "p1", "kind": "confirmation", "status": "confirmed", "ratio": 0.9, "ticker": "AMD"})
    _mark(Store(tmp_path / "db.sqlite"), "p1", "2026-09-28", "open", "2026-09-28T13:45:00+00:00", 2.0, 2.1)
    r = c.get("/api/holding?today=2026-09-29").json()
    by = {x["pick_id"]: x for x in r["rows"]}
    assert set(by) >= {"a", "b", "p1"} and "p2" not in by                   # official 10-day plans still open
    assert by["p1"]["group"] == "pure" and "F.1" in by["p1"]["finalists"]    # OI confirmed + 45 DTE + 20% OTM
    assert by["p1"]["live"]["paid"]["price"] == 2.1 and by["p1"]["exit_by"] == "2026-10-02"
    assert by["a"]["group"] == "official" and by["a"]["hold_day"] == 2
    assert by["p1"]["take"] == "take" and by["a"]["take"] is None and r["taken_open"] == 1      # Amendment 16
    card = c.get("/api/scorecard").json()["taken"]
    assert card["taken"]["closed"] == 0 and set(card) == {"taken", "all_finalist"}


def test_live_block_shows_last_close_before_entry(tmp_path):
    c = client(tmp_path)
    st = Store(tmp_path / "db.sqlite")
    _mark(st, "a", "2026-09-25", "scan", "2026-09-25T20:35:00+00:00", 2.0, 2.2)          # flow-day close, pre-entry
    lv = c.get("/api/picks").json()["picks"][0]["live"]
    assert lv["last_close"] == {"day": "2026-09-25", "bid": 2.0, "ask": 2.2, "mid": 2.1,
                                "contract": "NVDA261120C00100000"}
    assert lv["paid"] is None and lv["now"] is None and lv["hold_day"] is None and lv["marks"] == []
