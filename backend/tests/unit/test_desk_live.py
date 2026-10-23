"""Signal Desk live layer: incremental flow pull, budget/quota state, per-source failures never crash."""
from datetime import date

from tests.conftest import raw_alert
from whaleproof.core.data_layer.client import UWError, UWQuotaExhausted
from whaleproof.desk.live import LiveState, pull_flow_incremental, safe


class FakeClient:
    def __init__(self, responses):
        self.responses, self.calls = responses, []

    def get(self, path, params=None):
        self.calls.append((path, dict(params or {})))
        r = self.responses[path]
        return r(params or {}) if callable(r) else r


D = date(2026, 9, 25)


def test_incremental_pull_stops_at_known_alert(store):
    old = [raw_alert(id=f"o{i}", created_at=f"2026-09-25T14:{i:02d}:00Z") for i in range(50, 0, -1)]
    store.upsert_alerts([{**r, "session_date": "2026-09-25"} for r in old[:1]])   # newest old alert already stored
    new = [raw_alert(id=f"n{i}", created_at=f"2026-09-25T15:{i:02d}:00Z") for i in range(10, 0, -1)]
    page = new + old            # 60 rows, newest first; contains a known id → no second page
    c = FakeClient({"/api/option-trades/flow-alerts": {"data": page * 4}})   # 240 ≥ page size would normally page on
    n = pull_flow_incremental(c, store, D)
    assert len(c.calls) == 1 and n.stored >= 10 and n.caught_up


def test_incremental_pull_pages_until_short_page(store):
    p1 = [raw_alert(id=f"a{i}", created_at=f"2026-09-25T15:{i % 60:02d}:{i // 60:02d}Z") for i in range(200)]
    p1.sort(key=lambda r: r["created_at"], reverse=True)
    p2 = [raw_alert(id="b0", created_at="2026-09-25T13:00:00Z")]
    pages = iter([{"data": p1}, {"data": p2}])
    c = FakeClient({"/api/option-trades/flow-alerts": lambda p: next(pages)})
    pull_flow_incremental(c, store, D)
    assert len(c.calls) == 2


def test_safe_records_error_and_returns_default():
    st = LiveState()
    def boom():
        raise UWError("500 /x")
    assert safe(st, "tide", boom, default=[]) == []
    assert st.sources["tide"]["ok"] is False and "500" in st.sources["tide"]["error"]


def test_safe_quota_sets_flag():
    st = LiveState()
    def quota():
        raise UWQuotaExhausted("used")
    safe(st, "flow", quota, default=None)
    assert st.quota_exhausted and st.sources["flow"]["ok"] is False


def test_safe_success_marks_fresh():
    st = LiveState()
    assert safe(st, "calendar", lambda: [1], default=[]) == [1]
    assert st.sources["calendar"]["ok"] is True and st.sources["calendar"]["at"]


def test_gex_all_null_row_is_none(store):
    from whaleproof.desk.live import gex_levels
    c = FakeClient({"/api/stock/SPY/gex-levels": {"data": [{"date": "2026-09-30", "call_wall": None, "put_wall": None,
                                                            "gamma_flip": None, "gamma_magnet": None}]}})
    assert gex_levels(c, store, "SPY", D, True) is None


def test_cache_only_reads_stale_cache_and_never_calls(store):
    from whaleproof.core.data_layer.fetch import cached_get
    from whaleproof.desk.live import CacheOnlyClient, StaleOkStore
    store.cache_put('/x?{"a": 1}', "/x", {"data": [1]})
    st = StaleOkStore(store)
    assert cached_get(CacheOnlyClient(), st, "/x", {"a": 1}, 0) == {"data": [1]}      # ttl 0 would normally refetch
    import pytest
    from whaleproof.core.data_layer.client import UWError
    with pytest.raises(UWError):
        cached_get(CacheOnlyClient(), st, "/missing", {}, 0)


def test_refresh_vol_also_stores_iv_rank(store):
    """Live far-OTM verdict uses IV rank (owner 2026-09-30) → the candidate fetch must pull it (1 call)."""
    from whaleproof.desk.live import refresh_vol
    c = FakeClient({"/api/stock/ZZZ/volatility/realized": {"data": []},
                    "/api/stock/ZZZ/iv-rank": {"data": [{"date": "2026-09-24", "iv_rank_1y": "12.5"}]}})
    refresh_vol(c, store, "ZZZ", D)
    assert store.latest_metric("ZZZ", D, "iv_rank")[1] == 12.5
    assert ("/api/stock/ZZZ/iv-rank", {"timespan": "1y"}) in c.calls


