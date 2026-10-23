"""Simple-rules backtest: every gate-passing alert (no top-40 cut, no 5/day cap), outcome from prices only."""
from datetime import date, timedelta

from tests.conftest import raw_alert
from whaleproof.core.backtest.simple import missing_price_tickers, run_simple_backtest
from whaleproof.core.data_layer.models import Bar, alert_to_row, parse_alert

D0 = date(2026, 9, 22)


def put_alert(store, **over):
    r = raw_alert(**over)
    store.upsert_alerts([alert_to_row(parse_alert(r), r)])


def bars(store, tkr, drift):
    store.put_ohlc(tkr, [Bar(D0 + timedelta(days=k), 100 + drift * k, 101 + drift * k, 99 + drift * k,
                             100 + drift * k, 1) for k in range(40)])


def seed(store):
    # 41 clean buys on different tickers → proves there is no top-40 cut
    for i in range(41):
        put_alert(store, id=f"c{i}", ticker=f"T{i}", created_at="2026-09-22T15:00:00Z", underlying_price="100",
                  strike="105", expiry="2026-10-16", option_chain=f"T{i}261016C00105000")
        bars(store, f"T{i}", 1.0)
    put_alert(store, id="sold", ticker="S", created_at="2026-09-22T15:00:00Z", underlying_price="100", strike="105",
              expiry="2026-10-16", total_ask_side_prem="50000", total_bid_side_prem="450000",
              option_chain="S261016C00105000")                     # sold call → noise
    bars(store, "S", -1.0)
    put_alert(store, id="late", ticker="L", created_at="2026-09-22T21:00:00Z", underlying_price="100",
              strike="105", expiry="2026-10-16", option_chain="L261016C00105000")   # after as_of → excluded
    bars(store, "L", 1.0)
    put_alert(store, id="noprice", ticker="NP", created_at="2026-09-22T15:00:00Z", underlying_price="100",
              strike="105", expiry="2026-10-16", option_chain="NP261016C00105000")
    bars(store, "SPY", 0.0)


def test_all_gate_passers_counted_no_cap(store):
    seed(store)
    rows, skipped = run_simple_backtest(store, D0, D0)
    pure = [r for r in rows if r.setup]
    assert len(pure) == 41 and all(r.label == "PURE" for r in pure)
    assert all(r.r5 > 0 and r.x5 is not None for r in pure)
    noise = [r for r in rows if not r.setup]
    assert [r.ticker for r in noise] == ["S"] and "not a buy" in noise[0].gate_fail
    assert "L" not in {r.ticker for r in rows} and skipped == 1            # NP has no prices


def test_dedupes_ticker_direction_keeps_biggest(store):
    seed(store)
    put_alert(store, id="big", ticker="T0", created_at="2026-09-22T16:00:00Z", underlying_price="100",
              strike="105", expiry="2026-10-16", total_premium="3000000", total_ask_side_prem="2900000",
              total_bid_side_prem="100000", option_chain="T0261016C00105000")
    rows, _ = run_simple_backtest(store, D0, D0)
    t0 = [r for r in rows if r.ticker == "T0"]
    assert len(t0) == 1 and t0[0].alert_id == "big" and t0[0].setup == "whale_sweep"


def test_missing_price_tickers_lists_gate_passers_without_bars(store):
    seed(store)
    assert missing_price_tickers(store, D0, D0) == ["NP"]


class PriceFake:
    def __init__(self):
        self.calls = []

    def get(self, path, params=None):
        self.calls.append(path)
        if path.endswith("/ohlc/1d"):
            return {"data": [{"date": (D0 + timedelta(days=k)).isoformat(), "open": 10, "high": 11, "low": 9,
                              "close": 10 + k, "volume": 1, "market_time": "r"} for k in range(30)]}
        return {"data": [{"report_date": "2026-10-20"}]}


def test_fill_prices_fetches_only_missing_two_calls_each(store):
    from whaleproof.commands.backfill import fill_prices
    seed(store)
    f = PriceFake()
    res = fill_prices(f, store, D0, D0, D0)
    assert res == {"tickers": 1, "done": 1, "stopped_reason": ""}
    assert f.calls == ["/api/stock/NP/ohlc/1d", "/api/earnings/NP"]
    assert store.get_ohlc("NP", D0, D0) and store.get_metric("NP", "all", "earnings") == ["2026-10-20"]
    fill_prices(f, store, D0, D0, D0)
    assert len(f.calls) == 2                                                # nothing missing any more


def test_fill_prices_respects_stop(store):
    from whaleproof.commands.backfill import fill_prices
    seed(store)
    f = PriceFake()
    assert fill_prices(f, store, D0, D0, D0, stop_at=lambda: True)["stopped_reason"] == "budget"
    assert f.calls == []


