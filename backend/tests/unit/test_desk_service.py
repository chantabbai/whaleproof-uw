"""Today's signals from the cache (no UW calls) + which session the desk shows."""
from datetime import UTC, date, datetime

from tests.conftest import raw_alert
from whaleproof import market_calendar as mc
from whaleproof.desk.service import compute_signals, data_day

D = date(2026, 9, 25)


def _store_alerts(store, *alerts):
    store.upsert_alerts([{**a, "session_date": D.isoformat()} for a in alerts])


def test_data_day_pre_open_uses_last_session():
    pre = datetime(2026, 9, 30, 8, 0, tzinfo=mc.NY)
    assert data_day(pre) == date(2026, 9, 29)
    assert data_day(datetime(2026, 9, 30, 10, 0, tzinfo=mc.NY)) == date(2026, 9, 30)
    assert data_day(datetime(2026, 10, 3, 12, 0, tzinfo=mc.NY)) == date(2026, 10, 2)


def test_compute_signals_funnel_and_reasons(store):
    whale = raw_alert(id="w", ticker="AAA", underlying_price="100", strike="110", expiry="2026-11-20",
                      total_premium="2000000", total_ask_side_prem="1950000", total_bid_side_prem="50000",
                      option_chain="AAA261120C00110000")
    sold = raw_alert(id="s", ticker="BBB", underlying_price="50", strike="55", expiry="2026-11-20",
                     total_premium="900000", total_ask_side_prem="50000", total_bid_side_prem="850000",
                     option_chain="BBB261120C00055000")
    _store_alerts(store, whale, sold)
    out = compute_signals(store, D, datetime(2026, 9, 25, 20, 15, tzinfo=UTC))
    assert out.funnel == {"raw": 2, "directional": 2, "clean": 1, "signals": 1}
    assert [s["ticker"] for s in out.signals] == ["AAA"] and out.signals[0]["tier"] == "whale"
    assert out.signals[0]["why"] and out.signals[0]["exit_by"] == "2026-10-02"
    assert out.rejected_top[0]["ticker"] == "BBB" and out.rejected_top[0]["stage"] == "gate"


def test_index_options_are_left_out_of_the_day_count_like_history_does(store):
    """UW history replies drop the stock price on index options, so backfill/quick-start never store them. Live days
    leave them out too, so 'alerts came in' means the same thing on every day (and they can't pass the gate anyway)."""
    whale = raw_alert(id="w", ticker="AAA", underlying_price="100", strike="110", expiry="2026-11-20",
                      total_premium="2000000", total_ask_side_prem="1950000", total_bid_side_prem="50000",
                      option_chain="AAA261120C00110000")
    spxw = raw_alert(id="x", ticker="SPXW", underlying_price="6700", strike="6800", expiry="2026-10-16",
                     total_premium="5000000", total_ask_side_prem="4900000", total_bid_side_prem="100000",
                     option_chain="SPXW261016C06800000")
    _store_alerts(store, whale, spxw)
    out = compute_signals(store, D, datetime(2026, 9, 25, 20, 15, tzinfo=UTC))
    assert out.funnel == {"raw": 1, "directional": 1, "clean": 1, "signals": 1}
    assert all(b["ticker"] != "SPXW" for b in out.bets) and all(r["ticker"] != "SPXW" for r in out.rejected_top)


def test_whale_put_goes_to_bearish_watch_not_signals(store):
    put = raw_alert(id="p", ticker="CCC", type="put", underlying_price="100", strike="90", expiry="2026-11-20",
                    total_premium="3000000", total_ask_side_prem="2900000", total_bid_side_prem="100000",
                    option_chain="CCC261120P00090000")
    _store_alerts(store, put)
    out = compute_signals(store, D, datetime(2026, 9, 25, 20, 15, tzinfo=UTC))
    assert out.signals == [] and out.funnel["signals"] == 0
    assert [b["ticker"] for b in out.bearish] == ["CCC"] and out.bearish[0]["tier"] == "whale"
    assert out.bearish[0]["direction"] == -1 and out.bearish[0]["why"]


def test_value_for_uses_iv_rank_basis_like_every_tested_window(store):
    """Owner 2026-09-30 (a): live option value = IV rank, as in all history windows; alert IV/RV is info only."""
    from whaleproof.core.data_layer.models import parse_alert
    from whaleproof.desk.service import value_for
    a = parse_alert(raw_alert(id="v", ticker="VVV", underlying_price="100", strike="120", expiry="2026-11-20",
                              iv="0.90", option_chain="VVV261120C00120000") | {"session_date": D.isoformat()})
    store.put_metric("VVV", "all", "vol_hist", [["2026-08-25", 21, 0.30, "2026-09-24"]])   # IV/RV 3.0 → "rich"
    store.put_metric("VVV", "2026-09-24", "iv_rank", 20.0)
    v = value_for(store, a)
    assert v["verdict"] == "cheap" and v["basis"] == "iv_rank"
    assert abs(v["iv_rv"] - 3.0) < 1e-9 and "info only" in v["reason"]
    store.conn.execute("DELETE FROM daily_metric WHERE kind='iv_rank'")
    assert value_for(store, a)["verdict"] == "unknown"                  # no rank → not a far-OTM signal (as in history)


def test_tracker_close_job_runs_after_close_only(tmp_path, monkeypatch):
    from datetime import UTC, datetime
    from types import SimpleNamespace

    import whaleproof.desk.service as sv
    from whaleproof.core.data_layer.store import Store
    calls = []
    monkeypatch.setattr(sv, "close_update", lambda c, st, items, day: calls.append((items, day)) or {"day": str(day)})
    svc = sv.DeskService(tmp_path / "c.sqlite", "")
    svc.client = SimpleNamespace(usage=SimpleNamespace(daily_count=None, daily_limit=None), get=None)
    svc.mode_env = "full"
    svc.tracker_open_fn = lambda: [("AAA", "C1")]
    st = Store(tmp_path / "c.sqlite")
    svc.refresh(st, datetime(2026, 10, 1, 18, 0, tzinfo=UTC))       # 14:00 ET, market open → no close job
    assert calls == []
    svc.refresh(st, datetime(2026, 10, 1, 20, 20, tzinfo=UTC))      # 16:20 ET → runs for 10-01
    assert calls == [([("AAA", "C1")], date(2026, 10, 1))] and svc.tracker_version == 1


