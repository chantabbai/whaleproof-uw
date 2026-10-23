"""Signal Desk API on a tiny temp cache: no UW key, no refresher thread — sections answer and user writes validate."""
from datetime import UTC

import pytest
from fastapi.testclient import TestClient

from tests.conftest import raw_alert
from whaleproof.api.app import create_app
from whaleproof.core.data_layer.store import Store
from whaleproof.desk.service import DeskService, data_day
from whaleproof.desk.userdb import UserDB


@pytest.fixture
def client(tmp_path):
    db = tmp_path / "c.sqlite"
    st = Store(db)
    from datetime import datetime, timedelta
    day = data_day(datetime.now(UTC))
    d, exp = day.isoformat(), (day + timedelta(days=45)).isoformat()
    st.upsert_alerts([{**raw_alert(id="w", ticker="AAA", underlying_price="100", strike="110", expiry=exp,
                                   total_premium="2000000", total_ask_side_prem="1950000", total_bid_side_prem="50000",
                                   created_at=f"{d}T15:00:00Z", option_chain="AAA270618C00110000"), "session_date": d}])
    (tmp_path / "journal").mkdir()
    svc = DeskService(db, "")                      # no key → cache only, nothing started
    app = create_app(tmp_path / "journal" / "picks.jsonl", db, tmp_path / "x.log",
                     desk=(svc, UserDB(tmp_path / "u.sqlite", tmp_path / "bk"), tmp_path / "rows"))
    svc.refresh(st)                                # no key → cache-only compute of today's signals
    return TestClient(app)


def test_sections_answer(client):
    for path in ("status", "today", "swing", "day", "watchlist", "journal", "methodology", "ticker/AAA"):
        assert client.get(f"/api/desk/{path}").status_code == 200, path
    t = client.get("/api/desk/today").json()
    assert t["funnel"]["raw"] == 1 and t["signals"][0]["ticker"] == "AAA"
    assert client.get("/api/desk/status").json()["live_enabled"] is False


def test_bad_inputs_rejected(client):
    assert client.get("/api/desk/ticker/DROP;TABLE").status_code == 400
    assert client.post("/api/desk/watchlist/bad!!").status_code == 400
    assert client.post("/api/desk/journal", json={"ticker": "AAPL", "entry_price": -5}).status_code in (400, 422)


def test_journal_snapshots_signal_and_exports_csv(client):
    client.get("/api/desk/today")
    r = client.post("/api/desk/journal", json={"ticker": "AAA", "direction": 1, "entry_price": 100, "stop": 95})
    assert r.status_code == 200
    tr = client.get("/api/desk/journal").json()["trades"][0]
    assert tr["signal"]["tier"] == "whale" and tr["signal"]["why"]
    assert "AAA" in client.get("/api/desk/journal.csv").text


def test_methodology_serves_compound_simulation(client, tmp_path):
    assert client.get("/api/desk/methodology").json()["compound"] is None        # no research file → None
    (tmp_path / "journal" / "research").mkdir(parents=True, exist_ok=True)
    (tmp_path / "journal" / "research" / "compound-stock-signals.json").write_text(
        '{"label": "exploratory", "curve": [{"d": "2023-11-03", "eq": 1.01, "spy": 1.0}]}')
    c = client.get("/api/desk/methodology").json()["compound"]
    assert c["label"] == "exploratory" and c["curve"][0]["eq"] == 1.01


def test_methodology_serves_beta_check(client, tmp_path):
    assert client.get("/api/desk/methodology").json()["beta"] is None
    (tmp_path / "journal" / "research").mkdir(parents=True, exist_ok=True)
    (tmp_path / "journal" / "research" / "beta-adjusted.json").write_text('{"holdout": {"signals": {"avg_beta": 2.4}}}')
    assert client.get("/api/desk/methodology").json()["beta"]["holdout"]["signals"]["avg_beta"] == 2.4


def test_period_labels_are_plain_words():
    from datetime import date

    from whaleproof.desk.history import period_label
    # every period names its months, so nobody has to guess which years "Sealed test" was (owner 10-13)
    assert period_label(date(2024, 3, 1)) == "Second sealed test (Oct 2023–Sep 2024)"
    assert period_label(date(2025, 3, 1)) == "Practice year (Oct 2024–Sep 2025, rules chosen here)"
    assert period_label(date(2026, 1, 5)) == "Sealed test (Oct 2025–May 2026)"
    assert period_label(date(2026, 8, 3)) == "Recent months (since Jun 2026)"


