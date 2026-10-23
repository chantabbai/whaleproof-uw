"""WhaleProof MCP server (Plan 3): thin tools over the same local API the dashboard uses — cache only, no UW calls.
Tested in memory with a fake API (no subprocess, no network)."""
import json

import pytest
from mcp import Client

from whaleproof.mcp_server import DISCLAIMER, build_server

PICK = {"pick_id": "a", "ticker": "KWEB", "direction": 1, "contract": "KWEB261218C00024000", "rank": 1,
        "session_date": "2026-09-28", "entry_session": "2026-09-29", "exit_by": "2026-10-12",
        "plan": {"entry_ref": 24.66, "invalidation": 23.53, "target": 26.0, "time_stop_sessions": 10, "structure": "long call"},
        "reasons_for": ["$2.12M calls, 100% ask-side"], "reasons_against": ["market tide bearish"],
        "confirmation": {"status": "confirmed", "ratio": 0.9}, "health": {"state": "HOLDING"},
        "outcome": {"status": "open", "return": 0.01}, "value": {"verdict": "cheap", "reason": "IV rank 28"},
        "pnl": {"contract": "KWEB261120C00024500", "entry_premium": 1.29, "ret_target_net": 0.46, "ret_stop_net": -0.58,
                "option_rr": 0.79, "delta": 0.56}}
FAKE = {
    "/api/picks": {"session_date": "2026-09-28", "entry_session": "2026-09-29", "picks": [PICK]},
    "/api/history": [PICK | {"kind": "official", "weights_version": "v0.5", "our_contract": "KWEB261120C00024500",
                             "option_result": 0.05}],
    "/api/finalists": {"session_date": "2026-09-28", "entry_session": "2026-09-29", "exit_by": "2026-10-05",
                       "overlap": [{"ticker": "BE", "direction": 1, "in": ["F.2", "F.3"], "waiting": []}],
                       "finalists": [{"id": "F.2", "name": "Cheap option, long", "blocks": ["option cheap", "long only"],
                                      "train": {"trades_per_day": 17.8, "win_rate": 0.48, "mean_x5": 0.009,
                                                "max_drawdown": -0.083},
                                      "exam": None, "waiting": [],
                                      "trades": [{"ticker": "BE", "direction": 1, "premium": 274000,
                                                  "contract": "BE261023C00305000", "also_in": ["F.3"],
                                                  "pnl": {"contract": "BE261120C00260000"}}]}]},
    "/api/scorecard": {"chain_valid": True, "picks_total": 10, "closed_count": 1, "open_count": 4,
                       "overall": {"n": 5, "hit_rate": 0.4, "mean": -0.0005}},
    "/api/pure": {"scorecard": {"all": {"closed": 0}}, "count": 86, "session_date": "2026-09-28", "by_setup": {}},
    "/api/combos": {"tested": 687, "finalists": [{"blocks": ["option cheap", "long only"], "mean_x5": 0.009}],
                    "ranked": [{"blocks": ["OI confirmed", "over 5% OTM"], "mean_x5": 0.0156, "win_rate": 0.55,
                                "max_drawdown": -0.1, "trades_per_day": 1.2}], "baseline": {"mean_x5": -0.0013}},
    "/api/ticker/BE": {"ticker": "BE", "alerts": [{"option_chain": "BE261023C00305000", "total_premium": "274000",
                                                     "created_at": "2026-09-28T15:00:00Z"}],
                       "bars": [{"date": "2026-09-28", "close": 250.0}], "pure": [], "scan": []},
    "/api/money-moved": [],
    "/api/desk/methodology": {"filter": {"far_otm": 0.15}, "citations": [],
                              "evidence": {"train_post": {"train": {"funnel": {"per_day": {"raw": 3000, "signals": 2}}, "signals": {"mean": 0.012, "n": 488}, "all_directional": {"mean": -0.001}}, "post": {"funnel": {"per_day": {"raw": 3000, "signals": 2}}, "signals": {"mean": 0.012, "n": 488}, "all_directional": {"mean": -0.001}}}, "holdout": {"funnel": {"per_day": {"raw": 3000, "signals": 2}}, "signals": {"mean": 0.012, "n": 488}, "all_directional": {"mean": -0.001}},
                                           "preperiod_farotm": {"funnel": {"per_day": {"raw": 3000, "signals": 2}}, "signals": {"mean": 0.012, "n": 488}, "all_directional": {"mean": -0.001}}},
                              "beta": {"holdout": {"signals": {"avg_beta": 2.43, "x5": {"mean": 0.0138},
                                                                "beta_adj": {"mean": 0.0057, "ci_low": -0.007, "ci_high": 0.016}},
                                                    "all": {"avg_beta": 1.6, "x5": {"mean": -0.0003}, "beta_adj": {"mean": -0.0005}}}}},
    "/api/desk/today": {"day": "2026-09-29", "funnel": {"raw": 3593, "directional": 478, "clean": 87, "signals": 1},
                        "signals": [{"ticker": "MRVL", "direction": 1, "tier": "whale", "why": ["$1.1M calls at the ask"],
                                     "premium": 1.1e6, "kind": "call", "strike": 110.0, "expiry": "2026-11-20",
                                     "otm_pct": 0.12, "entry": "2026-09-30", "exit_by": "2026-10-06"}], "active": [], "rejected_top": [{"ticker": "NVDA", "reason": "not clearly opening"}],
                        "regime": {"gamma": {"positive": True}, "tide_last": None},
                        "evidence": {"pre": {"signals": {"mean": 0.017, "n": 233}, "all": {"mean": -0.0007}},
                                     "train": {"signals": {"mean": 0.012, "n": 488}, "all": {"mean": -0.001}, "label": "in-sample"},
                                     "holdout": None, "post": {"signals": {"mean": -0.0155, "n": 318}, "all": {"mean": -0.0015}}}},
}