def test_tracker_settle_job_refetches_the_morning_after_and_redraws_the_record(tmp_path, monkeypatch):
    from datetime import UTC, datetime
    from types import SimpleNamespace

    import whaleproof.desk.service as sv
    import whaleproof.desk.tracker as tr
    from whaleproof.core.data_layer.store import Store
    monkeypatch.setattr(sv, "close_update", lambda c, st, items, day: None)
    fetched = []
    monkeypatch.setattr(tr, "ingest_bars", lambda c, s, t, ttl: fetched.append(t))
    svc = sv.DeskService(tmp_path / "c.sqlite", "")
    svc.client = SimpleNamespace(usage=SimpleNamespace(daily_count=None, daily_limit=None), get=None)
    svc.mode_env = "full"
    svc.tracker_settle_fn = lambda d: ["SPY", "CRDO"] if d == date(2026, 10, 13) else []
    monkeypatch.setattr(sv.live_evidence, "exit_tickers", lambda store, d: ["CRDO", "ZZZ"] if d == date(2026, 10, 13) else [])
    st = Store(tmp_path / "c.sqlite")
    svc.refresh(st, datetime(2026, 10, 14, 1, 0, tzinfo=UTC))       # Tue 21:00 ET: Tue's close too fresh
    assert fetched == [] and svc.tracker_version == 0 and svc.live_ev_version == 0
    svc._last.pop("tracker_settle")                                 # 11 h later (the job's throttle is wall-clock)
    svc.refresh(st, datetime(2026, 10, 14, 12, 5, tzinfo=UTC))      # Wed 08:05 ET
    assert fetched == ["SPY", "CRDO", "ZZZ"] and svc.tracker_version == 1 and svc.live_ev_version == 1


def test_bets_carry_every_trade_with_its_verdict_and_kind(make_alert):
    from whaleproof.desk.service import _bets
    sig = make_alert(id="s", ticker="AAA")
    gate = make_alert(id="g", ticker="BBB", type="call", total_ask_side_prem="0", total_bid_side_prem="500000")
    sale = make_alert(id="p", ticker="CCC", type="put", total_ask_side_prem="0", total_bid_side_prem="500000")
    trades = [(sig, [], False), (gate, ["not a buy (ask-side 0% < 70%)"], False), (sale, ["not a buy"], True)]
    rejected = [{"id": "g", "stage": "gate", "reason": "not a buy (ask-side 0% < 70%)"},
                {"id": "p", "stage": "gate", "reason": "not a buy"}]
    out = {b["id"]: b for b in _bets(trades, rejected, [{"id": "s", "label": "Whale conviction bet"}], {"AAA": "Tech"})}
    assert (out["s"]["verdict"], out["s"]["bet_kind"], out["s"]["sector"]) == ("signal", "clean buy", "Tech")
    assert (out["g"]["verdict"], out["g"]["bet_kind"], out["g"]["direction"]) == ("gate", "not a clean buy", -1)
    assert (out["p"]["bet_kind"], out["p"]["opt_type"], out["p"]["direction"]) == ("put sale", "put", 1)


def test_viewed_ticker_gets_fresh_bars_gex_and_darkpool(tmp_path):
    """Opening a ticker page asks the refresher for that ticker's bars, GEX and dark-pool levels (the API itself never
    calls UW). Repeat views inside the refresh interval cost nothing; stale views are dropped."""
    from tests.unit.test_desk_live import FakeClient
    from whaleproof.core.data_layer.store import Store
    from whaleproof.desk.service import DeskService
    d = date(2026, 10, 1)
    c = FakeClient({
        "/api/stock/MU/ohlc/1d": {"data": [{"date": "2026-10-01", "open": 1, "high": 2, "low": 1, "close": 2,
                                            "volume": 5, "market_time": "r"}]},
        "/api/stock/MU/gex-levels": {"data": [{"date": "2026-10-01", "call_wall": 1100, "put_wall": 1000,
                                               "gamma_flip": 1050, "gamma_magnet": None}]},
        "/api/darkpool/MU/price-levels": {"data": [{"price": "1055", "dark_pool_volume": "900"}]},
        "/api/stock/MU/info": {"data": {"full_name": "MICRON TECHNOLOGY", "sector": "Technology",
                                        "short_description": "makes memory."}},
    })
    st = Store(tmp_path / "c.sqlite")
    svc = DeskService(tmp_path / "c.sqlite", "")
    svc.client = c
    svc.view("MU")
    svc._refresh_viewed(st, d, live_day=True)
    assert [b.close for b in st.get_ohlc("MU", d, d)] == [2]
    from whaleproof.desk.company import company_info     # company header info fetched once (cached forever)
    assert company_info(st, "MU")["name"] == "Micron Technology"
    v = svc.view_ctx["MU"]
    assert v["gex"]["call_wall"] == 1100 and v["gex"]["date"] == "2026-10-01"
    assert v["dp"] == [{"price": 1055.0, "volume": 900.0}] and v["at"]
    n = len(c.calls)
    svc.view("MU")
    svc._refresh_viewed(st, d, live_day=True)
    assert len(c.calls) == n                          # inside the interval → no new calls
    svc.viewed["MU"] -= 3600                           # viewed an hour ago → no longer refreshed
    svc._last.clear()
    svc._refresh_viewed(st, d, live_day=True)
    assert len(c.calls) == n and "MU" not in svc.viewed