def test_tracker_serves_rows_and_csv(client):
    t = client.get("/api/desk/tracker").json()
    assert {"rows", "as_of", "priced_through", "last_close_update", "periods"} <= t.keys()
    for r in t["rows"]:                                   # today's AAA appears once its decision time has passed
        assert r["ticker"] == "AAA" and r["stock"]["status"] == "waiting" and r["period"] == "Live (from Sep 30, 2026)"
        assert set(r["stock"]["now"]) == {"entry", "price", "source", "at", "move", "net"}   # live mark for holds
    csv = client.get("/api/desk/tracker.csv").text
    assert csv.splitlines()[0].startswith("signal_day,ticker,period,tier")


def test_cold_cache_says_history_is_not_loaded(client):
    """Quick-start installs have no history rows: pages must not claim 'never passed in the 2-year history'."""
    assert client.get("/api/desk/ticker/NVDA").json()["history_loaded"] is False
    assert client.get("/api/desk/tracker").json()["history_loaded"] is False


def test_methodology_serves_holding_period_study(client, tmp_path):
    assert client.get("/api/desk/methodology").json()["holding"] is None
    (tmp_path / "journal" / "research").mkdir(parents=True, exist_ok=True)
    (tmp_path / "journal" / "research" / "holding-period.json").write_text('{"horizons": [5, 10], "periods": {}}')
    assert client.get("/api/desk/methodology").json()["holding"]["horizons"] == [5, 10]


def test_tracker_list_omits_daily_paths_served_per_row(client):
    """The list stays light: daily paths load only when a row is expanded."""
    for r in client.get("/api/desk/tracker").json()["rows"]:
        assert "path" not in r["stock"] and (r["option"] is None or "path" not in r["option"])
        p = client.get(f"/api/desk/tracker/{r['id']}/path").json()
        assert p["stock"] == [] and p["option"] == []                    # waiting: no prices yet
        assert p["why_lost"] is None                                     # only finished signals that lagged SPY
    assert client.get("/api/desk/tracker/nope/path").status_code == 404


def test_alerts_lists_every_bet_with_verdict_and_history(client):
    a = client.get("/api/desk/alerts").json()
    assert a["label"].startswith("History lookup")
    b = a["bets"][0]
    assert (b["ticker"], b["verdict"], b["bet_kind"], b["opt_type"]) == ("AAA", "signal", "clean buy", "call")
    assert b["history"]["matches"] == 0 and b["history"]["thin"] is True     # no history rows in the temp folder
    d = client.get(f"/api/desk/alerts/{b['id']}").json()
    assert d["bet"]["ticker"] == "AAA" and "in_plain_words" in d["history"] and "baseline" in d["history"]
    assert client.get("/api/desk/alerts/nope").status_code == 404


def test_manual_lookup_validates(client):
    ok = client.get("/api/desk/lookup", params={"direction": 1, "opt_type": "call", "premium": 500000, "dte": 30,
                                                "otm_pct": 0.05, "sweep": True})
    assert ok.status_code == 200 and ok.json()["matches"] == 0
    assert client.get("/api/desk/lookup", params={"direction": 3, "opt_type": "call", "premium": 1, "dte": 1,
                                                  "otm_pct": 0}).status_code == 400
    assert client.get("/api/desk/lookup", params={"direction": 1, "opt_type": "swap", "premium": 1, "dte": 1,
                                                  "otm_pct": 0}).status_code == 400


def test_ticker_flow_lists_newest_day_first_even_when_older_alerts_are_bigger(client, tmp_path):
    from datetime import datetime, timedelta
    day = data_day(datetime.now(UTC))
    older = []
    for i in range(13):                             # 13 bigger alerts on earlier days would crowd out a top-12 cut
        d = (day - timedelta(days=2 + i)).isoformat()
        older.append({**raw_alert(id=f"o{i}", ticker="AAA", total_premium="9000000", created_at=f"{d}T15:00:00Z"),
                      "session_date": d})
    Store(tmp_path / "c.sqlite").upsert_alerts(older)
    rows = client.get("/api/desk/ticker/AAA").json()["top_alerts"]
    assert rows[0]["date"] == day.isoformat()
    dates = [r["date"] for r in rows]
    assert dates == sorted(dates, reverse=True)


def _earn_rows(dates_moves, implied=0.05):
    return [{"report_date": d, "report_time": "postmarket", "expected_move_perc": str(implied),
             "post_earnings_move_1d": str(m)} for d, m in dates_moves]