def fake_get(path: str):
    return FAKE.get(path)


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
async def client():
    async with Client(build_server(fake_get, legacy=True), raise_exceptions=True) as c:   # legacy tools still tested
        yield c


@pytest.mark.anyio
async def test_default_server_exposes_only_the_desk_tools():
    """Owner 2026-09-30: the old engine's tools (option picks, finalists…) are off by default — they contradict the
    tested 'act on the stock' result and their data is a stale copy in this fork."""
    async with Client(build_server(fake_get), raise_exceptions=True) as c:
        names = {t.name for t in (await c.list_tools()).tools}
    assert names == {"desk_signals", "desk_ticker", "desk_evidence", "desk_lookup", "desk_tracker", "desk_earnings"}


def data(result) -> dict:
    return result.structured_content if result.structured_content is not None else json.loads(result.content[0].text)


@pytest.mark.anyio
async def test_lists_the_tools(client):
    names = {t.name for t in (await client.list_tools()).tools}
    assert {"desk_signals", "desk_ticker", "desk_evidence", "todays_picks", "finalist_trades", "check_ticker", "explain_pick", "scorecard", "strategy_results",
            "money_moved"} <= names


@pytest.mark.anyio
async def test_todays_picks_is_compact_and_honest(client):
    d = data(await client.call_tool("todays_picks", {}))
    p = d["picks"][0]
    assert p["ticker"] == "KWEB" and p["we_buy"] == "KWEB $24.50 Call · Nov 20 '26 (KWEB261120C00024500)" and p["stop"] == 23.53
    assert p["option_at_target"] == 0.46 and d["status"] == "not proven" and d["disclaimer"] == DISCLAIMER


@pytest.mark.anyio
async def test_finalist_trades_include_overlap_and_learning_year(client):
    d = data(await client.call_tool("finalist_trades", {}))
    f = d["finalists"][0]
    assert f["id"] == "F.2" and f["trades"][0]["ticker"] == "BE" and f["trades"][0]["also_in"] == ["F.3"]
    assert f["learning_year"]["trades_per_day"] == 17.8 and f["final_exam"] == "not taken yet"
    assert d["overlap"][0]["ticker"] == "BE"


@pytest.mark.anyio
async def test_check_ticker_and_explain_pick(client):
    t = data(await client.call_tool("check_ticker", {"ticker": "be"}))
    assert t["ticker"] == "BE" and t["in_finalists"] == ["F.2"] and t["last_close"] == 250.0
    e = data(await client.call_tool("explain_pick", {"ticker": "kweb"}))
    assert e["picks"][0]["why"] == ["$2.12M calls, 100% ask-side"] and e["picks"][0]["option_result_estimate"] == 0.05
    missing = data(await client.call_tool("explain_pick", {"ticker": "ZZZ"}))
    assert missing["picks"] == [] and "no pick" in missing["note"]


@pytest.mark.anyio
async def test_scorecard_and_strategy_results(client):
    s = data(await client.call_tool("scorecard", {}))
    assert s["journal_untampered"] is True and s["official"]["scored"] == 5
    r = data(await client.call_tool("strategy_results", {"top": 5}))
    assert r["mixes_tested"] == 687 and r["top"][0]["rules"] == ["OI confirmed", "over 5% OTM"]


@pytest.mark.anyio
async def test_down_api_fails_soft():
    async with Client(build_server(lambda p: None), raise_exceptions=True) as c:
        for tool in ("desk_signals", "desk_evidence"):
            d = data(await c.call_tool(tool, {}))
            assert "not available" in d["error"]
    async with Client(build_server(lambda p: None, legacy=True), raise_exceptions=True) as c:
        assert "not available" in data(await c.call_tool("todays_picks", {}))["error"]