def test_closed_market_day_polls_uw_once_then_stops(tmp_path, monkeypatch):
    """Weekend/holiday: the last session's data is final, so each live job runs once (catch-up after a start) and
    then not again until the next session — no 30-min flow polls all Saturday."""
    from types import SimpleNamespace

    import whaleproof.desk.live as lv
    import whaleproof.desk.service as sv
    from whaleproof.core.data_layer.store import Store
    calls = []
    for fn in ("pull_flow_incremental", "market_tide", "sector_tides", "gex_levels", "stock_state"):
        monkeypatch.setattr(lv, fn, lambda *a, fn=fn, **k: calls.append(fn) or [])
    svc = sv.DeskService(tmp_path / "c.sqlite", "")
    svc.client = SimpleNamespace(usage=SimpleNamespace(daily_count=None, daily_limit=None), get=None)
    svc.mode_env = "full"
    st = Store(tmp_path / "c.sqlite")
    sat = datetime(2026, 10, 3, 16, 0, tzinfo=UTC)                   # Saturday 12:00 ET
    svc.refresh(st, sat)
    first = list(calls)
    assert "pull_flow_incremental" in first
    svc._last = {k: v - 7200 for k, v in svc._last.items()}            # two hours later
    svc.refresh(st, sat.replace(hour=18))
    assert calls == first
    svc._last = {k: v - 7200 for k, v in svc._last.items()}
    svc.refresh(st, datetime(2026, 10, 5, 14, 0, tzinfo=UTC))          # Monday 10:00 ET, open → polling resumes
    assert calls.count("pull_flow_incremental") == 2


def test_status_count_falls_back_to_this_desks_calls_when_uw_sends_no_daily_count(tmp_path, monkeypatch):
    """UW stopped sending x-uw-daily-req-count (~10-07): the 'N of 40,000 used today' line uses the desk's own count."""
    from types import SimpleNamespace

    import whaleproof.desk.live as lv
    import whaleproof.desk.service as sv
    from whaleproof.core.data_layer.store import Store
    usage = SimpleNamespace(daily_count=None, daily_limit=None, sent=0)

    def pull(*a, **k):
        usage.sent += 7
        return []
    monkeypatch.setattr(lv, "pull_flow_incremental", pull)
    for fn in ("market_tide", "sector_tides", "gex_levels", "stock_state"):
        monkeypatch.setattr(lv, fn, lambda *a, **k: [])
    svc = sv.DeskService(tmp_path / "c.sqlite", "")
    svc.client = SimpleNamespace(usage=usage, get=None)
    svc.mode_env = "full"
    svc.refresh(Store(tmp_path / "c.sqlite"), datetime(2026, 10, 9, 14, 0, tzinfo=UTC))      # Friday 10:00 ET
    assert svc.state.usage["count"] == 7


def test_viewed_ticker_fetched_once_on_a_closed_market_day(tmp_path, monkeypatch):
    import whaleproof.desk.live as lv
    import whaleproof.desk.service as sv
    from whaleproof.core.data_layer.store import Store
    calls = []
    monkeypatch.setattr(sv, "ingest_bars", lambda *a, **k: calls.append("bars"))
    monkeypatch.setattr(lv, "gex_levels", lambda *a, **k: None)
    monkeypatch.setattr(lv, "darkpool_levels", lambda *a, **k: [])
    monkeypatch.setattr(lv, "refresh_vol", lambda *a, **k: None)
    monkeypatch.setattr(lv, "refresh_earnings", lambda *a, **k: None)
    monkeypatch.setattr(lv, "sector_of", lambda *a, **k: None)
    svc = sv.DeskService(tmp_path / "c.sqlite", "")
    st = Store(tmp_path / "c.sqlite")
    svc.view("MU")
    svc._refresh_viewed(st, date(2026, 10, 2), live_day=False, closed=True)
    svc._last = {k: v - 3600 for k, v in svc._last.items()}            # an hour later, page still open
    svc.view("MU")
    svc._refresh_viewed(st, date(2026, 10, 2), live_day=False, closed=True)
    assert calls == ["bars"]


def test_earnings_calendar_job_pulls_next_five_sessions_and_missing_histories(tmp_path, monkeypatch):
    """Pre-open Monday: premarket + afterhours for today and the next 4 sessions; past reports fetched only for
    tickers with no fresh cached history (biggest first, capped); today's lists feed the Today page."""
    from types import SimpleNamespace

    import whaleproof.desk.live as lv
    import whaleproof.desk.service as sv
    from whaleproof.core.data_layer.store import Store
    asked, hist = [], []

    def cal(client, store, when, d, **k):
        asked.append((when, d.isoformat()))
        if d.isoformat() == "2026-10-05" and when == "premarket":
            return [{"ticker": "BIG", "report_date": "2026-10-05", "report_time": "premarket",
                     "expected_move_perc": 0.05, "marketcap": 9e10},
                    {"ticker": "SMALL", "report_date": "2026-10-05", "report_time": "premarket",
                     "expected_move_perc": 0.08, "marketcap": 1e9}]
        return []
    monkeypatch.setattr(lv, "earnings_session", cal)
    monkeypatch.setattr(sv, "cached_get", lambda c, s, path, p, ttl: hist.append(path))
    monkeypatch.setattr(sv, "EARN_HIST_MAX", 1)
    for fn in ("pull_flow_incremental", "market_tide", "sector_tides", "gex_levels", "stock_state"):
        monkeypatch.setattr(lv, fn, lambda *a, **k: [])
    svc = sv.DeskService(tmp_path / "c.sqlite", "")
    svc.client = SimpleNamespace(usage=SimpleNamespace(daily_count=None, daily_limit=None), get=None)
    st = Store(tmp_path / "c.sqlite")
    svc.refresh(st, datetime(2026, 10, 5, 12, 40, tzinfo=UTC))          # Monday 08:40 ET, pre-open
    days = sorted({d for _, d in asked})
    assert days == ["2026-10-05", "2026-10-06", "2026-10-07", "2026-10-08", "2026-10-09"] and len(asked) == 10
    assert hist == ["/api/earnings/BIG"]                                 # cap 1 → biggest first
    snap = svc.snapshot()
    assert [x["ticker"] for x in snap.earnings_upcoming] == ["BIG", "SMALL"] and snap.earnings_at
    assert [x["ticker"] for x in snap.earnings_today["premarket"]] == ["BIG", "SMALL"]
    assert snap.earnings_today["afterhours"] == []
    n = len(asked)
    svc.refresh(st, datetime(2026, 10, 5, 13, 0, tzinfo=UTC))           # 20 min later → not due
    assert len(asked) == n