def test_earnings_page_labels_upcoming_and_serves_backtest(client, tmp_path):
    import json
    from datetime import date
    st = Store(tmp_path / "c.sqlite")
    past = [("2025-07-24", 0.02), ("2025-10-23", -0.04), ("2026-01-22", 0.06), ("2026-04-23", -0.08)]
    st.cache_put('/api/earnings/AAA?{}', "/api/earnings/AAA", {"data": _earn_rows(past)})
    from datetime import UTC, datetime
    from whaleproof import market_calendar as mc
    from whaleproof.desk.service import reporting_window
    d1, _ = reporting_window([], datetime.now(UTC))            # the first session the page still lists
    d0 = mc.previous_session(date.fromisoformat(d1)).isoformat()
    d2 = mc.next_session(date.fromisoformat(d1)).isoformat()
    svc = client.app.state.desk_svc
    svc.snap.earnings_upcoming = [{"ticker": "OLD", "report_date": d0, "report_time": "postmarket",
                                   "expected_move_perc": 0.03, "side": "afterhours"},
                                  {"ticker": "AAA", "report_date": d1, "report_time": "postmarket",
                                   "expected_move_perc": 0.03, "side": "afterhours", "marketcap": 1e10},
                                  {"ticker": "ZZZ", "report_date": d2, "report_time": "premarket",
                                   "expected_move_perc": 0.04, "side": "premarket"}]
    svc.snap.earnings_at = "2026-10-05T12:40:00+00:00"
    (tmp_path / "journal" / "research").mkdir(parents=True, exist_ok=True)
    (tmp_path / "journal" / "research" / "earnings-moves.json").write_text(json.dumps(
        {"verdict": "supports", "scored": 10, "all": {"beat": 0.34}, "sensitivity": {"by_label": {}}}))
    e = client.get("/api/desk/earnings").json()
    assert e["at"] == "2026-10-05T12:40:00+00:00" and e["backtest"]["verdict"] == "supports"
    a, z = e["upcoming"]                                         # OLD already reported: not listed
    assert a["ticker"] == "AAA" and a["label"] == "cheap" and a["past"] == 0.05 and len(a["history"]) == 4
    assert z["label"] is None and z["note"] == "no past reports cached"
    t = client.get("/api/desk/earnings/aaa").json()
    assert t["ticker"] == "AAA" and t["next"]["label"] == "cheap" and len(t["history"]) == 4
    assert client.get("/api/desk/earnings/DROP;TABLE").status_code == 400
    assert client.get("/api/desk/ticker/AAA").json()["earnings_view"]["next"]["date"] == d1
    assert client.get("/api/desk/earnings/AAA").json()["next"]["reported"] is False   # d1 is ahead: not out yet
    assert all(r["reported"] is False for r in e["upcoming"])
    assert date.fromisoformat(t["history"][0]["day"]) == date(2026, 4, 23)


def test_api_speaks_plain_words_while_engine_text_stays(client):
    """Reasons, why-lines and tier labels leave the API in plain words (desk/plain.py); the engine's own strings are
    untouched, so filter logic that reads them keeps working."""
    s = client.get("/api/desk/today").json()["signals"][0]
    assert s["label"] == "Whale-size bet" and s["tier"] == "whale"
    assert any(w.endswith("until it expires.") for w in s["why"]) and not any("ask-side)" in w for w in s["why"])
    assert client.get("/api/desk/swing").json()["signals"][0]["label"] == "Whale-size bet"
    assert client.get("/api/desk/alerts").json()["bets"][0]["reason"] == "Whale-size bet"
    from whaleproof.desk.signals import TIER_LABEL
    assert TIER_LABEL["whale"] == "Whale conviction bet"            # stored/engine wording unchanged


def test_ticker_page_carries_the_live_price_when_the_refresher_has_one(client):
    svc = client.app.state.desk_svc
    assert client.get("/api/desk/ticker/AAA").json()["spot"] is None
    svc.view_ctx["AAA"] = {"spot": {"last": 12.5, "prev_close": 12.0}, "spot_at": "2026-10-06T14:00:00+00:00"}
    d = client.get("/api/desk/ticker/AAA").json()
    assert d["spot"]["last"] == 12.5 and d["spot_at"] == "2026-10-06T14:00:00+00:00"


def test_ticker_page_knows_a_signal_still_in_its_hold(client):
    """AMAT 10-06: an Oct 5 signal bought at today's open is not 'a signal today' (today's flow), but it is held —
    the ticker page must say so instead of 'Not a signal today'."""
    from datetime import date, datetime
    from types import SimpleNamespace

    from whaleproof import market_calendar as mc
    svc = client.app.state.desk_svc
    today = datetime.now(mc.NY).date()
    prev = mc.previous_session(today)
    held = {"id": "h1", "ticker": "BBB", "direction": 1, "session_date": prev.isoformat(), "entry": today.isoformat(),
            "exit_by": (today.replace(day=28) if today.day < 28 else today).isoformat(), "contract": None, "size": None,
            "tier": "far_otm", "label": "Long shot"}
    svc.recent = [SimpleNamespace(signals=[held], bearish=[])]
    h = client.get("/api/desk/ticker/BBB").json()["holding"]
    assert [x["id"] for x in h] == ["h1"] and "since_entry" in h[0]
    assert client.get("/api/desk/ticker/AAA").json()["holding"] == []
    assert date.fromisoformat(h[0]["exit_by"]) >= today