@pytest.mark.anyio
async def test_every_contract_code_is_readable(client):
    """Owner 09-29: no raw OCC codes in answers — readable text with the code in brackets once."""
    import re
    for tool, args in [("todays_picks", {}), ("finalist_trades", {}), ("check_ticker", {"ticker": "KWEB"}),
                       ("explain_pick", {"ticker": "KWEB"}), ("money_moved", {})]:
        txt = json.dumps(data(await client.call_tool(tool, args)))
        assert not re.search(r'"[A-Z.]+\d{6}[CP]\d{8}"', txt), tool


@pytest.mark.anyio
async def test_desk_signals_carry_reasons_funnel_and_disclaimer(client):
    d = data(await client.call_tool("desk_signals", {}))
    assert d["funnel"]["raw"] == 3593 and d["signals"][0]["why"] == ["$1.1M calls at the ask"]
    assert d["rejected_biggest"][0]["reason"] == "not clearly opening"
    assert "Not financial advice" in d["disclaimer"]
    ev = d["evidence"]
    assert [p["period"] for p in ev["periods"]] == ["Second sealed test · Oct 2023 – Sep 2024",
                                                   "Practice year · Oct 2024 – Sep 2025", "Recent months · Jun – Sep 2026"]
    pre = ev["periods"][0]
    assert pre["signals_traded"] == 233 and pre["beat_buying_every_alert"] is True and "n" not in pre
    assert ev["periods"][2]["beat_buying_every_alert"] is False
    assert "signals_traded" in ev["how_to_read"]


@pytest.mark.anyio
async def test_desk_signals_say_when_today_is_still_forming_like_sightings():
    """10-20: at 10 AM Sightings says 'still forming until 4:15 PM ET … to watch, not buy yet' and names the latest
    signals; the MCP only gave an empty list, which reads as 'nothing today'."""
    today = FAKE["/api/desk/today"] | {"forming": True, "signals": [],
                                       "latest": {"day": "2026-09-28", "tickers": ["AAA", "BBB"]}}
    done = FAKE["/api/desk/today"] | {"forming": False}
    async with Client(build_server((dict(FAKE) | {"/api/desk/today": today}).get), raise_exceptions=True) as c:
        d = data(await c.call_tool("desk_signals", {}))
    async with Client(build_server((dict(FAKE) | {"/api/desk/today": done}).get), raise_exceptions=True) as c:
        f = data(await c.call_tool("desk_signals", {}))
    assert d["still_forming"] is True and f["still_forming"] is False
    assert d["in_plain_words"] == ("Tue, Sep 29 is still forming: nothing is final until 4:15 PM ET, and the rule buys at "
                                   "the next open, so today's signals are to watch, not buy yet. Latest signals: Mon, "
                                   "Sep 28, AAA, BBB.")
    assert "in_plain_words" not in f


@pytest.mark.anyio
async def test_desk_evidence_has_all_windows_beta_and_plain_reading(client):
    d = data(await client.call_tool("desk_evidence", {}))
    names = [p["period"] for p in d["periods"]]
    assert names == ["Second sealed test · Oct 2023 – Sep 2024", "Practice year · Oct 2024 – Sep 2025",
                     "Sealed test · Oct 2025 – May 2026", "Recent months · Jun – Sep 2026"]
    ho = d["periods"][2]
    assert ho["signals_traded"] == 488 and ho["signals_per_day"] == 2 and ho["what_it_is"].startswith("Rules locked first")
    assert ho["risk_adjusted_signals_avg_per_trade"] == 0.0057 and ho["signals_move_vs_market"] == 2.43
    assert "signals_traded" in d["how_to_read"] and "pre_period" not in d
    assert "3 of 4 periods" in d["reading"] and "2.3x" in d["reading"] and "not proven" in d["reading"]
    assert "UW flow carries" in d["reading"] and "firehose" not in d["reading"] and "every alert" not in d["reading"]


@pytest.mark.anyio
async def test_desk_signals_separate_whale_trade_from_tested_stock_action(client):
    sig = data(await client.call_tool("desk_signals", {}))["signals"][0]
    assert sig["tested_action"] == "Buy MRVL stock at the Sep 30 open and sell at the Oct 6 close. That's what the backtest measured."
    assert sig["whale_did"]["strike"] == 110.0 and sig["whale_did"]["kind"] == "call"
    assert sig["signal_type"] in ("Whale-size bet", "Long shot, not overpriced")
    assert "strike" not in sig