def test_economic_calendar_refreshes_live_with_the_earnings_job(tmp_path, monkeypatch):
    """Bug 10-06: the economic calendar was only rebuilt from cache, so the Today page showed a Sep 30 pull forever
    ('Nothing in the next three days'). It now refreshes with the earnings calendar (same 6 h cadence, 1 call)."""
    from types import SimpleNamespace

    import whaleproof.desk.live as lv
    import whaleproof.desk.service as sv
    from whaleproof.core.data_layer.store import Store
    pulls = []
    ev = [{"time": "2026-10-07T12:30:00Z", "event": "CPI", "forecast": None, "prev": None, "reported_period": None}]
    monkeypatch.setattr(lv, "economic_calendar", lambda c, s: pulls.append(1) or ev)
    monkeypatch.setattr(lv, "earnings_session", lambda *a, **k: [])
    for fn in ("pull_flow_incremental", "market_tide", "sector_tides", "gex_levels", "stock_state"):
        monkeypatch.setattr(lv, fn, lambda *a, **k: [])
    svc = sv.DeskService(tmp_path / "c.sqlite", "")
    svc.client = SimpleNamespace(usage=SimpleNamespace(daily_count=None, daily_limit=None), get=None)
    st = Store(tmp_path / "c.sqlite")
    svc.refresh(st, datetime(2026, 10, 6, 12, 40, tzinfo=UTC))          # Tue 08:40 ET
    assert pulls == [1] and [e["event"] for e in svc.snapshot().calendar] == ["CPI"]
    svc.refresh(st, datetime(2026, 10, 6, 13, 0, tzinfo=UTC))           # 20 min later → not due
    assert pulls == [1]


def test_earnings_calendar_keeps_todays_after_close_reporters_until_the_day_ends():
    from whaleproof.desk.service import earnings_days
    assert earnings_days(datetime(2026, 10, 5, 21, 0, tzinfo=UTC))[0] == date(2026, 10, 5)   # Mon 17:00 ET: tonight's reports
    assert earnings_days(datetime(2026, 10, 3, 16, 0, tzinfo=UTC))[0] == date(2026, 10, 5)   # Saturday


def test_cache_only_desk_rebuilds_earnings_calendar_from_cached_pages(tmp_path):
    from whaleproof.core.data_layer.fetch import cache_key
    from whaleproof.core.data_layer.store import Store
    from whaleproof.desk.service import DeskService
    st = Store(tmp_path / "c.sqlite")
    st.cache_put(cache_key("/api/earnings/premarket", {"date": "2026-10-06", "limit": 100, "page": 0}),
                 "/api/earnings/premarket", {"data": [{"symbol": "AAA", "report_date": "2026-10-06",
                                                       "report_time": "premarket", "expected_move_perc": "0.04"}]})
    svc = DeskService(tmp_path / "c.sqlite", "")                       # no key → cache only
    svc.refresh(st, datetime(2026, 10, 6, 13, 0, tzinfo=UTC))          # Tue 09:00 ET → from Tue 10-06
    up = svc.snapshot().earnings_upcoming
    assert [(x["ticker"], x["side"], x["report_date"]) for x in up] == [("AAA", "premarket", "2026-10-06")]


def test_viewed_ticker_gets_a_live_price_every_minute_while_open(tmp_path, monkeypatch):
    """An open ticker page shows the current price, not just the last close: the refresher fetches the viewed ticker's
    stock state at most every VIEW_SPOT_S on a live day (bars/GEX/dark pool keep their 15-min cadence)."""
    import whaleproof.desk.live as lv
    import whaleproof.desk.service as sv
    from whaleproof.core.data_layer.store import Store
    calls = []
    monkeypatch.setattr(sv, "ingest_bars", lambda *a, **k: calls.append("bars"))
    monkeypatch.setattr(lv, "gex_levels", lambda *a, **k: None)
    monkeypatch.setattr(lv, "darkpool_levels", lambda *a, **k: [])
    monkeypatch.setattr(lv, "refresh_vol", lambda *a, **k: None)
    monkeypatch.setattr(lv, "refresh_earnings", lambda *a, **k: None)
    monkeypatch.setattr(lv, "sector_of", lambda *a, **k: None)
    monkeypatch.setattr(lv, "stock_state", lambda c, s, t: calls.append("spot") or {"last": 531.2, "prev_close": 529.98})
    svc = sv.DeskService(tmp_path / "c.sqlite", "")
    st = Store(tmp_path / "c.sqlite")
    d = date(2026, 10, 6)
    svc.view("AMAT")
    svc._refresh_viewed(st, d, live_day=True)
    assert svc.view_ctx["AMAT"]["spot"]["last"] == 531.2 and svc.view_ctx["AMAT"]["spot_at"]
    svc._refresh_viewed(st, d, live_day=True)
    assert calls == ["spot", "bars"]                               # same minute → nothing new
    svc._last = {k: (v - sv.VIEW_SPOT_S - 1 if k.startswith("vspot:") else v) for k, v in svc._last.items()}
    svc._refresh_viewed(st, d, live_day=True)
    assert calls == ["spot", "bars", "spot"]                       # a minute later → price only, levels wait
    assert svc.view_ctx["AMAT"]["gex"] is None and "dp" in svc.view_ctx["AMAT"]   # earlier fields kept