def test_ticker_page_signal_card_matches_the_sightings_card(client):
    """Owner 10-07: a signal opened from the ticker page showed no open interest (and no price since entry), while
    the same signal on Sightings did — pre-open on the buy day it is still 'today's' signal, exactly when OI matters."""
    tick = {s["id"]: s for s in client.get("/api/desk/ticker/AAA").json()["signal_today"]}
    swing = {s["id"]: s for s in client.get("/api/desk/swing").json()["signals"]}
    assert tick and tick.keys() <= swing.keys()
    for sid, s in tick.items():
        assert s.keys() == swing[sid].keys() and "oi" in s


def test_today_names_the_latest_signals_for_a_quiet_day(client):
    """Empty-day fallback (field review): Today always carries the most recent earlier day that had signals."""
    from datetime import datetime
    from types import SimpleNamespace

    from whaleproof import market_calendar as mc
    svc = client.app.state.desk_svc
    today = datetime.now(mc.NY).date()
    d1, d2 = mc.previous_session(today), mc.previous_session(mc.previous_session(today))
    sig = {"id": "x", "ticker": "BBB", "direction": 1, "session_date": d2.isoformat(), "entry": d1.isoformat(),
           "exit_by": d1.isoformat(), "contract": None, "size": None, "tier": "whale", "label": "Whale"}
    svc.recent = [SimpleNamespace(day=d1.isoformat(), signals=[], bearish=[]),
                  SimpleNamespace(day=d2.isoformat(), signals=[sig], bearish=[])]
    assert client.get("/api/desk/today").json()["latest"] == {"day": d2.isoformat(), "tickers": ["BBB"]}
    svc.recent = [SimpleNamespace(day=d1.isoformat(), signals=[], bearish=[])]
    assert client.get("/api/desk/today").json()["latest"] is None


def test_tracker_lessons_serve_the_locked_rules_and_the_forward_tally(client, tmp_path):
    """Owner 10-07: lessons from the record. Before a freeze file exists the page says so; after, it lists every
    locked rule, its history (research JSON) and the forward tally on signals decided after the lock."""
    import json
    from datetime import UTC, datetime

    from whaleproof.desk import lessons as L
    assert client.get("/api/desk/tracker/lessons").json()["frozen"] is None
    L.freeze(tmp_path / "journal" / "lessons-frozen.json", datetime(2026, 10, 7, 14, 50, tzinfo=UTC), "abc")
    (tmp_path / "journal" / "research").mkdir(exist_ok=True)
    (tmp_path / "journal" / "research" / "lessons.json").write_text(json.dumps({"rules": {"take_profit_5": {"helped_periods": 1}}}))
    d = client.get("/api/desk/tracker/lessons").json()
    assert d["frozen"]["hash"] == L.candidates_hash() and d["changed_since_freeze"] is False
    assert [r["key"] for r in d["rules"]] == list(L.CANDIDATES)
    assert d["rules"][0]["history"] == {"helped_periods": 1} and d["rules"][0]["forward"]["trades"] == 0


def test_tracker_path_carries_review_and_rule_outcomes(client):
    rows = client.get("/api/desk/tracker").json()["rows"]
    for r in rows:                                        # fixture rows are unfinished: keys present, values empty
        p = client.get(f"/api/desk/tracker/{r['id']}/path").json()
        assert p["review"] is None and p["lessons"] is None and isinstance(p["oi"], list)


def test_today_serves_the_surfacing_log(client):
    """Owner 10-07: what surfaced today and what went back under, with the reason in plain words."""
    from datetime import UTC, datetime

    from whaleproof.desk import surfacing
    svc = client.app.state.desk_svc
    day = client.get("/api/desk/today").json()["day"]
    log = surfacing.update(surfacing.empty(day), [{"ticker": "HPE", "direction": 1, "premium": 1e6, "tier": "far_otm"}],
                           [], datetime(2026, 10, 7, 15, 0, tzinfo=UTC))
    log = surfacing.update(log, [], [], datetime(2026, 10, 7, 17, 0, tzinfo=UTC))
    surfacing.save(svc._surf_path(day), log)
    svc._surf = None
    s = client.get("/api/desk/today").json()["surfacing"]
    assert [u["ticker"] for u in s["went_under"]] == ["HPE"] and s["went_under"][0]["reason"] == "no longer in today's flow"


