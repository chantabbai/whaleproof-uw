"""Signal Desk conviction filter: one classifier for history and live."""
from datetime import UTC, date, datetime

from tests.conftest import raw_alert
from whaleproof.core.data_layer.models import parse_alert
from whaleproof.desk.signals import Context, classify

AS_OF = datetime(2026, 9, 25, 20, 15, tzinfo=UTC)


def alert(**over):
    base = dict(underlying_price="100", strike="110", expiry="2026-11-20", total_premium="1500000",
                total_ask_side_prem="1450000", total_bid_side_prem="50000", all_opening_trades=True,
                has_multileg=False, has_sweep=True)
    base.update(over)
    return parse_alert(raw_alert(**base))


def ctx(**over):
    base = dict(same_day=[], earnings=[], value="fair", value_reason="IV 40% vs realized 38%", repeat=0)
    base.update(over)
    return Context(**base)


def test_whale_long_passes_with_reasons():
    r = classify(alert(), ctx(), AS_OF)
    assert r.passed and r.tier == "whale"
    text = " ".join(r.why)
    assert "$1.5M" in text and "ask" in text and "10% out of the money" in text and "sweep" in text.lower()


def test_far_otm_fair_passes_small_premium():
    r = classify(alert(strike="120", total_premium="300000", total_ask_side_prem="290000",
                       total_bid_side_prem="10000"), ctx(), AS_OF)
    assert r.passed and r.tier == "far_otm"


def test_far_otm_rich_rejected():
    r = classify(alert(strike="120", total_premium="300000", total_ask_side_prem="290000",
                       total_bid_side_prem="10000"), ctx(value="rich"), AS_OF)
    assert not r.passed and "rich" in r.reason


def test_small_near_money_buy_is_below_bar():
    r = classify(alert(strike="103", total_premium="300000", total_ask_side_prem="290000",
                       total_bid_side_prem="10000"), ctx(), AS_OF)
    assert not r.passed and r.stage == "conviction"


def test_gate_failure_is_first_reason():
    r = classify(alert(total_ask_side_prem="100000", total_bid_side_prem="1400000"), ctx(), AS_OF)
    assert not r.passed and r.stage == "gate" and "not a buy" in r.reason


def test_put_buy_rejected_as_bearish():
    r = classify(alert(type="put", strike="90", option_chain="NVDA261120P00090000"), ctx(), AS_OF)
    assert not r.passed and "bearish" in r.reason


def test_earnings_before_exit_rejected_premarket_next_day_counts():
    # flow Fri 09-25 → entry Mon 09-28 open; a Mon PREMARKET report happens before our entry → still blocked
    r = classify(alert(), ctx(earnings=[(date(2026, 9, 28), "premarket")]), AS_OF)
    assert not r.passed and "earnings" in r.reason
    later = classify(alert(), ctx(earnings=[(date(2026, 10, 20), "postmarket")]), AS_OF)
    assert later.passed


def test_penny_stock_rejected():
    r = classify(alert(underlying_price="4", strike="4.4"), ctx(), AS_OF)
    assert not r.passed and r.stage == "liquidity"


def test_why_does_not_claim_no_earnings_without_data():
    r = classify(alert(), ctx(earnings=[]), AS_OF)
    assert any("not available" in w for w in r.why) and not any(w.startswith("No earnings") for w in r.why)
    r2 = classify(alert(), ctx(earnings=[(date(2026, 12, 1), "postmarket")]), AS_OF)
    assert any(w.startswith("No earnings before") for w in r2.why)


def test_money_rounds_like_the_ui_and_never_says_1000k():
    from whaleproof.desk.signals import _money
    assert _money(878_500) == "$879K"          # All bets row said $879K, its reason $878K (Python rounds half to even)
    assert _money(1_250_000) == "$1.3M"
    assert _money(999_600) == "$1.0M"          # not "$1000K"
    assert _money(125_000) == "$125K"