def test_earnings_session_pages_and_drops_rows_from_other_dates(store):
    """Calendar lists can exceed UW's page size in peak season; a row dated ≠ the asked day is a fallback, not a hit."""
    from whaleproof.desk.live import earnings_session
    day = date(2026, 10, 28)
    p0 = [{"symbol": f"T{i}", "report_date": "2026-10-28", "report_time": "premarket", "expected_move_perc": "0.05",
           "has_options": True} for i in range(100)]
    p1 = [{"symbol": "LAST", "report_date": "2026-10-28", "expected_move_perc": None},
          {"symbol": "OLD", "report_date": "2026-10-27", "expected_move_perc": "0.04"}]
    c = FakeClient({"/api/earnings/premarket": lambda p: {"data": [p0, p1, []][p["page"]]}})
    out = earnings_session(c, store, "premarket", day)
    assert [x["page"] for _, x in c.calls] == [0, 1] and all(x["limit"] == 100 for _, x in c.calls)
    assert len(out) == 101 and out[-1]["ticker"] == "LAST" and out[-1]["expected_move_perc"] is None
    assert out[0]["report_time"] == "premarket" and out[0]["has_options"] is True


def test_incremental_pull_says_whether_it_caught_up(store):
    """Bug 10-16 follow-up: Track record saves a day only once the catch-up reached alerts already stored (or the start
    of the day). A pull that runs out of pages (busy days now near 8K alerts) or gets a stuck cursor hasn't."""
    short = [raw_alert(id="s0", created_at="2026-09-25T15:00:00Z")]
    assert pull_flow_incremental(FakeClient({"/api/option-trades/flow-alerts": {"data": short}}), store, D).caught_up
    pg = iter(range(100))

    def stuck(p):                                                       # new ids, same time every page → cursor can't move
        k = next(pg)
        return {"data": [raw_alert(id=f"x{k}-{i}", created_at="2026-09-25T15:00:00Z") for i in range(200)]}
    r = pull_flow_incremental(FakeClient({"/api/option-trades/flow-alerts": stuck}), store, D)
    assert not r.caught_up
    n = iter(range(10_000))

    def endless(p):
        k = next(n)
        return {"data": [raw_alert(id=f"e{k}-{i}", created_at=f"2026-09-25T{15 - k // 60 % 9:02d}:{59 - k % 60:02d}:{59 - i % 60:02d}Z")
                         for i in range(200)]}
    r = pull_flow_incremental(FakeClient({"/api/option-trades/flow-alerts": endless}), store, D)
    assert not r.caught_up                                              # ran out of pages