@pytest.mark.anyio
async def test_desk_ticker_past_signals_in_plain_words():
    fake = dict(FAKE) | {"/api/desk/ticker/AAA": {"ticker": "AAA", "past_signals": [
        {"date": "2026-01-05", "tier": "whale", "direction": 1, "premium": 2e6, "otm_pct": 0.1, "x5": 0.02, "period": "Sealed test"}]}}
    async with Client(build_server(fake.get), raise_exceptions=True) as c:
        d = data(await c.call_tool("desk_ticker", {"ticker": "aaa"}))
    p = d["past_signals"][0]
    assert p["result_5d_vs_sp500"] == 0.02 and p["period"] == "Sealed test" and "x5" not in p
    assert "in-sample" not in d["disclaimer"]


def _keys(v):
    if isinstance(v, dict):
        for k, x in v.items():
            yield k
            yield from _keys(x)
    elif isinstance(v, list):
        for x in v:
            yield from _keys(x)


@pytest.mark.anyio
async def test_desk_tools_have_no_statistician_shorthand():
    """Owner 09-30: answers read '(n=170)' — no bare 'n' key or 'n=' text anywhere a client model could copy it."""
    fake = dict(FAKE)
    fake["/api/desk/today"] = FAKE["/api/desk/today"] | {"signals": [FAKE["/api/desk/today"]["signals"][0] | {
        "cluster": {"sector": "Technology", "n": 4}}]}
    fake["/api/desk/ticker/AAA"] = {"ticker": "AAA", "flow_daily": [{"date": "2026-09-30", "bull": 1.0, "bear": 2.0,
                                    "other": 0.0, "n": 19}], "iv_rank": [{"date": "2026-09-29", "v": 5.3}], "past_signals": []}
    async with Client(build_server(fake.get), raise_exceptions=True) as c:
        outs = [data(await c.call_tool("desk_signals", {})), data(await c.call_tool("desk_evidence", {})),
                data(await c.call_tool("desk_ticker", {"ticker": "AAA"}))]
    for d in outs:
        assert not {"n", "v", "ci_low", "ci_high"} & set(_keys(d))
        assert "n=" not in json.dumps(d)
    sig = outs[0]["signals"][0]
    assert sig["cluster"] == {"sector": "Technology", "signals_in_sector_that_day": 4}   # the signal's own day (10-20)
    unknown = FAKE["/api/desk/today"] | {"signals": [FAKE["/api/desk/today"]["signals"][0] | {
        "cluster": {"sector": "Unknown", "n": 2}}]}
    async with Client(build_server((dict(FAKE) | {"/api/desk/today": unknown}).get), raise_exceptions=True) as c:
        assert data(await c.call_tool("desk_signals", {}))["signals"][0]["cluster"] is None   # ETFs: no sector to share
    assert outs[2]["flow_daily"][0]["alerts"] == 19 and outs[2]["iv_rank_latest"] == {"date": "2026-09-29", "iv_rank": 5.3}


@pytest.mark.anyio
async def test_desk_evidence_rows_carry_a_plain_sentence(client):
    """Each period row has `in_plain_words`, ready to quote, with the trade count written out."""
    ho = data(await client.call_tool("desk_evidence", {}))["periods"][2]
    s = ho["in_plain_words"]
    assert s.startswith("Sealed test (Oct 2025 – May 2026): 488 signals traded, averaging +1.20% per trade")
    assert "all one-way UW alerts averaged −0.10%" in s
    pre = data(await client.call_tool("desk_signals", {}))["evidence"]["periods"][0]
    assert pre["in_plain_words"].startswith("Second sealed test (Oct 2023 – Sep 2024): 233 signals traded, averaging +1.70%")


@pytest.mark.anyio
async def test_desk_ticker_sums_past_signals_per_period_in_words():
    fake = dict(FAKE) | {"/api/desk/ticker/AAA": {"ticker": "AAA", "past_signals": [
        {"date": "2026-01-05", "x5": 0.02, "period": "Sealed test"},
        {"date": "2026-01-06", "x5": -0.01, "period": "Sealed test"},
        {"date": "2026-09-23", "x5": None, "period": "Recent months"}]}}
    async with Client(build_server(fake.get), raise_exceptions=True) as c:
        d = data(await c.call_tool("desk_ticker", {"ticker": "AAA"}))
    assert d["past_signals_by_period"] == [
        "Sealed test: 2 past signals on AAA, 1 beat the S&P 500 over five days, average +0.50% per trade.",
        "Recent months: 1 past signal on AAA, still inside its five-day hold (no result yet)."]