def test_evidence_carries_a_live_row_with_valid_json(client):
    """Owner 10-07: 'Does the filter help?' gets a live row; tiny samples give no range (None, not NaN)."""
    import json
    import time
    ev = client.get("/api/desk/methodology").json()["evidence"]          # first call starts the background scoring
    for _ in range(100):
        if ev["live"]:
            break
        time.sleep(0.05)
        ev = client.get("/api/desk/methodology").json()["evidence"]
    assert "live" in ev and ev["live"]["window"][0] == "2026-09-30" and "unpriced" in ev["live"]
    json.dumps(ev, allow_nan=False)


def test_tracker_carries_each_periods_all_alerts_baseline(client, tmp_path):
    import json
    (tmp_path / "journal" / "desk-evidence.json").write_text(json.dumps({"meta": {"filter_hash": "x"},
        "train": {"label": "t", "funnel": {}, "signals": {}, "all_directional": {"n": 9, "mean": -0.001}, "clean": {}},
        "post": {"label": "p", "funnel": {}, "signals": {}, "all_directional": {"n": 4, "mean": -0.002}, "clean": {}}}))
    b = client.get("/api/desk/tracker").json()["baseline"]
    assert b["Practice year (Oct 2024–Sep 2025, rules chosen here)"]["mean"] == -0.001 and b["Recent months (since Jun 2026)"]["n"] == 4


def test_today_carries_each_holds_move_today_and_the_sp500s(client):
    """Owner 10-07: the Sightings tape (book's move today vs the S&P, each hold scrolling) reads these fields."""
    t = client.get("/api/desk/today").json()
    assert "spy_today" in t["regime"] and set(t["regime"]["spy_today"]) == {"today_move", "today_day", "price_now", "today_since"}
    for s in [*t["signals"], *t["active"]]:
        assert "today_move" in s and "today_day" in s and "price_now" in s


def test_journal_open_stock_trades_carry_where_they_stand_now(client, tmp_path):
    """Owner 10-08: open trades said only "Still open". Same price as Sightings (last close off-hours), against the
    price the owner logged; closed trades and option trades get no mark."""
    from datetime import date, timedelta
    from whaleproof.core.data_layer.models import Bar
    d = date.today() - timedelta(days=1)
    Store(tmp_path / "c.sqlite").put_ohlc("BBB", [Bar(d, 50.0, 56.0, 49.0, 55.0, 1000.0)])
    client.post("/api/desk/journal", json={"ticker": "BBB", "direction": 1, "entry_price": 50, "size": 2, "entry_date": d.isoformat()})
    client.post("/api/desk/journal", json={"ticker": "BBB", "direction": 1, "entry_price": 1.5, "size": 1,
                                           "instrument": "option", "entry_date": d.isoformat()})
    trades = {t["instrument"]: t for t in client.get("/api/desk/journal").json()["trades"]}
    now = trades["stock"]["now"]
    assert now["price"] == 55.0 and now["source"] == "close" and now["date"] == d.isoformat()
    assert abs(now["move"] - 0.10) < 1e-9 and abs(now["pnl"] - 10.0) < 1e-9
    assert trades["option"]["now"] is None


def test_ticker_page_carries_company_header(client, tmp_path):
    from whaleproof.core.data_layer.fetch import cache_key
    assert client.get("/api/desk/ticker/AAA").json()["company"] is None
    Store(tmp_path / "c.sqlite").cache_put(cache_key("/api/stock/AAA/info", {}), "/api/stock/AAA/info",
                                           {"data": {"full_name": "ACME HOLDINGS",
                                                     "short_description": "makes things."}})
    assert client.get("/api/desk/ticker/AAA").json()["company"] == {
        "name": "Acme Holdings", "description": "Makes things."}


def test_lookup_from_what_uw_shows_ticker_strike_expiry(client, tmp_path):
    """Check-a-bet form: ticker + strike + expiry → distance out of the money and days from the stock's last close."""
    from datetime import datetime, timedelta
    from whaleproof.core.data_layer.models import Bar
    day = data_day(datetime.now(UTC))
    st = Store(tmp_path / "c.sqlite")
    st.put_ohlc("ACME", [Bar(day - timedelta(days=1), 99, 101, 98, 100.0, 1000)])
    st.put_metric("ACME", "all", "sector", "Technology")
    exp = (day + timedelta(days=39)).isoformat()
    r = client.get("/api/desk/lookup", params={"direction": 1, "opt_type": "call", "premium": 1_200_000,
                                               "ticker": "acme", "strike": 111, "expiry": exp})
    assert r.status_code == 200
    i = r.json()["inputs"]
    assert i["ticker"] == "ACME" and i["spot"] == 100.0 and abs(i["otm_pct"] - 0.11) < 1e-9 and i["dte"] == 39
    assert i["sector"] == "Technology" and i["spot_date"] == (day - timedelta(days=1)).isoformat()
    put = client.get("/api/desk/lookup", params={"direction": 1, "opt_type": "put", "premium": 200_000, "ticker": "ACME",
                                                 "strike": 90, "expiry": exp}).json()["inputs"]
    assert abs(put["otm_pct"] - 0.10) < 1e-9                       # puts: out of the money below the price
    nope = client.get("/api/desk/lookup", params={"direction": 1, "opt_type": "call", "premium": 200_000, "ticker": "ZZZZQ",
                                                  "strike": 10, "expiry": exp})
    assert nope.status_code == 400 and "ZZZZQ" in nope.json()["detail"]
    assert client.get("/api/desk/lookup", params={"direction": 1, "opt_type": "call", "premium": 1}).status_code == 400
    old = client.get("/api/desk/lookup", params={"direction": 1, "opt_type": "call", "premium": 200_000, "ticker": "ACME", "strike": 110,
                                                 "expiry": (day - timedelta(days=3)).isoformat()})
    assert old.status_code == 400 and "passed" in old.json()["detail"]