def test_viewed_ticker_also_refreshes_iv_rank_vol_and_earnings(tmp_path, monkeypatch):
    """Audit 10-06: the ticker page showed MU's IV rank from Oct 5 and SPY's from Sep 29 — vol and earnings were only
    fetched for signal candidates. An open page now refreshes them with its levels (cached 12 h, so ≤3 calls)."""
    import whaleproof.desk.live as lv
    import whaleproof.desk.service as sv
    from whaleproof.core.data_layer.store import Store
    calls = []
    monkeypatch.setattr(sv, "ingest_bars", lambda *a, **k: None)
    monkeypatch.setattr(lv, "gex_levels", lambda *a, **k: None)
    monkeypatch.setattr(lv, "darkpool_levels", lambda *a, **k: [])
    monkeypatch.setattr(lv, "stock_state", lambda *a, **k: None)
    monkeypatch.setattr(lv, "refresh_vol", lambda c, s, t, d: calls.append(("vol", t)))
    monkeypatch.setattr(lv, "refresh_earnings", lambda c, s, t: calls.append(("earn", t)))
    monkeypatch.setattr(lv, "sector_of", lambda *a, **k: None)
    svc = sv.DeskService(tmp_path / "c.sqlite", "")
    svc.view("MU")
    svc._refresh_viewed(Store(tmp_path / "c.sqlite"), date(2026, 10, 6), live_day=True)
    assert ("vol", "MU") in calls and ("earn", "MU") in calls


def test_reporting_window_moves_to_the_next_session_after_the_close():
    """At 23:00 ET Tuesday the Sightings sidebar lists Wednesday's reporters, not the ones that already reported."""
    from datetime import UTC, datetime
    from whaleproof.desk.service import reporting_window
    cal = [{"ticker": "AAA", "report_date": "2026-10-06", "side": "afterhours"},
           {"ticker": "BBB", "report_date": "2026-10-07", "side": "premarket"},
           {"ticker": "CCC", "report_date": "2026-10-07", "side": "afterhours"}]
    day, w = reporting_window(cal, datetime(2026, 10, 6, 18, 0, tzinfo=UTC))          # 14:00 ET, session open
    assert day == "2026-10-06" and [r["ticker"] for r in w["afterhours"]] == ["AAA"] and w["premarket"] == []
    day, w = reporting_window(cal, datetime(2026, 10, 7, 3, 0, tzinfo=UTC))           # 23:00 ET
    assert day == "2026-10-07" and [r["ticker"] for r in w["premarket"]] == ["BBB"]
    day, _ = reporting_window(cal, datetime(2026, 10, 10, 15, 0, tzinfo=UTC))         # Saturday → Monday
    assert day == "2026-10-12"


def test_recent_days_reach_the_hold_that_sells_today():
    """10-07: Sep 30 signals sell at the Oct 7 close, but a 4-session lookback from Oct 7 stopped at Oct 1, so after the
    open Sightings dropped them on their sell day (no live price or quote, 'Selling next' skipped today)."""
    from datetime import date

    from whaleproof import market_calendar as mc
    from whaleproof.desk.service import HOLD_LOOKBACK
    from whaleproof.desk.signals import exit_session
    for day in (date(2026, 10, 7), date(2026, 11, 30), date(2026, 12, 28)):   # plain week, after Thanksgiving, after Xmas
        seen, d = [], day
        for _ in range(HOLD_LOOKBACK):
            d = mc.previous_session(d)
            seen.append(d)
        assert any(exit_session(x) == day for x in seen)                  # the hold selling at today's close
        assert exit_session(mc.previous_session(d)) < day                 # one further back is already sold


def test_entry_day_tickers_need_todays_bar_once_the_market_has_opened(store):
    """Owner 10-07: signals bought at today's open sat in 'buying at the open' all day, because today's bar (the entry
    price) was only fetched by the close job. During the session the desk fetches it for those tickers."""
    from whaleproof.core.data_layer.models import Bar
    from whaleproof.desk.service import entry_day_tickers
    today = date(2026, 10, 7)
    tracked = [{"ticker": "CRDO", "entry": "2026-10-07"}, {"ticker": "IREN", "entry": "2026-10-07"},
               {"ticker": "AMAT", "entry": "2026-10-06"}, {"ticker": "CRDO", "entry": "2026-10-07"}]
    open_ = datetime(2026, 10, 7, 9, 31, tzinfo=mc.NY)
    assert entry_day_tickers(store, tracked, open_) == ["CRDO", "IREN"]
    store.put_ohlc("IREN", [Bar(today, 38.5, 39.0, 38.2, 38.8, 1e6)])
    assert entry_day_tickers(store, tracked, open_) == ["CRDO"]                   # IREN's open is in
    assert entry_day_tickers(store, tracked, datetime(2026, 10, 7, 9, 0, tzinfo=mc.NY)) == []   # not open yet


def test_day_is_final_only_after_a_flow_pull_at_or_after_its_decision_time(tmp_path, monkeypatch):
    """Bug 10-16: a restart at 7:32 PM ET after the live feed had stopped at 3:03 PM built the day's signals from the
    alerts already saved; Track record froze them a minute before the catch-up pull reached CIEN's 3:24 PM alert.
    The refresher now says when a day's signals are final: built after a successful flow pull made at or after the
    close + 15 min. Before that, or when the pull fails, they stay provisional."""
    from types import SimpleNamespace

    import whaleproof.desk.live as lv
    import whaleproof.desk.service as sv
    from whaleproof.core.data_layer.store import Store
    ok = {"pull": True}

    def pull(*a, **k):
        if not ok["pull"]:
            raise OSError("network down")
        return lv.FlowPull(0, True)
    monkeypatch.setattr(lv, "pull_flow_incremental", pull)
    for fn in ("market_tide", "sector_tides", "gex_levels", "stock_state"):
        monkeypatch.setattr(lv, fn, lambda *a, **k: [])

    def desk():
        svc = sv.DeskService(tmp_path / "c.sqlite", "")
        svc.client = SimpleNamespace(usage=SimpleNamespace(daily_count=None, daily_limit=None), get=None)
        svc.mode_env = "full"
        return svc
    st = Store(tmp_path / "c.sqlite")
    svc = desk()
    svc.refresh(st, datetime(2026, 10, 16, 19, 30, tzinfo=UTC))        # Fri 3:30 PM ET: still forming
    assert svc.snapshot().signals.day == "2026-10-16" and not svc.snapshot().signals_final
    svc = desk()
    svc.refresh(st, datetime(2026, 10, 16, 23, 32, tzinfo=UTC))        # 7:32 PM ET restart, catch-up pull succeeds
    assert svc.snapshot().signals.day == "2026-10-16" and svc.snapshot().signals_final
    ok["pull"] = False
    svc = desk()
    svc.refresh(st, datetime(2026, 10, 16, 23, 32, tzinfo=UTC))        # catch-up pull fails → not final
    assert svc.snapshot().signals is not None and not svc.snapshot().signals_final
    svc = desk()
    svc.client = None                                                   # no key: nothing can catch up → not final
    svc.refresh(st, datetime(2026, 10, 16, 23, 32, tzinfo=UTC))
    assert not svc.snapshot().signals_final


