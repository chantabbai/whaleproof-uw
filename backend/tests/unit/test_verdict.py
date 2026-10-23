import json
from datetime import datetime, timezone

from whaleproof.core.data_layer.context import AlertContext
from whaleproof.core.data_layer.models import GexLevels
from whaleproof.core.verdict.candidates import prefilter
from whaleproof.core.verdict.verdict import evaluate
from whaleproof.core.verdict.weights import V0, Weights, load_weights, save_weights

AS_OF = datetime(2026, 9, 25, 20, 15, tzinfo=timezone.utc)


def ctx(alert, **over):
    base = dict(alert=alert, as_of=AS_OF, gex=None, dp_levels=None, iv_rank=None, unusual_pct=None,
                tide=None, earnings=[], same_dir_recent=0, ref_price=None)
    base.update(over)
    return AlertContext(**base)


def strong(make_alert):
    return make_alert(total_premium="2000000", total_ask_side_prem="1950000", total_bid_side_prem="50000",
                      underlying_price="100", strike="105", iv="0.5", expiry="2026-10-16")


def full(alert):
    return ctx(alert, gex=GexLevels(125, 90, 95, 100), dp_levels=[(98.0, 9000)], iv_rank=15,
               unusual_pct=95, tide=6e8, same_dir_recent=3, ref_price=100.5)


def test_strong_confluence_is_go_with_plan(make_alert):
    v = evaluate(full(strong(make_alert)))
    assert v.label == "GO" and v.score >= 70 and v.weights_version == "v0"
    assert v.plan.direction == "bullish" and v.plan.invalidation == 95  # flip is 0.55× hold-EM below
    assert v.plan.target == 113.01  # call wall 125 is >2× hold-EM away → fallback spot + 1.25×EM
    assert v.plan.time_stop_sessions == 10 and v.plan.structure == "long call"
    assert len(v.reasons_for) <= 3 and len(v.reasons_against) <= 2
    assert v.score_parity != v.score  # unusualness is live-only
    json.dumps(v.to_dict())  # serializable


def test_hard_fail_forces_skip(make_alert):
    a = make_alert(total_premium="2000000", total_ask_side_prem="1950000", total_bid_side_prem="50000",
                   open_interest=10, volume=20)
    assert evaluate(full(a)).label == "SKIP"


def test_low_coverage_caps_at_watch(make_alert):
    v = evaluate(ctx(strong(make_alert), same_dir_recent=3))  # only flow + persistence + catalyst
    assert v.coverage < 0.5 and v.label in ("WATCH", "SKIP")


def test_rich_iv_suggests_spread(make_alert):
    c = full(strong(make_alert))
    c = AlertContext(**{**c.__dict__, "iv_rank": 85})
    assert evaluate(c).plan.structure == "call debit spread"


def test_prefilter_dedupes_and_filters(make_alert):
    a1 = make_alert(id="1", total_premium="300000", total_ask_side_prem="290000", total_bid_side_prem="0")
    a2 = make_alert(id="2", total_premium="900000", total_ask_side_prem="890000", total_bid_side_prem="0")
    penny = make_alert(id="3", ticker="PNY", underlying_price="2")
    etn = make_alert(id="4", ticker="XYZ", issue_type="Index")
    amb = make_alert(id="5", ticker="AMB", has_multileg=True)
    assert [a.id for a in prefilter([a1, a2, penny, etn, amb])] == ["2"]


def test_weights_roundtrip(tmp_path):
    w = Weights("v1", {**V0.w, "flow_quality": 0.4}, {"n": 10})
    save_weights(w, tmp_path / "v1.json")
    assert load_weights(tmp_path / "v1.json") == w


def test_plan_levels_bounded_by_holding_period_move(make_alert):
    # spot 46, far put wall 17 → invalidation must be clamped near spot, not 60% away
    a = make_alert(underlying_price="46", strike="50", iv="0.8", expiry="2027-03-19",
                   total_premium="2000000", total_ask_side_prem="1950000", total_bid_side_prem="50000")
    v = evaluate(ctx(a, gex=GexLevels(200.0, 17.0, 50.0, 45.0), ref_price=46.0))
    em_h = 46 * 0.8 * (10 / 252) ** 0.5  # ≈ 7.33 over the 10-session hold
    assert 46 - v.plan.invalidation <= 1.0 * em_h + 1e-6
    assert v.plan.target - 46 <= 2.0 * em_h + 1e-6
    assert v.plan.invalidation < 46 < v.plan.target


def test_signed_weights_match_flipped_scores(make_alert):
    """A negative weight is 'fade this check': same score as a positive weight on the negated check."""
    base = evaluate(full(strong(make_alert)))
    w_pos = Weights("p", dict(V0.w))
    w_neg = Weights("n", dict(V0.w) | {"regime": -V0.w["regime"]})
    s_pos, s_neg = evaluate(full(strong(make_alert)), w_pos), evaluate(full(strong(make_alert)), w_neg)
    reg = next(c for c in base.checks if c.name == "regime")
    assert reg.available and reg.score != 0
    assert 0 <= s_neg.score_parity <= 100 and s_neg.coverage == s_pos.coverage
    delta = 50 * 2 * V0.w["regime"] * reg.score * reg.confidence
    par = sum(w for n, w in V0.w.items() if n in __import__("whaleproof.core.verdict.weights", fromlist=["x"]).BACKTESTABLE
              and next(c for c in base.checks if c.name == n).available)
    assert round(s_pos.score_parity - s_neg.score_parity, 1) == round(delta / par, 1)