HIST = {"matches": 204, "win_share": 0.475, "avg": -0.0059, "median": -0.0038, "traits_dropped": ["sector"], "thin": False,
        "periods": [{"period": "Sealed test", "matches": 95, "win_share": 0.49, "avg": -0.0028, "median": -0.0039}],
        "periods_agree": False, "baseline": {"matches": 275187, "win_share": 0.489, "avg": -0.0008, "median": -0.001},
        "in_plain_words": "Of 204 earlier bets like this, 48% beat the S&P 500 over the 5-day hold.", "label": "History lookup"}
BET = {"id": "b1", "ticker": "NVDA", "direction": 1, "opt_type": "call", "bet_kind": "clean buy", "premium": 2.5e6,
       "strike": 200.0, "expiry": "2026-11-20", "dte": 48, "otm_pct": 0.06, "sweep": True, "sector": "Technology",
       "session_date": "2026-10-02", "verdict": "conviction", "reason": "premium under the whale bar",
       "history": {"matches": 204}}


def _lookup_fake() -> dict:
    small = BET | {"id": "b2", "premium": 3e5, "verdict": "gate", "reason": "not a buy"}
    return dict(FAKE) | {
        "/api/desk/alerts": {"day": "2026-10-02", "bets": [small, BET, BET | {"id": "b3", "ticker": "AMD"}]},
        "/api/desk/alerts/b1": {"bet": BET, "history": HIST, "label": "History lookup"},
        "/api/desk/alerts/b2": {"bet": small, "history": HIST, "label": "History lookup"},
        "/api/desk/lookup?direction=1&opt_type=call&premium=500000.0&dte=30&otm_pct=0.05&sweep=false&bet_kind=clean+buy":
            HIST}


@pytest.mark.anyio
async def test_desk_lookup_by_ticker_lists_todays_bets_biggest_first_with_history():
    async with Client(build_server(_lookup_fake().get), raise_exceptions=True) as c:
        d = data(await c.call_tool("desk_lookup", {"ticker": "nvda"}))
    assert d["flow_day"] == "2026-10-02" and [b["premium"] for b in d["bets"]] == [2.5e6, 3e5]
    b = d["bets"][0]
    assert b["side"] == "bullish" and b["is_signal"] is False and b["filter_said"] == "premium under the whale bar"
    assert b["history"]["in_plain_words"].startswith("Of 204 earlier bets like this")
    assert b["history"]["earlier_bets_matched"] == 204 and "label" in d and d["disclaimer"]


@pytest.mark.anyio
async def test_desk_lookup_by_traits_uses_fraction_otm_and_plain_side():
    async with Client(build_server(_lookup_fake().get), raise_exceptions=True) as c:
        d = data(await c.call_tool("desk_lookup", {"side": "bullish", "option_type": "call", "premium": 500000,
                                                    "days_to_expiry": 30, "otm_pct": 0.05}))
    assert d["history"]["in_plain_words"].startswith("Of 204") and d["history"]["periods"][0]["earlier_bets_matched"] == 95


CONTRACT_Q = ("/api/desk/lookup?direction=1&opt_type=call&premium=2500000.0&ticker=NVDA&strike=200.0&expiry=2026-11-20"
              "&sweep=false&bet_kind=clean+buy")
CONTRACT_HIST = HIST | {"inputs": {"ticker": "NVDA", "spot": 188.5, "spot_date": "2026-10-15", "spot_source": "close",
                                   "otm_pct": 0.061, "dte": 35, "sector": "Technology"},
                        "filter": {"signal": True, "stage": "signal", "tier": "whale", "value": "fair",
                                   "reason": "Whale-size bet bought at the ask",
                                   "record": {"tier": "whale", "trades": 412, "beat": 0.54, "avg": 0.0151}}}


@pytest.mark.anyio
async def test_desk_lookup_by_contract_gives_filter_verdict_and_sealed_test_record():
    """Owner 10-12: ticker + strike + expiry (what UW shows) → would the filter take it, why, and that signal type's
    sealed-test record — same check as All bets' form."""
    fake = dict(FAKE) | {CONTRACT_Q: CONTRACT_HIST}
    async with Client(build_server(fake.get), raise_exceptions=True) as c:
        d = data(await c.call_tool("desk_lookup", {"ticker": "nvda", "side": "bullish", "option_type": "call",
                                                    "premium": 2500000, "strike": 200, "expiry": "2026-11-20"}))
    f = d["filter_check"]
    assert f["is_signal"] is True and f["filter_said"] == "Whale-size bet bought at the ask"
    assert f["signal_type"] == "Whale-size bet"
    assert f["sealed_test_record"] == {"trades": 412, "beat_sp500_share": 0.54, "avg_vs_sp500": 0.0151,
                                       "in_plain_words": "In the sealed test (Oct 2025 to May 2026), 412 whale-size bet "
                                       "signals traded on the stock (next open, sold five days later): 54% beat the "
                                       "S&P 500, average +1.51% a trade after costs. Not proven."}
    assert d["worked_out_from"] == {"stock_price": 188.5, "price_date": "2026-10-15", "otm_pct": 0.061,
                                    "days_to_expiry": 35, "sector": "Technology"}
    assert d["history"]["earlier_bets_matched"] == 204 and d["disclaimer"]


