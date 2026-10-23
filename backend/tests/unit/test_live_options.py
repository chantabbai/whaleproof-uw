"""Live option tracking: snap our contract to a strike that is really listed; the after-open "still worth buying?"
check; parsing UW's per-expiry chain and stock state."""
from whaleproof.core.options import live


def q(sym, bid, ask):
    return {"option_symbol": sym, "nbbo_bid": str(bid), "nbbo_ask": str(ask), "last_price": str((bid + ask) / 2),
            "implied_volatility": "0.3", "delta": 0.5, "volume": 10, "open_interest": 100}


def test_parse_chain_and_state():
    chain = live.parse_chain({"data": [q("KWEB261120C00024000", 1.2, 1.3), {"option_symbol": None}]})
    assert chain["KWEB261120C00024000"]["ask"] == 1.3 and len(chain) == 1
    st = live.parse_state({"data": {"close": "24.5", "open": "24.44", "prev_close": "24.66", "market_time": "r"}})
    assert st == {"last": 24.5, "open": 24.44, "prev_close": 24.66, "market_time": "r"}


def test_parse_state_unknown_ticker_is_empty_not_a_crash():
    """10-22 fresh-install test: UW answers {"data": null} for a ticker it doesn't know (a typo on a ticker page). The
    AttributeError got past live.safe and aborted every refresh pass while that page counted as viewed (10 min)."""
    assert live.parse_state({"data": None}) == {"last": None, "open": None, "prev_close": None, "market_time": None}


def test_snap_to_nearest_listed_strike_same_expiry_and_type():
    chain = {s: {"open_interest": 500} for s in ["KWEB261120C00024000", "KWEB261120C00025000", "KWEB261120P00024500"]}
    assert live.snap_listed("KWEB261120C00024500", chain) == "KWEB261120C00024000"    # tie → lower for calls
    assert live.snap_listed("KWEB261120C00024000", chain) == "KWEB261120C00024000"
    assert live.snap_listed("KWEB261218C00024000", chain) is None                     # other expiry not in chain


def test_snap_skips_dead_strikes_amendment_17():
    chain = {"GKOS261120C00100000": {"open_interest": 0}, "GKOS261120C00105000": {"open_interest": "250"},
             "GKOS261120C00095000": {"open_interest": 99}, "GKOS261120C00090000": {}}
    assert live.snap_listed("GKOS261120C00100000", chain, spot=100) == "GKOS261120C00105000"   # nearest with OI ≥ 100
    chain["GKOS261120C00095000"]["open_interest"] = 100
    assert live.snap_listed("GKOS261120C00100000", chain, spot=100) == "GKOS261120C00095000"   # tie → lower for calls
    far = {"GKOS261120C00100000": {"open_interest": 3}, "GKOS261120C00115000": {"open_interest": 9000}}
    assert live.snap_listed("GKOS261120C00100000", far, spot=100) is None                   # > 10% from the stock
    dead = {"GKOS261120C00100000": {"open_interest": None}, "GKOS261120C00101000": {"open_interest": "x"}}
    assert live.snap_listed("GKOS261120C00100000", dead, spot=100) is None                  # missing/bad OI = 0


def test_no_liquid_strike_is_a_skip():
    plan = {"entry_ref": 100.0, "target": 110.0, "invalidation": 95.0}
    chk = live.after_open_check(1, plan, 100.5, 2.0, None, bid_now=None, quote_given=True, contract_found=False)
    assert chk["decision"] == "skip: no liquid strike"


def test_after_open_check():
    plan = {"entry_ref": 100.0, "target": 110.0, "invalidation": 95.0}
    ok = live.after_open_check(1, plan, stock_now=101.0, est_premium=2.0, ask_now=2.1)
    assert ok["decision"] == "still a buy" and round(ok["progress"], 2) == 0.1
    assert live.after_open_check(1, plan, 106.0, 2.0, 3.0)["decision"] == "already moved"      # 60% of the way
    assert live.after_open_check(1, plan, 94.0, 2.0, 1.0)["decision"] == "skip: past the stop"
    ran = live.after_open_check(1, plan, 101.0, 2.0, 2.6)                                     # +30% vs estimate
    assert ran["decision"] == "skip: price ran" and round(ran["price_change"], 2) == 0.3
    short = {"entry_ref": 100.0, "target": 90.0, "invalidation": 105.0}
    assert live.after_open_check(-1, short, 94.0, 2.0, 2.0)["decision"] == "already moved"
    assert live.after_open_check(1, plan, None, 2.0, None)["decision"] == "no live price"


def test_after_open_check_wide_spread_amendment_14():
    plan = {"entry_ref": 100.0, "target": 110.0, "invalidation": 95.0}
    wide = live.after_open_check(1, plan, 101.0, 2.0, 2.1, bid_now=1.85)                   # 0.25 / 1.975 = 12.7%
    assert wide["decision"] == "skip: wide spread" and round(wide["spread"], 3) == 0.127
    assert "12.7%" not in wide["reason"] and "13%" in wide["reason"]
    assert live.after_open_check(1, plan, 101.0, 2.0, 2.1, bid_now=2.0)["decision"] == "still a buy"   # 4.9%
    nq = live.after_open_check(1, plan, 101.0, 2.0, None, bid_now=None, quote_given=True)   # untraded today: no quote
    assert nq["decision"] == "still a buy" and "no quote at 9:45" in nq["reason"]           # Amendment 14a
    assert live.after_open_check(1, plan, 101.0, 2.0, 2.6, bid_now=1.0)["decision"] == "skip: price ran"  # order