def test_unsaved_past_days_are_caught_up_before_they_count_as_final(tmp_path, monkeypatch):
    """Owner 10-19: a day the desk was off for over its close (restart only after the next open) used to be saved from
    whatever alerts were stored. The refresher now pulls the rest of each unsaved past day the API names (newest
    first, stops at a stored alert: ~1 call when nothing was missed) and only then reports it caught up."""
    from types import SimpleNamespace

    import whaleproof.desk.live as lv
    import whaleproof.desk.service as sv
    from whaleproof.core.data_layer.store import Store
    pulled, ok = [], {"pull": True}

    def pull(c, store, d):
        pulled.append(d.isoformat())
        if not ok["pull"]:
            raise OSError("network down")
        return lv.FlowPull(3, True)
    monkeypatch.setattr(lv, "pull_flow_incremental", pull)
    for fn in ("market_tide", "sector_tides", "gex_levels", "stock_state"):
        monkeypatch.setattr(lv, fn, lambda *a, **k: [])

    def desk():
        svc = sv.DeskService(tmp_path / "c.sqlite", "")
        svc.client = SimpleNamespace(usage=SimpleNamespace(daily_count=None, daily_limit=None), get=None)
        svc.mode_env = "full"
        svc.catchup_days_fn = lambda: ["2026-10-16"]
        return svc
    st = Store(tmp_path / "c.sqlite")
    svc = desk()
    svc._past["2026-10-16"] = "stale"                                  # built before the catch-up → dropped
    svc.refresh(st, datetime(2026, 10, 19, 14, 0, tzinfo=UTC))         # Mon 10:00 ET restart
    assert pulled == ["2026-10-19", "2026-10-16"]
    assert svc.caught_up("2026-10-16") and svc._past["2026-10-16"] != "stale"      # rebuilt after the catch-up
    assert not svc.caught_up("2026-10-15")
    ok["pull"] = False
    svc = desk()
    svc.refresh(st, datetime(2026, 10, 19, 14, 0, tzinfo=UTC))
    assert not svc.caught_up("2026-10-16")


def test_keyless_desk_rereads_the_cache_so_mcp_matches_the_live_desk(tmp_path, monkeypatch):
    """10-20: the MCP (no key) filled spot/GEX once at start and kept them all day, so it showed Sep 29's gamma and
    old prices while the dashboard showed today's. A keyless desk reads a cache the live desk keeps writing: every
    minute it re-reads the panels, so both say the same thing."""
    import time as _time

    from whaleproof.core.data_layer.fetch import cache_key
    from whaleproof.core.data_layer.store import Store
    from whaleproof.desk.service import DeskService
    st = Store(tmp_path / "c.sqlite")

    def put(flip: float, spot: float) -> None:
        st.cache_put(cache_key("/api/stock/SPY/gex-levels", {"date": "2026-10-20", "source": "oi"}),
                     "/api/stock/SPY/gex-levels", {"data": [{"date": "2026-10-20", "gamma_flip": str(flip),
                                                              "call_wall": "800", "put_wall": "700", "gamma_magnet": "760"}]})
        st.cache_put(cache_key("/api/stock/SPY/stock-state", {}), "/api/stock/SPY/stock-state",
                     {"data": {"close": str(spot), "open": "765", "prev_close": "766", "market_time": "regular"}})

    clock = [1_000_000.0]
    monkeypatch.setattr(_time, "time", lambda: clock[0])
    put(765.0, 768.0)
    svc = DeskService(tmp_path / "c.sqlite", "")                       # no key → cache only (the MCP)
    at = datetime(2026, 10, 20, 14, 0, tzinfo=UTC)                     # Tue 10:00 ET, market open
    svc.refresh(st, at)
    assert svc.snapshot().gex["SPY"]["gamma_flip"] == 765.0
    put(770.0, 762.0)                                                  # the live desk writes newer pulls
    clock[0] += 61
    svc.refresh(st, at)
    assert svc.snapshot().gex["SPY"]["gamma_flip"] == 770.0
    assert svc.snapshot().spot["SPY"]["last"] == 762.0


def test_open_journal_trades_get_a_live_price_and_each_days_close(tmp_path, monkeypatch):
    """10-20: journal trades on tickers outside the watchlist were priced at whatever bar an earlier page left (GWRE
    at Oct 14's close on Oct 20). Open journal stock tickers now join the live price list, and get one daily-bar pull
    per finished session so 'last close' is the real one."""
    import whaleproof.desk.service as sv
    from whaleproof.core.data_layer.store import Store
    calls = []
    monkeypatch.setattr(sv, "ingest_bars", lambda c, s, t, ttl: calls.append(t))
    svc = sv.DeskService(tmp_path / "c.sqlite", "", watchlist_fn=lambda: ["WWW"], journal_fn=lambda: ["GWRE", "WWW"])
    svc.client = object()                                              # pretend a key: pulls allowed
    st = Store(tmp_path / "c.sqlite")
    assert svc._spot_tickers([{"ticker": "SIG"}]) == ["SPY", "QQQ", "IWM", "WWW", "GWRE", "SIG"]
    at = datetime(2026, 10, 20, 14, 0, tzinfo=UTC)                     # Tue 10:00 ET → last finished session Mon 10-19
    svc._refresh_journal_bars(st, at)
    svc._refresh_journal_bars(st, at)
    assert calls == ["GWRE", "WWW"]                                    # once per ticker per finished session
    svc._refresh_journal_bars(st, datetime(2026, 10, 20, 21, 0, tzinfo=UTC))   # after Tue's close → Tue's bar
    assert calls == ["GWRE", "WWW", "GWRE", "WWW"]


