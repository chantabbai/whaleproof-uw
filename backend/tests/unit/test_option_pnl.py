"""Plan 2b task 2: Black-Scholes option P&L estimate at the plan's target / stop (model estimate, IV held flat)."""
import math
from datetime import date

import pytest

from whaleproof.core.options import pnl


def test_parse_occ_symbol():
    c = pnl.parse_contract("PLTR261016P00190000")
    assert c == {"ticker": "PLTR", "expiry": date(2026, 10, 16), "kind": "P", "strike": 190.0}
    assert pnl.parse_contract("BRKB261218C00512500")["strike"] == 512.5
    assert pnl.parse_contract("junk") is None


def test_black_scholes_textbook_value_and_parity():
    # Hull: S=42, K=40, r=10%, σ=20%, T=0.5 → call 4.76, put 0.81
    assert pnl.bs_price("C", 42, 40, 0.5, 0.2, r=0.10) == pytest.approx(4.76, abs=0.01)
    assert pnl.bs_price("P", 42, 40, 0.5, 0.2, r=0.10) == pytest.approx(0.81, abs=0.01)
    c, p = pnl.bs_price("C", 100, 105, 0.3, 0.4), pnl.bs_price("P", 100, 105, 0.3, 0.4)
    assert c - p == pytest.approx(100 - 105 * math.exp(-pnl.RATE * 0.3), abs=1e-9)


def test_expiry_is_intrinsic_and_price_monotone_in_spot():
    assert pnl.bs_price("C", 110, 100, 0, 0.5) == 10 and pnl.bs_price("P", 110, 100, 0, 0.5) == 0
    vals = [pnl.bs_price("C", s, 100, 0.2, 0.3) for s in (90, 95, 100, 105, 110)]
    assert vals == sorted(vals)


def test_estimate_long_call_at_target_and_stop():
    e = pnl.estimate("NVDA261016C00200000", spot=195, target=210, stop=188, iv=0.5,
                     entry=date(2026, 9, 28), exit_sessions=5)
    assert e["structure"] == "long call" and e["entry_premium"] > 0
    assert e["ret_target"] > 0 > e["ret_stop"] >= -1
    assert e["breakeven"] == pytest.approx(200 + e["entry_premium"])
    assert e["ret_target_iv_down"] < e["ret_target"] < e["ret_target_iv_up"]      # ±5 vol points


def test_estimate_debit_spread_caps_the_gain():
    kw = dict(spot=195, target=230, stop=188, iv=0.5, entry=date(2026, 9, 28), exit_sessions=5)
    single = pnl.estimate("NVDA261016C00200000", **kw)
    spread = pnl.estimate("NVDA261016C00200000", spread_width=10, **kw)
    assert spread["structure"] == "call debit spread" and spread["entry_premium"] < single["entry_premium"]
    assert spread["value_target"] <= 10 + 1e-9


def test_estimate_put_and_bad_input():
    e = pnl.estimate("PLTR261016P00190000", spot=192, target=180, stop=198, iv=0.6,
                     entry=date(2026, 9, 28), exit_sessions=5)
    assert e["ret_target"] > 0 > e["ret_stop"] and e["breakeven"] == pytest.approx(190 - e["entry_premium"])
    assert pnl.estimate("junk", spot=1, target=2, stop=0.5, iv=0.3, entry=date(2026, 9, 28), exit_sessions=5) is None
    assert pnl.estimate("PLTR261016P00190000", spot=192, target=180, stop=198, iv=None,
                        entry=date(2026, 9, 28), exit_sessions=5) is None


def test_readable_contract():
    from whaleproof.core.options.pnl import readable
    assert readable("SPY261120C00765000") == "SPY $765 Call · Nov 20 '26"
    assert readable("KWEB261120P00024500") == "KWEB $24.50 Put · Nov 20 '26"
    assert readable("BRK.B270115C00500000") == "BRK.B $500 Call · Jan 15 '27"
    assert readable("MU261113C01030000") == "MU $1,030 Call · Nov 13 '26"      # thousands comma, like the app
    assert readable("not a contract") == "not a contract"