def test_incremental_pull_does_not_stop_on_alerts_repeated_at_the_page_boundary(store):
    """Bug 10-22: UW's `older_than` is inclusive, so alerts sharing the oldest millisecond of one page come back on the
    next. The pull took those repeats for "already stored" and stopped: a desk started at 11:33 lost 9:30–11:01."""
    from datetime import datetime, timedelta, timezone
    t0 = datetime(2026, 9, 25, 13, 30, tzinfo=timezone.utc)
    day = [raw_alert(id=f"d{k}", created_at=(t0 + timedelta(seconds=k // 3)).isoformat().replace("+00:00", "Z"))
           for k in range(700)]                                         # 3 alerts per second → boundaries share a time
    day.sort(key=lambda r: r["created_at"], reverse=True)

    def uw(p):
        c = p["older_than"]
        cut = datetime.fromtimestamp(int(c) / 1000, timezone.utc) if c.isdigit() else datetime(2026, 9, 26, tzinfo=timezone.utc)
        return {"data": [r for r in day if datetime.fromisoformat(r["created_at"].replace("Z", "+00:00")) <= cut][:200]}
    r = pull_flow_incremental(FakeClient({"/api/option-trades/flow-alerts": uw}), store, D)
    n = store.conn.execute("SELECT COUNT(*) FROM flow_alerts WHERE session_date = '2026-09-25'").fetchone()[0]
    assert n == 700 and r.caught_up


def _uw_day(n: int, per_s: int = 3):
    """A fake UW day of n alerts (per_s share each second) and an `older_than`-inclusive server over it."""
    from datetime import datetime, timedelta, timezone
    t0 = datetime(2026, 9, 25, 13, 30, tzinfo=timezone.utc)
    day = [raw_alert(id=f"d{k}", created_at=(t0 + timedelta(seconds=k // per_s)).isoformat().replace("+00:00", "Z"))
           for k in range(n)]
    day.sort(key=lambda r: r["created_at"], reverse=True)

    def uw(p):
        c = p["older_than"]
        cut = datetime.fromtimestamp(int(c) / 1000, timezone.utc) if c.isdigit() else datetime(2026, 9, 26, tzinfo=timezone.utc)
        return {"data": [r for r in day if datetime.fromisoformat(r["created_at"].replace("Z", "+00:00")) <= cut][:200]}
    return day, uw


def _stored(store) -> int:
    return store.conn.execute("SELECT COUNT(*) FROM flow_alerts WHERE session_date = '2026-09-25'").fetchone()[0]


def test_catchup_cut_by_a_uw_error_is_resumed_by_the_next_pull(store):
    """A catch-up that UW cuts off mid-way (500, timeout) left a hole: the next pull saw its own newest alerts at the
    top, called the day caught up, and the hole stayed for good (and Track record froze it)."""
    _, uw = _uw_day(900)
    calls = iter(range(100))

    def flaky(p):
        if next(calls) == 2:
            raise UWError("500 flow-alerts")
        return uw(p)
    c = FakeClient({"/api/option-trades/flow-alerts": flaky})
    try:
        pull_flow_incremental(c, store, D)
    except UWError:
        pass
    assert _stored(store) < 900
    r = pull_flow_incremental(c, store, D)
    assert _stored(store) == 900 and r.caught_up


def test_catchup_cut_by_the_page_cap_is_resumed_by_the_next_pull(store, monkeypatch):
    import whaleproof.desk.live as lv
    monkeypatch.setattr(lv, "MAX_PAGES", 2)
    _, uw = _uw_day(900)
    c = FakeClient({"/api/option-trades/flow-alerts": uw})
    assert not pull_flow_incremental(c, store, D).caught_up
    while not (r := pull_flow_incremental(c, store, D)).caught_up:
        pass
    assert _stored(store) == 900 and r.caught_up


def test_past_day_pull_starts_at_its_own_end_not_the_next_days(store, monkeypatch):
    """10-23 fresh-install test: `older_than=<next date>` makes UW return the whole next day first. Catching up a past
    day followed by a busy one (Oct 15 → Oct 16, 7,631 alerts) spent the 40-page cap on Oct 16, stored nothing for Oct
    15 and started over from the top every pull, so the day never caught up. The top cursor is now the next day's
    midnight in New York, and a hole is saved once."""
    from datetime import datetime, timedelta, timezone
    import whaleproof.desk.live as lv
    monkeypatch.setattr(lv, "MAX_PAGES", 3)
    t0 = datetime(2026, 9, 25, 13, 30, tzinfo=timezone.utc)
    day = [raw_alert(id=f"d{k}", created_at=(t0 + timedelta(seconds=k)).isoformat().replace("+00:00", "Z")) for k in range(500)]
    t1 = datetime(2026, 9, 26, 13, 30, tzinfo=timezone.utc)
    nxt = [raw_alert(id=f"n{k}", created_at=(t1 + timedelta(seconds=k)).isoformat().replace("+00:00", "Z")) for k in range(2000)]
    rows_ = sorted(day + nxt, key=lambda r: r["created_at"], reverse=True)

    def uw(p):                                  # UW: a date cursor means "through the end of that date"
        c = p["older_than"]
        cut = datetime.fromtimestamp(int(c) / 1000, timezone.utc) if c.isdigit() else datetime(2026, 9, 27, 4, tzinfo=timezone.utc)
        return {"data": [r for r in rows_ if datetime.fromisoformat(r["created_at"].replace("Z", "+00:00")) <= cut][:200]}
    c = FakeClient({"/api/option-trades/flow-alerts": uw})
    r = pull_flow_incremental(c, store, D)
    assert _stored(store) == 500 and r.caught_up and len(c.calls) == 3


def test_page_cap_hole_is_saved_once(store, monkeypatch):
    import json
    import whaleproof.desk.live as lv
    monkeypatch.setattr(lv, "MAX_PAGES", 1)
    _, uw = _uw_day(2000)
    c = FakeClient({"/api/option-trades/flow-alerts": uw})
    for _ in range(3):
        pull_flow_incremental(c, store, D)
    holes = json.loads(store.get_checkpoint("flow_gaps:2026-09-25"))
    assert len(holes) == len(set(holes))