def test_check_a_bet_says_whether_our_filter_would_take_it(client, tmp_path):
    """The check runs the frozen filter's own rules (signals.decide) on what was typed."""
    from datetime import datetime, timedelta
    from whaleproof.core.data_layer.models import Bar
    day = data_day(datetime.now(UTC))
    st = Store(tmp_path / "c.sqlite")
    st.put_ohlc("ACME", [Bar(day - timedelta(days=1), 99, 101, 98, 100.0, 1000)])
    st.put_ohlc("PENY", [Bar(day - timedelta(days=1), 3, 3, 3, 3.0, 1000)])
    exp = (day + timedelta(days=40)).isoformat()
    q = lambda **k: client.get("/api/desk/lookup", params={"direction": 1, "opt_type": "call", "premium": 1_200_000,
                                                           "ticker": "ACME", "strike": 111, "expiry": exp} | k).json()["filter"]
    whale = q()
    assert whale["signal"] is True and whale["tier"] == "whale"
    near = q(strike=103, premium=500_000)
    assert near["signal"] is False and near["stage"] == "conviction" and "$1" in near["reason"]
    put = q(opt_type="put", strike=90, direction=-1)
    assert put["signal"] is False and put["stage"] == "direction"
    sold = q(direction=-1, bet_kind="not a clean buy")
    assert sold["signal"] is False and sold["stage"] == "gate"
    cheap_stock = q(ticker="PENY", strike=3.3)
    assert cheap_stock["signal"] is False and cheap_stock["stage"] == "liquidity"
    by_hand = client.get("/api/desk/lookup", params={"direction": 1, "opt_type": "call", "premium": 200_000, "dte": 30,
                                                     "otm_pct": 0.05}).json()
    assert by_hand["filter"] is None                                  # no ticker: price/earnings unknown, no verdict


def test_check_a_bet_applies_the_first_screen_too(client, tmp_path):
    """Trader test 10-12: a 2-year LEAP and a 784%-out call came back 'Signal' — the first screen (7–90 days,
    5% in to 30% out, stock/ADR/ETF, no ETF puts) must run before the final rules, and under $100K isn't a UW alert."""
    from datetime import datetime, timedelta
    from whaleproof.core.data_layer.fetch import cache_key
    from whaleproof.core.data_layer.models import Bar
    day = data_day(datetime.now(UTC))
    st = Store(tmp_path / "c.sqlite")
    for t in ("ACME", "SPYX"):
        st.put_ohlc(t, [Bar(day - timedelta(days=1), 99, 101, 98, 100.0, 1000)])
    st.cache_put(cache_key("/api/stock/SPYX/info", {}), "/api/stock/SPYX/info", {"data": {"issue_type": "ETF"}})
    q = lambda days=40, **k: client.get("/api/desk/lookup", params={"direction": 1, "opt_type": "call", "premium": 1_200_000,
                                                                  "ticker": "ACME", "strike": 111,
                                                                  "expiry": (day + timedelta(days=days)).isoformat()} | k)
    leap = q(days=731).json()["filter"]
    assert leap["signal"] is False and leap["stage"] == "gate" and "7 to 90 days" in leap["reason"]
    far = q(strike=900).json()["filter"]
    assert far["signal"] is False and far["stage"] == "gate" and "30% out" in far["reason"]
    etf_put = q(ticker="SPYX", opt_type="put", strike=90, direction=-1).json()["filter"]
    assert etf_put["stage"] == "gate" and "hedge" in etf_put["reason"]
    small = q(premium=50_000)
    assert small.status_code == 400 and "$100K" in small.json()["detail"]


def test_one_day_reads_singular():
    from whaleproof.desk.plain import reason
    assert reason("DTE 1 outside 7–90").startswith("Expires in 1 day.")
    assert reason("DTE 0 outside 7–90").startswith("Expires today.")