@pytest.mark.anyio
async def test_desk_lookup_by_contract_not_a_signal_has_no_record_and_bad_input_hints():
    no = CONTRACT_HIST | {"filter": {"signal": False, "stage": "gate", "tier": None, "reason": "DTE 400 outside 7–90"}}
    async with Client(build_server((dict(FAKE) | {CONTRACT_Q: no}).get), raise_exceptions=True) as c:
        d = data(await c.call_tool("desk_lookup", {"ticker": "NVDA", "side": "bullish", "option_type": "call",
                                                    "premium": 2500000, "strike": 200, "expiry": "2026-11-20"}))
        e = data(await c.call_tool("desk_lookup", {"ticker": "NVDA", "side": "bullish", "option_type": "call",
                                                    "premium": 2500000, "strike": 200, "expiry": "2020-01-17"}))
    assert d["filter_check"] == {"is_signal": False, "filter_said": "DTE 400 outside 7–90"}
    assert "error" in e and "expiry" in e["hint"]


@pytest.mark.anyio
async def test_desk_lookup_shows_the_apis_reason_for_a_rejected_bet_not_desk_down():
    """A bad bet (expiry passed, premium under $100K…) gets the API's own message, not 'data is not available'."""
    def get(path):
        get.rejected = "That expiry date has already passed." if "expiry=2020" in path else None
        return None
    get.rejected = None
    async with Client(build_server(get), raise_exceptions=True) as c:
        e = data(await c.call_tool("desk_lookup", {"ticker": "NVDA", "side": "bullish", "option_type": "call",
                                                    "premium": 2500000, "strike": 200, "expiry": "2020-01-17"}))
        t = data(await c.call_tool("desk_lookup", {"side": "bullish", "option_type": "call", "premium": 500000,
                                                    "days_to_expiry": 30, "otm_pct": 0.05}))
    assert e["error"] == "That expiry date has already passed." and "not available" not in e["error"]
    assert "not available" in t["error"]                 # no reason given (desk really unreadable) → unchanged


def test_local_api_get_keeps_none_on_errors_and_remembers_the_rejection(monkeypatch):
    from whaleproof import mcp_server

    class R:
        def __init__(self, code, body):
            self.status_code, self._b = code, body

        def json(self):
            return self._b

    class FakeClient:
        def get(self, path):
            return R(400, {"detail": "bad expiry date"}) if "bad" in path else R(200, {"ok": 1})

    g = mcp_server._api_get(FakeClient(), lambda: None)
    assert g("/bad") is None and g.rejected == "bad expiry date"
    assert g("/good") == {"ok": 1} and g.rejected is None


@pytest.mark.anyio
async def test_desk_lookup_without_ticker_or_traits_explains_usage():
    async with Client(build_server(_lookup_fake().get), raise_exceptions=True) as c:
        d = data(await c.call_tool("desk_lookup", {}))
        e = data(await c.call_tool("desk_lookup", {"ticker": "ZZZZ"}))
    assert "error" in d and "ticker" in d["error"]
    assert e["bets"] == [] and "No UW-flagged bets on ZZZZ" in e["in_plain_words"]


def _trk(ticker, period, status, vs, ret=None, opt=None, sector="Technology", day="2026-01-05"):
    return {"id": ticker + day, "session_date": day, "ticker": ticker, "direction": 1, "tier": "whale", "period": period,
            "sector": sector, "entry_on": day, "exit_by": "2026-01-12", "contract": None,
            "stock": {"status": status, "entry_date": day if status != "waiting" else None, "entry": 10.0,
                      "days_held": 5 if status == "closed" else 1, "ret": ret if ret is not None else vs, "vs_spy": vs,
                      "last": 10.5},
            "option": opt and {"ret": opt}}


TRACKER = {"priced_through": "2026-10-02", "note": "Stock: buy the next open...", "rows": [
    *[_trk(f"P{i}", "Practice year (rules chosen here)", "closed", 0.01, opt=0.1, day=f"2025-01-{i + 10}")
      for i in range(10)],
    _trk("AAA", "Sealed test", "closed", 0.02, opt=0.5), _trk("BBB", "Sealed test", "closed", -0.01, opt=-0.6),
    _trk("CCC", "Practice year (rules chosen here)", "closed", 0.03, sector="Energy"),
    _trk("FFF", "Second sealed test (2023–24)", "closed", 0.04, sector="Health", day="2024-01-05"),
    _trk("DDD", "Live (from Sep 30)", "open", 0.015, day="2026-10-01"),
    _trk("EEE", "Live (from Sep 30)", "waiting", None, day="2026-10-02")]}


