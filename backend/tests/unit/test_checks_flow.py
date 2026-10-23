from datetime import datetime, timezone

from whaleproof.core.checks.flow import chase_guard, flow_quality, liquidity, persistence
from whaleproof.core.data_layer.context import AlertContext

AS_OF = datetime(2026, 9, 25, 20, 15, tzinfo=timezone.utc)


def ctx(alert, **over):
    base = dict(alert=alert, as_of=AS_OF, gex=None, dp_levels=None, iv_rank=None, unusual_pct=None,
                tide=None, earnings=[], same_dir_recent=0, ref_price=None)
    base.update(over)
    return AlertContext(**base)


def test_strong_flow_scores_high(make_alert):
    r = flow_quality(ctx(make_alert(total_premium="2000000", total_ask_side_prem="1900000",
                                    total_bid_side_prem="100000")))
    assert r.score > 0.7 and not r.hard_fail and "ask" in r.reason


def test_weak_flow_scores_low(make_alert):
    r = flow_quality(ctx(make_alert(total_premium="100000", total_ask_side_prem="72000",
                                    total_bid_side_prem="28000", all_opening_trades=False,
                                    volume_oi_ratio="0.2", total_size=10, open_interest=5000, volume=100,
                                    expiry="2026-09-26", has_sweep=False)))
    assert r.score < 0


def test_ambiguous_direction_hard_fails(make_alert):
    r = flow_quality(ctx(make_alert(has_multileg=True)))
    assert r.hard_fail and r.score == 0


def test_persistence_scales_and_caps(make_alert):
    a = make_alert()
    assert persistence(ctx(a, same_dir_recent=0)).score == 0
    assert round(persistence(ctx(a, same_dir_recent=1)).score, 3) == 0.333
    assert persistence(ctx(a, same_dir_recent=9)).score == 1


def test_liquidity_gate(make_alert):
    assert liquidity(ctx(make_alert(open_interest=100, volume=200))).hard_fail
    assert not liquidity(ctx(make_alert(open_interest=100, volume=800))).hard_fail


def test_chase_guard(make_alert):
    a = make_alert(underlying_price="100", iv="0.5", expiry="2026-10-16")  # EM ≈ 12
    assert not chase_guard(ctx(a)).available
    assert chase_guard(ctx(a, ref_price=113.5)).hard_fail          # ran > 1 EM in trade direction
    ok = chase_guard(ctx(a, ref_price=103))
    assert not ok.hard_fail and ok.score < 0
    better = chase_guard(ctx(a, ref_price=97))                     # cheaper entry than whale
    assert better.score > 0