def test_check_a_bet_falls_back_to_the_price_on_the_tickers_latest_alert(client, tmp_path):
    """Trader test 10-12: KHC, VZ, AI… had flow today but no saved daily bars, so the check refused them."""
    from datetime import datetime, timedelta
    day = data_day(datetime.now(UTC))
    exp = (day + timedelta(days=40)).isoformat()
    # the fixture's AAA alert: underlying_price 100 on the data day, no bars saved
    r = client.get("/api/desk/lookup", params={"direction": 1, "opt_type": "call", "premium": 1_200_000,
                                               "ticker": "AAA", "strike": 110, "expiry": exp})
    assert r.status_code == 200
    i = r.json()["inputs"]
    assert i["spot"] == 100.0 and i["spot_source"] == "alert" and abs(i["otm_pct"] - 0.10) < 1e-9


def test_check_a_bet_signal_shows_its_types_sealed_test_record(client, tmp_path):
    import json
    from datetime import datetime, timedelta
    from whaleproof.core.data_layer.models import Bar
    day = data_day(datetime.now(UTC))
    Store(tmp_path / "c.sqlite").put_ohlc("ACME", [Bar(day - timedelta(days=1), 99, 101, 98, 100.0, 1000)])
    (tmp_path / "journal" / "desk-holdout.json").write_text(json.dumps(
        {"tiers": {"whale": {"n": 153, "win_rate": 0.549, "mean": 0.0059}, "far_otm": {"n": 475, "win_rate": 0.518, "mean": 0.017}}}))
    q = lambda **k: client.get("/api/desk/lookup", params={"direction": 1, "opt_type": "call", "premium": 1_200_000, "ticker": "ACME",
                                                           "strike": 111, "expiry": (day + timedelta(days=40)).isoformat()} | k).json()["filter"]
    rec = q()["record"]
    assert rec == {"tier": "whale", "trades": 153, "beat": 0.549, "avg": 0.0059}
    assert q(strike=103, premium=500_000).get("record") is None          # not a signal: no record


def test_dark_pool_levels_carry_their_day_and_old_ones_leave_the_ticker_page(client, tmp_path):
    """Market key levels showed KTOS's busiest dark-pool price from Feb 24 next to today's price (owner 10-13 sweep)."""
    from datetime import datetime, timedelta
    day = data_day(datetime.now(UTC))
    st = Store(tmp_path / "c.sqlite")
    st.put_metric("SPY", (day - timedelta(days=60)).isoformat(), "dp_levels", [[500.0, 9_000_000]])
    st.put_metric("QQQ", day.isoformat(), "dp_levels", [[700.0, 1_000_000]])
    lv = client.get("/api/desk/day").json()["levels"]
    assert lv["SPY"]["dp_top"] == [[500.0, 9_000_000]] and lv["SPY"]["dp_date"] == (day - timedelta(days=60)).isoformat()
    assert lv["QQQ"]["dp_date"] == day.isoformat()          # Market shows each level with its day
    st.put_metric("ACME", (day - timedelta(days=60)).isoformat(), "dp_levels", [[50.0, 9_000_000]])
    assert client.get("/api/desk/ticker/ACME").json()["dp_levels"] == []



def _startup_app(tmp_path, monkeypatch, wait_s=30.0):
    """App on a one-alert cache with the startup jobs (Track record warm-up, bet-history index) instrumented."""
    import time
    from datetime import datetime, timedelta
    import whaleproof.api.desk as desk_api
    import threading
    calls: dict[str, float] = {}
    mine: set = set()                       # only this app's startup threads count (earlier tests' threads may linger)
    real_build, real_index = desk_api.build_rows, desk_api.LookupIndex

    def seen(name):
        if threading.current_thread() in mine:
            calls.setdefault(name, time.monotonic())
    monkeypatch.setattr(desk_api, "STARTUP_WAIT_S", wait_s)
    monkeypatch.setattr(desk_api, "build_rows", lambda *a, **k: (seen("tracker"), real_build(*a, **k))[1])
    monkeypatch.setattr(desk_api, "LookupIndex", lambda *a, **k: (seen("lookup"), real_index(*a, **k))[1])
    db = tmp_path / "c.sqlite"
    st = Store(db)
    day = data_day(datetime.now(UTC))
    d, exp = day.isoformat(), (day + timedelta(days=45)).isoformat()
    st.upsert_alerts([{**raw_alert(id="w", ticker="AAA", underlying_price="100", strike="110", expiry=exp,
                                   total_premium="2000000", total_ask_side_prem="1950000", total_bid_side_prem="50000",
                                   created_at=f"{d}T15:00:00Z", option_chain="AAA270618C00110000"), "session_date": d}])
    (tmp_path / "journal").mkdir()
    before = set(threading.enumerate())
    app = create_app(tmp_path / "journal" / "picks.jsonl", db, tmp_path / "x.log",
                     desk=(DeskService(db, ""), UserDB(tmp_path / "u.sqlite", tmp_path / "bk"), tmp_path / "rows"))
    mine.update(t for t in threading.enumerate() if t not in before and t.name.startswith("signaldesk-"))
    assert {t.name for t in mine} >= {"signaldesk-warm", "signaldesk-lookup"}
    return TestClient(app), calls