@pytest.mark.anyio
async def test_desk_tracker_summarises_periods_in_words_and_lists_open():
    fake = dict(FAKE) | {"/api/desk/tracker": TRACKER}
    async with Client(build_server(fake.get), raise_exceptions=True) as c:
        d = data(await c.call_tool("desk_tracker", {}))
        s = data(await c.call_tool("desk_tracker", {"period": "sealed"}))
        e = data(await c.call_tool("desk_tracker", {"sector": "energy"}))
    sealed = next(p for p in d["periods"] if p["period"] == "Sealed test")
    assert sealed["finished"] == 2 and sealed["beat_sp500"] == 1 and sealed["stock_avg_vs_sp500"] == 0.005
    assert sealed["in_plain_words"] == ("Sealed test: 2 finished signals, 1 beat the S&P 500 over the five-day hold, "
                                        "stock average +0.50% per trade vs the S&P 500 after costs; too few whale "
                                        "options priced to tell (2).")
    assert sealed["whale_option_avg_return"] is None and sealed["whale_options_priced"] == 2
    assert [o["ticker"] for o in d["open_now"]] == ["DDD"] and [w["ticker"] for w in d["waiting"]] == ["EEE"]
    assert d["prices_through"] == "2026-10-02" and d["disclaimer"]
    assert {p["period"] for p in s["periods"]} == {"Sealed test"}
    assert [p["finished"] for p in e["periods"]] == [1]
    practice = next(p for p in d["periods"] if p["period"].startswith("Practice"))
    assert practice["in_plain_words"].endswith("the whale's own option averaged +10.00% (10 priced).")
    for out in (d, s, e):
        assert not {"n", "ci_low", "ci_high"} & set(_keys(out)) and "n=" not in json.dumps(out)


_ST = lambda b, r=100: {"reports": r, "beat": b, "median_move_vs_implied": 0.7, "mean_edge": -0.01}  # noqa: E731
EARN_ROW = {"ticker": "AAA", "date": "2026-10-06", "time": "postmarket", "implied": 0.03, "past": 0.05, "ratio": 0.6,
            "label": "cheap", "note": None, "sector": "Technology", "marketcap": 5e9, "history_reports": 8,
            "history": [{"day": "2026-07-23", "time": "postmarket", "implied": 0.04, "actual": -0.06, "beat": True},
                        {"day": "2026-04-23", "time": "postmarket", "implied": 0.04, "actual": 0.01, "beat": False}]}
EARNINGS = {"at": "2026-10-04T19:34:34+00:00", "sessions": ["2026-10-06"], "thresholds": {}, "upcoming": [
    EARN_ROW, EARN_ROW | {"ticker": "BBB", "label": None, "ratio": None, "past": None, "note": "no past reports cached",
                          "history": [], "history_reports": 0, "reported": True}],
    "backtest": {"scored": 28048, "verdict": "supports", "all": _ST(0.3442, 28048),
                 "by_label": {"cheap": _ST(0.511), "fair": _ST(0.4118), "rich": _ST(0.2939)},
                 "by_label_year": {"cheap": {"2026": _ST(0.4026)}},
                 "cheap_minus_rich_beat": {"all": 0.2171, "range95": [0.187, 0.2471], "by_year": {}}}}


@pytest.mark.anyio
async def test_desk_earnings_lists_coming_reports_in_words_and_history_says_not_a_trade():
    fake = dict(FAKE) | {"/api/desk/earnings": EARNINGS,
                         "/api/desk/earnings/AAA": {"ticker": "AAA", "next": EARN_ROW, "history": EARN_ROW["history"],
                                                    "scored": []}}
    async with Client(build_server(fake.get), raise_exceptions=True) as c:
        names = {t.name for t in (await c.list_tools()).tools}
        d = data(await c.call_tool("desk_earnings", {}))
        t = data(await c.call_tool("desk_earnings", {"ticker": "aaa"}))
    assert "desk_earnings" in names
    a, b = d["coming"]
    assert a["in_plain_words"] == ("AAA reports Tue, Oct 6 after the close. Options price a move of about 3.0%; its "
                                   "median move on its last 8 reports was 5.0%, so the implied move looks cheap (0.60×). "
                                   "On the 2 most recent reports the move beat the implied move 1 time.")
    assert b["in_plain_words"] == "BBB reported Tue, Oct 6 after the close. Options price a move of about 3.0%; no label (no past reports cached)."
    h = d["what_history_says"]
    assert "28,048 reports" in h and "34%" in h and "cheap 51%" in h and "not proven" in h
    assert t["next"]["in_plain_words"].startswith("AAA reports Tue, Oct 6") and len(t["past_reports"]) == 2
    assert d["disclaimer"] and "n=" not in json.dumps(d) and not {"n", "ci_low", "ci_high"} & set(_keys(d))


