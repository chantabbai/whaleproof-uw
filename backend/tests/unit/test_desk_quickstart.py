"""Quick-start: backfill the last few sessions on a fresh key, inside a hard call cap, resumable."""
from datetime import date

import pytest

from tests.conftest import raw_alert
from whaleproof.core.data_layer.client import UWAuthError, UWBudgetExceeded, UWError, Usage
from whaleproof.desk.quickstart import CallCap, run, tier_possible

D1, D2 = date(2026, 9, 24), date(2026, 9, 25)
FLOW = "/api/option-trades/flow-alerts"


class FakeClient:
    """Answers by path; `step` = how much UW's daily counter moves per call (retries / other users of the key)."""
    def __init__(self, flow_by_day, step=1, fail_day=None):
        self.flow_by_day, self.step, self.fail_day = flow_by_day, step, fail_day
        self.usage, self.calls = Usage(daily_count=1000), []

    def get(self, path, params=None):
        params = dict(params or {})
        self.calls.append((path, params))
        self.usage.daily_count += self.step
        if path == FLOW:
            if params["newer_than"] == self.fail_day:
                raise UWError("403 flow: historic_data_access_missing")
            return {"data": self.flow_by_day.get(params["newer_than"], [])}
        if path.endswith("/info"):
            return {"data": [{"sector": "Technology"}]}
        if path.endswith("/historic"):
            return {"chains": []}
        return {"data": []}

    def paths(self, needle):
        return [p for p, _ in self.calls if needle in p]


def whale(**over):   # $1.5M call, 200 strike vs 190 spot → 5.3% OTM: a whale-tier candidate
    return raw_alert(**({"total_premium": "1500000", "total_ask_side_prem": "1400000", "total_bid_side_prem": "100000"}
                        | over))


def small(**over):   # $200K, 2% OTM: can never reach a tier
    return raw_alert(**({"id": "s1", "ticker": "AAPL", "option_chain": "AAPL261016C00200000", "underlying_price": "196",
                         "total_premium": "200000", "total_ask_side_prem": "190000", "total_bid_side_prem": "10000"}
                        | over))


def flow():
    return {"2026-09-24": [whale(id="w1", created_at="2026-09-24T14:30:00Z"), small(created_at="2026-09-24T15:00:00Z")],
            "2026-09-25": [whale(id="w2", created_at="2026-09-25T14:30:00Z")]}


def test_tier_possible(make_alert):
    assert tier_possible(make_alert(total_premium="1500000"))
    assert not tier_possible(make_alert(ticker="AAPL", underlying_price="196", total_premium="200000"))
    assert tier_possible(make_alert(underlying_price="160", total_premium="200000"))          # 25% OTM: far-OTM
    assert not tier_possible(make_alert(underlying_price="4", strike="5", total_premium="2000000"))   # under $5


def test_cap_counts_uw_header_not_just_own_calls():
    c = FakeClient({}, step=3)                       # every call moves UW's counter by 3 (retries, other users)
    cap = CallCap(c, max_calls=10)
    with pytest.raises(UWBudgetExceeded):
        for _ in range(10):
            cap.get("/api/x")
    assert len(c.calls) == 4 and cap.used() >= 10   # 1 + 3·3 = 10 by the header after 4 calls


def test_run_builds_signals_and_fetches_context_only_for_candidates(store):
    c = FakeClient(flow())
    res = run(c, store, [D2, D1], max_calls=500)
    assert res["stopped"] is None
    assert [d["signals"] for d in res["days"]] == [1, 1]
    assert c.paths("/api/earnings/NVDA") and not c.paths("/api/earnings/AAPL")      # small alert: no context calls
    assert c.paths("/api/stock/NVDA/iv-rank")          # whale tier too: the card shows the option value
    assert c.paths("/api/option-contract/NVDA261016C00200000/historic")            # tracker's option column
    assert c.paths("/api/stock/SPY/ohlc/1d")
    assert res["calls"] == len(c.calls)


def test_rerun_makes_no_calls(store):
    run(FakeClient(flow()), store, [D2, D1], max_calls=500)
    c = FakeClient(flow())
    run(c, store, [D2, D1], max_calls=500)
    assert c.calls == []                             # past-day flow cached forever, context within its 12 h TTL


def test_cap_stops_cleanly_and_resume_finishes(store):
    first = run(FakeClient(flow()), store, [D2, D1], max_calls=4)
    assert first["stopped"]
    second = run(FakeClient(flow()), store, [D2, D1], max_calls=500)
    assert second["stopped"] is None and [d["signals"] for d in second["days"]] == [1, 1]


def test_one_failing_day_does_not_abort_the_others(store):
    res = run(FakeClient(flow(), fail_day="2026-09-24"), store, [D2, D1], max_calls=500)
    assert res["days"][0]["signals"] == 1
    assert "historic_data_access_missing" in res["days"][1]["error"]


def test_auth_error_aborts(store):
    class Refused(FakeClient):
        def get(self, path, params=None):
            raise UWAuthError("401 bad key")
    with pytest.raises(UWAuthError):
        run(Refused({}), store, [D2], max_calls=500)


def test_no_cap_by_default_owner_10_16():
    """Owner 10-16 (UW lifted its call limits): quick-start has no call cap unless --max-calls is given.
    A 500 cap stopped a fresh-install run after 4 of 5 busy sessions (7.6K alerts a day)."""
    c = FakeClient({}, step=3)
    cap = CallCap(c, max_calls=None)
    for _ in range(50):
        cap.get("/api/x")
    assert len(c.calls) == 50
    from whaleproof.commands import quickstart as cmd
    import argparse
    seen = {}
    real = argparse.ArgumentParser.parse_args
    def grab(self, argv=None, ns=None):
        out = real(self, argv, ns)
        seen.update(vars(out))
        raise SystemExit(0)
    import pytest as _pt
    _mp = _pt.MonkeyPatch()
    _mp.setattr(argparse.ArgumentParser, "parse_args", grab)
    try:
        with _pt.raises(SystemExit):
            cmd.main([])
    finally:
        _mp.undo()
    assert seen["max_calls"] is None


def test_context_dates_use_new_york_today_not_the_computer_date(store, monkeypatch):
    """Bug 10-22: UW 422s a realized-vol `date` later than today in New York ("may not be a future EST date"). A user
    east of New York (Asia from midday ET, Europe evenings) ran quick-start on their local date → every day skipped."""
    from datetime import datetime

    import whaleproof.desk.quickstart as qs
    from whaleproof import market_calendar as mc

    class Ahead(date):                               # the computer's local date is already tomorrow
        @classmethod
        def today(cls):
            return datetime.now(mc.NY).date().replace(year=2099)
    monkeypatch.setattr(qs, "date", Ahead)
    c = FakeClient(flow())
    run(c, store, [D2], max_calls=500)
    asked = {p["date"] for path, p in c.calls if path.endswith("/volatility/realized")}
    assert asked == {datetime.now(mc.NY).date().isoformat()}