def _until(cond, s=10.0):
    import time
    end = time.monotonic() + s
    while not cond() and time.monotonic() < end:
        time.sleep(0.05)
    return cond()


def test_startup_jobs_wait_for_todays_signals_so_sightings_loads_first(tmp_path, monkeypatch):
    """Cold start 10-16: the Track record warm-up and the bet-history index used to start with the server and share
    the CPU with the first Sightings load (restart → home 40–75 s). They now start once today's signals exist."""
    import time
    c, calls = _startup_app(tmp_path, monkeypatch)
    time.sleep(0.6)
    assert calls == {}                                     # nothing built before today's signals
    assert c.get("/api/desk/today").status_code == 200
    done = time.monotonic()
    assert _until(lambda: {"tracker", "lookup"} <= calls.keys())
    assert calls["tracker"] >= done - 0.5 and calls["lookup"] >= done - 0.5


def test_startup_jobs_still_run_when_no_page_is_opened(tmp_path, monkeypatch):
    c, calls = _startup_app(tmp_path, monkeypatch, wait_s=0.3)
    assert _until(lambda: {"tracker", "lookup"} <= calls.keys())
    assert c.get("/api/desk/today").status_code == 200    # and the pages answer as before


def test_keyless_ticker_reads_the_gex_and_dark_pool_the_live_desk_cached(tmp_path):
    """10-20: the dashboard's ticker page showed today's GEX and dark-pool levels (pulled when the page was viewed);
    the MCP (no key) showed Sep 29's GEX and no dark pool. A keyless desk now reads those cached pulls too."""
    from datetime import datetime

    from whaleproof.core.data_layer.fetch import cache_key
    db = tmp_path / "c.sqlite"
    st = Store(db)
    d = data_day(datetime.now(UTC)).isoformat()
    st.put_metric("AAA", "2026-09-29", "gex", {"call_wall": 120.0, "put_wall": 90.0, "gamma_flip": 99.0, "gamma_magnet": 100.0})
    st.cache_put(cache_key("/api/stock/AAA/gex-levels", {"date": d, "source": "oi"}), "/api/stock/AAA/gex-levels",
                 {"data": [{"date": d, "call_wall": "130", "put_wall": "95", "gamma_flip": "104.5", "gamma_magnet": "110"}]})
    st.cache_put(cache_key("/api/darkpool/AAA/price-levels", {"date": d}), "/api/darkpool/AAA/price-levels",
                 {"data": [{"price": "101.5", "dark_pool_volume": "50000"}, {"price": "99", "dark_pool_volume": "80000"}]})
    (tmp_path / "journal").mkdir()
    app = create_app(tmp_path / "journal" / "picks.jsonl", db, tmp_path / "x.log",
                     desk=(DeskService(db, ""), UserDB(tmp_path / "u.sqlite", tmp_path / "bk"), tmp_path / "rows"))
    t = TestClient(app).get("/api/desk/ticker/AAA").json()
    assert t["gex"]["date"] == d and t["gex"]["gamma_flip"] == 104.5
    assert t["dp_levels"] == [[99.0, 80000.0], [101.5, 50000.0]]


def test_earnings_warning_last_full_session_is_the_day_before_unless_after_the_close(tmp_path):
    """10-20 trader review: RIOT 'Oct 29, time not set — last full session before it: Oct 29'. Without a set time
    the report may come before the open, so the safe last full session is the day before (as for before-the-open)."""
    from datetime import date

    from whaleproof.api.desk import _earn_warn
    st = Store(tmp_path / "c.sqlite")
    for t, when in (("AAA", "unknown"), ("BBB", "premarket"), ("CCC", "postmarket")):
        st.cache_put(f"/api/earnings/{t}?{{}}", f"/api/earnings/{t}",
                     {"data": [{"report_date": "2026-10-29", "report_time": when}]})
    d = date(2026, 10, 20)
    assert _earn_warn(st, "AAA", d)["last_session_before"] == "2026-10-28"
    assert _earn_warn(st, "BBB", d)["last_session_before"] == "2026-10-28"
    assert _earn_warn(st, "CCC", d)["last_session_before"] == "2026-10-29"
