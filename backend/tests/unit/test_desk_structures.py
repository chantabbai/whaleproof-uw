"""Option structures on a bullish signal, 5-session hold, Black-Scholes with real IV, per-leg bid/ask costs."""
from datetime import date

from whaleproof.desk.structures import Leg, evaluate, structures_for

E, X, EXP = date(2026, 1, 5), date(2026, 1, 9), date(2026, 2, 20)


def test_short_put_earns_when_stock_flat_and_loses_on_crash():
    legs = structures_for(100.0, 110.0)["short_put"]
    flat = evaluate(legs, 100.0, 100.0, E, X, EXP, 0.4, 0.4)
    crash = evaluate(legs, 100.0, 80.0, E, X, EXP, 0.4, 0.4)
    assert flat["ret"] > 0 > crash["ret"] and flat["basis"] == "collateral"


def test_call_spread_gain_capped_by_width():
    legs = structures_for(100.0, 110.0)["call_spread"]
    moon = evaluate(legs, 100.0, 200.0, E, X, date(2026, 1, 9), 0.4, 0.4)   # expires at exit → intrinsic
    width = legs[1].strike - legs[0].strike
    assert moon["ret"] <= width / moon["risk"] - 1 + 1e-9


def test_long_call_matches_structure_of_whale_strike():
    legs = structures_for(100.0, 110.0)["long_call"]
    assert legs == [Leg("C", 110.0, +1)]


def test_put_spread_loss_limited_to_max_risk():
    legs = structures_for(100.0, 110.0)["put_spread"]
    r = evaluate(legs, 100.0, 10.0, E, X, date(2026, 1, 9), 0.4, 0.4)
    assert r["pnl"] >= -r["risk"] - r["cost"] - 1e-9     # max loss = width − credit, plus trading costs


def test_real_prices_short_put_uses_conservative_fills():
    from whaleproof.desk.structures import evaluate_real
    hist = {"P95": {"2026-01-05": {"open_price": "2.00", "nbbo_bid": "1.90", "nbbo_ask": "2.10"},
                    "2026-01-09": {"nbbo_bid": "0.90", "nbbo_ask": "1.00"}}}
    r = evaluate_real([Leg("P", 95.0, -1)], ["P95"], hist.get, E, X)
    assert abs(r["pnl"] - (1.90 - 1.00)) < 1e-9 and r["basis"] == "collateral"   # sold 2.00−0.10, bought back at the ask
    assert evaluate_real([Leg("P", 95.0, -1)], ["MISSING"], hist.get, E, X) is None