def test_fill_prices_marks_done_and_skips_rescan(store, monkeypatch):
    from whaleproof.commands import backfill as bf
    seed(store)
    f = PriceFake()
    bf.fill_prices(f, store, D0, D0, D0)
    assert store.get_checkpoint("prices_done") == D0.isoformat()
    monkeypatch.setattr("whaleproof.core.backtest.simple.missing_price_tickers",
                        lambda *a: (_ for _ in ()).throw(AssertionError("rescanned")))
    assert bf.fill_prices(f, store, D0, D0, D0)["stopped_reason"] == "already done"


def test_history_then_prices_runs_prices_only_when_history_complete(store, monkeypatch):
    from whaleproof.commands import backfill as bf
    ran = []
    monkeypatch.setattr(bf, "backfill", lambda *a, **k: ran.append("history") or {"stopped_reason": ""})
    monkeypatch.setattr(bf, "fill_prices", lambda *a, **k: ran.append("prices") or {"stopped_reason": ""})
    monkeypatch.setattr(bf, "enrich", lambda *a, **k: ran.append("enrich") or {"stopped_reason": ""})
    monkeypatch.setattr(bf, "backfill_complete", lambda *a, **k: False)
    bf.history_then_prices(None, store, D0, D0, D0, lambda: False)
    assert ran == ["history"]
    monkeypatch.setattr(bf, "backfill_complete", lambda *a, **k: True)
    ran.clear()
    bf.history_then_prices(None, store, D0, D0, D0, lambda: False)
    assert ran == ["history", "enrich", "prices"]
    monkeypatch.setattr(bf, "enrich", lambda *a, **k: ran.append("enrich") or {"stopped_reason": "budget"})
    ran.clear()
    bf.history_then_prices(None, store, D0, D0, D0, lambda: False)
    assert ran == ["history", "enrich"]                   # out of budget → prices wait for the next run


def test_put_sale_rows_reported_separately(store):
    from whaleproof.core.backtest.runner import summarize
    seed(store)
    put_alert(store, id="ps", ticker="PS", created_at="2026-09-22T15:00:00Z", type="put", underlying_price="100",
              strike="95", expiry="2026-10-16", total_ask_side_prem="20000", total_bid_side_prem="480000",
              option_chain="PS261016P00095000")
    bars(store, "PS", 1.0)
    rows, _ = run_simple_backtest(store, D0, D0)
    ps = next(r for r in rows if r.ticker == "PS")
    assert ps.setup == "put_sale" and ps.label == "PUT_SALE" and ps.direction == 1
    s = summarize(rows, 0)
    assert s["by_setup"]["put_sale"]["n"] == 1 and s["by_setup"]["pure_all"]["n"] == 41
    assert s["by_setup"]["noise"]["n"] == 1                                   # the sold call only
    assert all(r.ticker != "PS" for r in rows if r.setup is None)             # not counted as noise either


def test_rows_carry_combination_blocks(store):
    """Amendment 11 building blocks: next-morning OI ratio, OTM %, market trend, cheap/rich view."""
    seed(store)
    store.put_metric("T0261016C00105000", D0, "oi", 1000)
    store.put_metric("T0261016C00105000", date(2026, 9, 23), "oi", 2800)     # +1800 on a 2000 size → 0.9
    store.put_metric("T0", "all", "vol_hist", [["2026-09-21", 0.5, 0.60, "2026-09-21"]])
    rows, _ = run_simple_backtest(store, D0, D0)
    t0 = next(r for r in rows if r.ticker == "T0")
    assert t0.oi_ratio == 0.9 and round(t0.otm_pct, 2) == 0.05
    assert t0.value == "cheap"                                                # IV 45% vs realized 60%
    t1 = next(r for r in rows if r.ticker == "T1")
    assert t1.oi_ratio is None and t1.value in (None, "unknown")
    assert t0.spy_trend is None                                              # < 50 SPY bars → unknown


def test_rows_carry_real_option_return_when_contract_history_is_cached(store):
    """Descriptive: the whale's own contract bought at the next open, sold at the 5th session's closing bid."""
    from whaleproof.core.data_layer.fetch import cache_key
    seed(store)
    path = "/api/option-contract/T0261016C00105000/historic"
    store.cache_put(cache_key(path, {"limit": 500}), path, {"chains": [
        {"date": "2026-09-23", "open_price": "2.00", "nbbo_bid": "1.90", "nbbo_ask": "2.10"},
        {"date": "2026-09-29", "last_price": "3.10", "nbbo_bid": "3.00", "nbbo_ask": "3.20"}]})
    rows, _ = run_simple_backtest(store, D0, D0)
    t0 = next(r for r in rows if r.ticker == "T0")
    assert round(t0.opt_r5, 4) == round(3.0 / 2.1 - 1, 4) and round(t0.opt_spread, 2) == 0.1
    assert next(r for r in rows if r.ticker == "T1").opt_r5 is None                 # not cached → not measured