@pytest.mark.anyio
async def test_desk_earnings_fits_an_mcp_answer_and_leads_with_the_pages_biggest_reporting():
    """10-20: 40 rows with every past report each came to 84K characters, more than an MCP app accepts. Rows keep the
    sentence (it already counts the beats), not the raw history; `biggest_coming` = the Earnings page's 'Biggest
    reporting' strip (not yet out, biggest market cap first, six)."""
    rows = [EARN_ROW | {"ticker": f"T{i:03d}", "marketcap": float(i), "history": EARN_ROW["history"] * 4,
                        "reported": i == 299} for i in range(300)]
    fake = dict(FAKE) | {"/api/desk/earnings": EARNINGS | {"upcoming": rows}}
    async with Client(build_server(fake.get), raise_exceptions=True) as c:
        d = data(await c.call_tool("desk_earnings", {}))
    assert len(json.dumps(d)) < 40_000 and d["coming_total"] == 300
    assert all("history" not in r and r["in_plain_words"] for r in d["coming"])
    assert [r["ticker"] for r in d["biggest_coming"]] == ["T298", "T297", "T296", "T295", "T294", "T293"]


@pytest.mark.anyio
async def test_desk_tracker_open_holds_use_the_live_mark_sightings_shows():
    """Open holds = API's `stock.now` / `hold_day` / `option.now` (same numbers as Sightings), not the last daily bar."""
    live = _trk("IREN", "Live (from Sep 30)", "open", 0.04, day="2026-10-06")
    live["stock"] |= {"entry": 36.0, "last": 38.70, "move": 0.075, "days_held": 1,
                      "now": {"entry": 36.0, "price": 37.07, "source": "live", "at": "2026-10-09T15:00:00+00:00",
                              "move": 0.0297, "net": 0.0287}}
    live |= {"hold_day": 2, "contract": "IREN261120C00040000",
             "option": {"contract": "IREN261120C00040000", "buy": 2.0, "sell": 2.6, "ret": 0.3,
                        "sell_date": "2026-10-08", "now": {"bid": 2.2, "at": "2026-10-09T15:00:00+00:00", "ret": 0.1}}}
    stale = _trk("JJJ", "Live (from Sep 30)", "open", 0.01, day="2026-10-06")   # API without live fields (older)
    fake = dict(FAKE) | {"/api/desk/tracker": {"priced_through": "2026-10-08", "rows": [live, stale]}}
    async with Client(build_server(fake.get), raise_exceptions=True) as c:
        d = data(await c.call_tool("desk_tracker", {}))
    o = {x["ticker"]: x for x in d["open_now"]}
    i = o["IREN"]
    assert i["price_now"] == 37.07 and i["price_source"] == "live" and i["day_of_hold"] == 2
    assert i["price_move_so_far"] == 0.0297 and i["net_after_costs_so_far"] == 0.0287
    assert i["whale_option"]["return_so_far"] == 0.1 and i["whale_option"]["price_source"] == "live"
    assert "days_held" not in i and "last" not in i
    # daily bars include today's unfinished one while the market is open: "so far", not "at last close" (10-20)
    assert "vs_sp500_so_far" in i and "vs_sp500_at_last_close" not in i
    j = o["JJJ"]
    assert j["price_now"] == 10.5 and j["price_source"] == "last close" and j["day_of_hold"] == 1
    assert j["whale_option"] is None


def test_period_sentence_says_one_signal_traded():
    from whaleproof.mcp_server import _plain_period
    assert _plain_period("Live · since Sep 30", 0.01, -0.001, 1).startswith("Live (since Sep 30): 1 signal traded,")


def test_period_sentence_says_range_includes_zero_once_without_not_proven():
    # owner 10-23 tone pass: "not proven" is said once, in the evidence reading, not on every period
    from whaleproof.mcp_server import _plain_period
    s = _plain_period("Sealed test · Oct 2025 – May 2026", 0.0143, -0.0003, 628, -0.0006, 0.0241)
    assert s.endswith("— range includes zero.") and "not proven" not in s


def test_mcp_percents_use_a_true_minus_and_no_minus_zero():
    from whaleproof.mcp_server import _pct
    assert _pct(-0.005) == "−0.50%" and _pct(0.005) == "+0.50%" and _pct(-0.00001) == "0.00%" and _pct(None) == "n/a"
