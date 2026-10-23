"""Our own contract (not the whale's), trading cost from the bid/ask spread, and Greeks on the estimate."""
from datetime import date

import pytest

from whaleproof.core.options import contract as oc
from whaleproof.core.options.pnl import estimate, parse_contract


def test_third_friday():
    assert oc.third_friday(2026, 10) == date(2026, 10, 16)
    assert oc.third_friday(2026, 11) == date(2026, 11, 20)


def test_expiry_leaves_room_after_the_hold():
    # monthly expiry at least max(21 days, 2.5 × the hold in calendar days) after entry
    assert oc.pick_expiry(date(2026, 9, 29), 10) == date(2026, 11, 20)     # 2.5 × 14 = 35 d → Nov 3 → Nov 20
    assert oc.pick_expiry(date(2026, 9, 29), 1) == date(2026, 11, 20)      # 21 d → Oct 20 → next monthly Nov 20
    assert oc.pick_expiry(date(2026, 9, 29), 30) == date(2027, 1, 15)      # 2.5 × 42 = 105 d → Jan 12 → Jan 15


def test_strike_near_the_money_on_a_sane_grid():
    assert oc.strike_step(24.66) == 0.5 and oc.round_strike(24.66, 1) == 24.5
    assert oc.strike_step(736.5) == 5 and oc.round_strike(736.5, 1) == 735.0
    assert oc.strike_step(186.2) == 2.5 and oc.round_strike(186.2, -1) == 185.0
    assert oc.round_strike(186.25, 1) == 185.0 and oc.round_strike(186.25, -1) == 187.5   # tie → slightly ITM


def test_choose_contract_builds_occ_symbol_for_our_direction():
    sym = oc.choose_contract("QQQ", 1, 736.53, date(2026, 9, 29), 1)
    c = parse_contract(sym)
    assert c["kind"] == "C" and c["strike"] == 735.0 and c["expiry"] == date(2026, 11, 20)
    put = parse_contract(oc.choose_contract("PLTR", -1, 186.2, date(2026, 9, 29), 10))
    assert put["kind"] == "P" and put["expiry"] == date(2026, 11, 20)


def test_spread_cost_is_bigger_for_cheap_options():
    assert oc.spread_cost(0.30) > oc.spread_cost(2.0) > oc.spread_cost(20.0)


def test_estimate_adds_greeks_costs_and_option_reward_risk():
    e = estimate("KWEB261120C00025000", spot=24.66, target=26.0, stop=23.53, iv=0.4,
                 entry=date(2026, 9, 29), exit_sessions=10)
    assert 0.3 < e["delta"] < 0.7 and e["theta_day"] < 0
    assert e["cost_pct"] == pytest.approx(oc.spread_cost(e["entry_premium"]))
    assert e["ret_target_net"] < e["ret_target"] and e["ret_stop_net"] < e["ret_stop"]
    assert e["option_rr"] == pytest.approx(e["ret_target_net"] / abs(e["ret_stop_net"]))


def test_option_mark_turns_a_stock_move_into_an_option_result():
    from whaleproof.core.options.pnl import mark
    sym, d0 = "MSFT261120C00520000", date(2026, 9, 28)
    flat = mark(sym, 0.3, d0, 520.0, 520.0, d0)
    assert -0.2 < flat < 0                                                     # only the bid/ask spread
    up = mark(sym, 0.3, d0, 520.0, 530.0, date(2026, 10, 2))
    decay = mark(sym, 0.3, d0, 520.0, 520.0, date(2026, 10, 16))
    assert up > 0 > flat > decay > -1                                          # time decay costs while flat
    assert mark("junk", 0.3, d0, 1, 1, d0) is None