def test_past_days_read_their_why_lines_from_the_frozen_record(tmp_path):
    """10-20: Track record froze AXTI's Oct 19 why-line with realized vol 104%; after UW published Oct 19's window the
    next day, Sightings and the MCP recomputed 110%. A past day with a frozen file now shows the frozen why-lines and
    value note, so every page and the MCP say the same thing."""
    import json

    from whaleproof.core.data_layer.store import Store
    from whaleproof.desk.service import DeskService
    st = Store(tmp_path / "c.sqlite")
    _store_alerts(st, raw_alert(id="w", ticker="AAA", underlying_price="100", strike="110", expiry="2026-11-20",
                                total_premium="2000000", total_ask_side_prem="1950000", total_bid_side_prem="50000",
                                option_chain="AAA261120C00110000"))
    svc = DeskService(tmp_path / "c.sqlite", "")
    nxt = date(2026, 9, 28)                                            # Mon: the lookback reaches Fri Sep 25
    fresh = next(d for d in svc.recent_days(st, nxt) if d.day == D.isoformat()).signals[0]
    live = tmp_path / "desk" / "live"
    live.mkdir(parents=True)
    frozen = fresh | {"why": ["frozen line"], "value": {"verdict": "fair", "reason": "frozen note"}}
    (live / f"{D.isoformat()}.json").write_text(json.dumps([frozen]))
    svc2 = DeskService(tmp_path / "c.sqlite", "")
    got = next(d for d in svc2.recent_days(st, nxt) if d.day == D.isoformat()).signals[0]
    assert got["why"] == ["frozen line"] and got["value"]["reason"] == "frozen note"
    assert got["ticker"] == "AAA" and got["exit_by"] == fresh["exit_by"]


def test_weekend_catchup_cut_short_keeps_going_while_it_makes_progress(tmp_path, monkeypatch):
    """10-22: on a closed day the flow job runs once per start. A new install on a Saturday catches up every live
    day in that one pass; a busy day cut by the page cap stayed incomplete until Monday. While a pull still stores new
    alerts the job comes due again; a pull that stores nothing (UW refusing) waits as before."""
    from types import SimpleNamespace

    import whaleproof.desk.live as lv
    import whaleproof.desk.service as sv
    from whaleproof.core.data_layer.store import Store
    pulls = iter([lv.FlowPull(0, True), lv.FlowPull(8000, False), lv.FlowPull(0, True), lv.FlowPull(600, True),
                  lv.FlowPull(0, True)])
    calls = []

    def pull(c, store, d):
        calls.append(d.isoformat())
        return next(pulls)
    monkeypatch.setattr(lv, "pull_flow_incremental", pull)
    for fn in ("market_tide", "sector_tides", "gex_levels", "stock_state"):
        monkeypatch.setattr(lv, fn, lambda *a, **k: [])
    svc = sv.DeskService(tmp_path / "c.sqlite", "")
    svc.client = SimpleNamespace(usage=SimpleNamespace(daily_count=None, daily_limit=None), get=None)
    svc.mode_env = "full"
    svc.catchup_days_fn = lambda: ["2026-10-01"]
    st = Store(tmp_path / "c.sqlite")
    sat = datetime(2026, 10, 3, 16, 0, tzinfo=UTC)                   # Saturday 12:00 ET
    svc.refresh(st, sat)                                               # Oct 2 caught up, Oct 1 cut at 8,000
    svc.refresh(st, sat)                                               # due again at once: Oct 1 finishes
    assert calls == ["2026-10-02", "2026-10-01", "2026-10-02", "2026-10-01"] and svc.caught_up("2026-10-01")
    svc.refresh(st, sat)
    assert len(calls) == 4                                             # all caught up: once per start, as before


def test_caught_up_past_day_is_scored_with_its_context_before_it_counts_as_final(tmp_path, monkeypatch):
    """10-22 fresh-install test: a day caught up after its close (fresh install, desk off overnight) was scored from the
    cache only. Long shots need IV rank, which only a live fetch brings, so Sep 30 froze with 4 of its 7 signals. The
    refresher now scores a caught-up past day the way it scores today (fetching candidates' earnings, sector and IV
    rank), and only then reports the day caught up, so nothing freezes it from the bare cache first."""
    from types import SimpleNamespace

    import whaleproof.desk.live as lv
    import whaleproof.desk.service as sv
    from whaleproof.core.data_layer.store import Store
    monkeypatch.setattr(lv, "pull_flow_incremental", lambda c, store, d: lv.FlowPull(3, True))
    for fn in ("market_tide", "sector_tides", "gex_levels", "stock_state"):
        monkeypatch.setattr(lv, fn, lambda *a, **k: [])
    svc = sv.DeskService(tmp_path / "c.sqlite", "")
    svc.client = SimpleNamespace(usage=SimpleNamespace(daily_count=None, daily_limit=None), get=None)
    svc.mode_env = "full"
    svc.catchup_days_fn = lambda: ["2026-10-16"]
    seen = {}

    def compute(store, d, as_of, fetch=None):
        if d.isoformat() == "2026-10-16":
            seen["fetch"], seen["final"] = fetch is not None, svc.caught_up("2026-10-16")
        return sv.DaySignals(d.isoformat(), as_of.isoformat(), {"raw": 1}, [], [], {}, [])
    monkeypatch.setattr(sv, "compute_signals", compute)
    st = Store(tmp_path / "c.sqlite")
    svc.refresh(st, datetime(2026, 10, 19, 14, 0, tzinfo=UTC))         # Mon 10:00 ET restart
    assert seen == {"fetch": True, "final": False}
    assert svc.caught_up("2026-10-16") and svc._past["2026-10-16"].day == "2026-10-16"


def test_caught_up_past_day_gets_its_prices_at_once_even_on_a_weekend(tmp_path, monkeypatch):
    """10-23 fresh-install test: a day caught up later showed "waiting" in Track record until the close job's next run:
    up to 30 min before the open or after the close, after 4:15 PM during the session, never on a weekend. The pass
    that catches a day up now runs the close job too; without a catch-up the job keeps its old hours."""
    from types import SimpleNamespace

    import whaleproof.desk.live as lv
    import whaleproof.desk.service as sv
    from whaleproof.core.data_layer.store import Store
    caught = {"ok": True}
    monkeypatch.setattr(lv, "pull_flow_incremental", lambda c, store, d: lv.FlowPull(3, caught["ok"]))
    for fn in ("market_tide", "sector_tides", "gex_levels", "stock_state"):
        monkeypatch.setattr(lv, fn, lambda *a, **k: [])
    monkeypatch.setattr(sv, "compute_signals", lambda store, d, as_of, fetch=None: sv.DaySignals(
        d.isoformat(), as_of.isoformat(), {"raw": 1}, [], [], {}, []))
    ran = []
    monkeypatch.setattr(sv, "close_update", lambda c, store, items, day: ran.append(day.isoformat()) or
                        {"day": day.isoformat(), "bars_missing": [], "options_missing": []})

    def desk():
        svc = sv.DeskService(tmp_path / "c.sqlite", "")
        svc.client = SimpleNamespace(usage=SimpleNamespace(daily_count=None, daily_limit=None), get=None)
        svc.mode_env = "full"
        svc.catchup_days_fn = lambda: ["2026-10-01"]
        svc.tracker_open_fn = lambda: [("BA", None)]
        return svc
    st = Store(tmp_path / "c.sqlite")
    sat = datetime(2026, 10, 3, 16, 0, tzinfo=UTC)                   # Saturday 12:00 ET
    svc = desk()
    svc.refresh(st, sat)
    assert ran == ["2026-10-02"]                                       # caught up → priced in the same pass
    ran.clear()
    caught["ok"] = False
    svc = desk()
    svc.refresh(st, sat)
    assert ran == []                                                   # no catch-up: weekend hours as before


def test_keyless_reader_never_writes_the_surfacing_log_and_sees_the_desks(tmp_path, monkeypatch):
    """10-22: the MCP runs a keyless DeskService over the same data dir. It updated and saved today's surfacing log too,
    from a copy it loaded once, so the desk and the MCP overwrote each other's entries. Only a desk with a key writes;
    a keyless reader re-reads the file the desk keeps writing."""
    import whaleproof.desk.service as sv
    from whaleproof.core.data_layer.store import Store
    from whaleproof.desk import surfacing
    sig = sv.DaySignals("2026-10-07", "", {"raw": 1}, [{"ticker": "HPE", "direction": 1, "tier": "far_otm", "exit_by": "2026-10-14", "contract": None, "expiry": "2026-11-20"}], [], {}, [])
    monkeypatch.setattr(sv, "compute_signals", lambda *a, **k: sig)
    monkeypatch.setattr(sv.DeskService, "recent_days", lambda *a, **k: [])
    svc = sv.DeskService(tmp_path / "c.sqlite", "")                  # keyless, like the MCP
    st = Store(tmp_path / "c.sqlite")
    svc.refresh(st, datetime(2026, 10, 7, 15, 0, tzinfo=UTC))       # Wednesday 11:00 ET, market open
    assert not svc._surf_path("2026-10-07").exists()
    desk_log = surfacing.update(surfacing.empty("2026-10-07"), [{"ticker": "MU", "direction": 1}], [],
                                datetime(2026, 10, 7, 15, 1, tzinfo=UTC))
    surfacing.save(svc._surf_path("2026-10-07"), desk_log)          # the live desk writes
    assert "MU:1" in svc.surfacing_log("2026-10-07")["seen"]


def test_keyless_reader_remembers_a_live_day_only_once_the_desk_saved_it(tmp_path, monkeypatch):
    """10-22: the MCP's keyless service memoized every past day forever. One computed while the desk was still catching
    that day up (a Saturday install) stayed incomplete in the MCP until it restarted. A keyless reader now keeps a live
    day only once the desk saved it as final; until then it recomputes from the cache the desk keeps filling."""
    import whaleproof.desk.service as sv
    from whaleproof.core.data_layer.store import Store
    n = []

    def compute(store, d, as_of, fetch=None):
        n.append(d.isoformat())
        return sv.DaySignals(d.isoformat(), "", {"raw": 0}, [], [], {}, [])
    monkeypatch.setattr(sv, "compute_signals", compute)
    svc = sv.DeskService(tmp_path / "c.sqlite", "")                  # keyless, like the MCP
    st = Store(tmp_path / "c.sqlite")
    svc.recent_days(st, date(2026, 10, 9), n=1)                       # Oct 8: live day, not saved yet
    svc.recent_days(st, date(2026, 10, 9), n=1)
    assert n == ["2026-10-08"]                                         # reused for a few minutes
    monkeypatch.setattr(sv, "PAST_SOFT_S", 0)                          # …then recomputed
    svc.recent_days(st, date(2026, 10, 9), n=1)
    assert n == ["2026-10-08", "2026-10-08"]
    (tmp_path / "desk" / "live").mkdir(parents=True)
    (tmp_path / "desk" / "live" / "2026-10-08.json").write_text("[]")  # the desk saved it
    svc.recent_days(st, date(2026, 10, 9), n=1)
    svc.recent_days(st, date(2026, 10, 9), n=1)
    assert n == ["2026-10-08"] * 3                                    # saved: kept for good
