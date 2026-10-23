"""Pure-directional gate + setup tagging (docs/preregistration.md Amendment 3)."""
from datetime import date, datetime, timezone

from tests.conftest import raw_alert
from whaleproof.core.data_layer.models import parse_alert
from whaleproof.core.verdict.setups import gate_failures, repeat_buys, setup_for

AS_OF = datetime(2026, 9, 25, 20, 15, tzinfo=timezone.utc)
D = date(2026, 9, 25)


def clean(**over):
    """Opening, 95% ask-side, single-leg, 5% OTM, 21 DTE call on a stock — passes the gate."""
    base = dict(underlying_price="190", strike="200", expiry="2026-10-16", total_premium="500000",
                total_ask_side_prem="475000", total_bid_side_prem="25000", all_opening_trades=True,
                has_multileg=False, has_sweep=False)
    base.update(over)
    return parse_alert(raw_alert(**base))


def fails(a, others=()):
    return gate_failures(a, list(others), AS_OF)


def test_clean_buy_passes():
    assert fails(clean()) == []


def test_selling_is_not_directional():
    a = clean(total_ask_side_prem="100000", total_bid_side_prem="400000")
    assert any("not a buy" in f for f in fails(a))


def test_multileg_floor_and_not_opening():
    assert any("multi-leg" in f for f in fails(clean(has_multileg=True)))
    assert any("floor" in f for f in fails(clean(has_floor=True)))
    closing = clean(all_opening_trades=False, volume=100, open_interest=5000, total_size=100, volume_oi_ratio="0.02")
    assert any("opening" in f for f in fails(closing))


def test_moneyness_and_dte_bounds():
    assert any("moneyness" in f for f in fails(clean(strike="150")))       # deep ITM call (−21%)
    assert any("moneyness" in f for f in fails(clean(strike="260")))       # +37% OTM lotto
    assert fails(clean(strike="240")) == []                                 # +26% far OTM ok (Amendment 5)
    assert fails(clean(strike="185")) == []                                 # −2.6% slightly ITM ok
    assert any("DTE" in f for f in fails(clean(expiry="2026-09-29")))       # 4 DTE
    assert any("DTE" in f for f in fails(clean(expiry="2027-03-19")))       # 175 DTE


def test_etf_puts_are_hedges_but_etf_calls_ok():
    put = clean(ticker="XLF", issue_type="ETF", type="put", strike="180", option_chain="XLF261016P00180000")
    assert any("ETF put" in f for f in fails(put))
    assert fails(clean(ticker="XLF", issue_type="ETF")) == []


def test_same_day_call_and_put_buying_is_vol_play():
    a = clean()
    put_buy = clean(id="p1", type="put", strike="180", option_chain="NVDA261016P00180000",
                    created_at="2026-09-25T14:35:00Z", total_premium="300000", total_ask_side_prem="290000",
                    total_bid_side_prem="10000")
    assert any("vol play" in f for f in fails(a, [a, put_buy]))
    small = clean(id="p2", type="put", strike="180", option_chain="NVDA261016P00180000",
                  total_premium="100000", total_ask_side_prem="95000", total_bid_side_prem="5000")
    assert fails(a, [small]) == []                                          # < 50% of our premium
    late = clean(id="p3", type="put", strike="180", option_chain="NVDA261016P00180000",
                 created_at="2026-09-25T20:30:00Z", total_premium="300000", total_ask_side_prem="290000",
                 total_bid_side_prem="10000")
    assert fails(a, [late]) == []                                           # after as_of → unknown at decision
    other_ticker = clean(id="p4", ticker="AMD", type="put", strike="180", option_chain="AMD261016P00180000",
                         total_premium="300000", total_ask_side_prem="290000", total_bid_side_prem="10000")
    assert fails(a, [other_ticker]) == []


def test_same_second_sold_leg_is_spread():
    a = clean()
    leg = clean(id="s1", strike="210", option_chain="NVDA261016C00210000", created_at="2026-09-25T14:30:00.500Z",
                total_ask_side_prem="10000", total_bid_side_prem="490000")
    assert any("spread leg" in f for f in fails(a, [leg]))
    later = clean(id="s2", strike="210", option_chain="NVDA261016C00210000", created_at="2026-09-25T14:31:00Z",
                  total_ask_side_prem="10000", total_bid_side_prem="490000")
    assert fails(a, [later]) == []


def test_setup_priority():
    earn = [date(2026, 9, 30)]
    assert setup_for(clean(has_sweep=True, total_premium="2000000", total_ask_side_prem="1900000"),
                     earn, 3) == "pre_earnings"
    assert setup_for(clean(has_sweep=True, total_premium="2000000", total_ask_side_prem="1900000"),
                     [date(2026, 11, 1)], 3) == "whale_sweep"
    assert setup_for(clean(has_sweep=True), [], 2) == "repeat_buyer"
    assert setup_for(clean(has_sweep=True), [], 1) == "sweep"
    assert setup_for(clean(), [date(2026, 9, 20)], 0) == "clean_other"     # past earnings ignored
    assert setup_for(clean(strike="235", has_sweep=True, total_premium="2000000", total_ask_side_prem="1900000"),
                     [], 3) == "far_otm"                                    # +24% OTM beats whale/repeat


def test_vol_play_needs_same_expiry_within_15_minutes():
    a = clean()                                                            # 14:30Z, expiry 2026-10-16
    other_expiry = clean(id="q1", type="put", strike="180", option_chain="NVDA261120P00180000",
                         expiry="2026-11-20", total_premium="300000", total_ask_side_prem="290000",
                         total_bid_side_prem="10000")
    assert fails(a, [other_expiry]) == []                                  # two-sided flow, not a straddle
    later = clean(id="q2", type="put", strike="180", option_chain="NVDA261016P00180000",
                  created_at="2026-09-25T15:00:00Z", total_premium="300000", total_ask_side_prem="290000",
                  total_bid_side_prem="10000")
    assert fails(a, [later]) == []                                         # 30 minutes apart
    strangle = clean(id="q3", type="put", strike="180", option_chain="NVDA261016P00180000",
                     created_at="2026-09-25T14:40:00Z", total_premium="300000", total_ask_side_prem="290000",
                     total_bid_side_prem="10000")
    assert any("vol play" in f for f in fails(a, [strangle]))


def test_repeat_buys_count_only_gate_passing_buys():
    a = clean(id="now")
    prior_buy = clean(id="b1", created_at="2026-09-24T15:00:00Z")
    sold_put = clean(id="s1", type="put", strike="180", option_chain="NVDA261016P00180000",
                     created_at="2026-09-24T16:00:00Z", total_ask_side_prem="20000",
                     total_bid_side_prem="480000")                         # bullish by old rule, but a sale
    closing = clean(id="c1", created_at="2026-09-23T15:00:00Z", all_opening_trades=False, volume=10,
                    open_interest=9000, total_size=10, volume_oi_ratio="0.001")
    other_dir = clean(id="p1", type="put", strike="180", option_chain="NVDA261016P00180000",
                      created_at="2026-09-24T17:00:00Z")
    assert repeat_buys(a, [a, prior_buy, sold_put, closing, other_dir], AS_OF) == 1


# ---------- Amendment 9: gated official candidates + put_sale ----------
def test_pure_only_keeps_gate_passers():
    from whaleproof.core.verdict.setups import pure_only
    buy = clean(id="b")
    sold = clean(id="s", ticker="AMD", option_chain="AMD261016C00200000",
                 total_ask_side_prem="20000", total_bid_side_prem="480000")
    assert [a.id for a in pure_only([buy, sold], AS_OF)] == ["b"]


def test_put_sale_setup():
    from whaleproof.core.verdict.setups import is_put_sale
    sale = clean(type="put", strike="180", option_chain="NVDA261016P00180000",
                 total_ask_side_prem="20000", total_bid_side_prem="480000")    # −5.3% OTM put, sold, opening
    assert is_put_sale(sale, [sale], AS_OF) and sale.direction == 1
    call_sale = clean(total_ask_side_prem="20000", total_bid_side_prem="480000")
    assert not is_put_sale(call_sale, [call_sale], AS_OF)                      # covered-call style → no
    itm = clean(type="put", strike="200", option_chain="NVDA261016P00200000",
                total_ask_side_prem="20000", total_bid_side_prem="480000")      # ITM put (−5% OTM → ITM)
    assert not is_put_sale(itm, [itm], AS_OF)
    short_dte = clean(type="put", strike="180", option_chain="NVDA260929P00180000", expiry="2026-09-29",
                      total_ask_side_prem="20000", total_bid_side_prem="480000")
    assert not is_put_sale(short_dte, [short_dte], AS_OF)                      # 4 DTE
    assert not is_put_sale(clean(type="put", strike="180", option_chain="NVDA261016P00180000"),
                           [], AS_OF)                                           # a bought put is not a sale


def _reference_gate_failures(a, same_day, as_of):
    """The gate exactly as it was before the 10-16 speed-up (full scans) — the indexed version must match it."""
    from whaleproof.core.verdict.setups import (BUY_SHARE, DTE_RANGE, GATE_TYPES, MONEYNESS, SPREAD_LEG_SECONDS,
                                                VOL_PLAY_RATIO, VOL_PLAY_SECONDS, _opening)
    out = []
    if a.ask_share < BUY_SHARE:
        out.append(f"not a buy (ask-side {a.ask_share * 100:.0f}% < {BUY_SHARE * 100:.0f}%)")
    if a.has_multileg:
        out.append("multi-leg")
    if a.has_floor:
        out.append("floor/cross trade")
    if not _opening(a):
        out.append("not clearly opening")
    if not MONEYNESS[0] <= a.otm_pct <= MONEYNESS[1]:
        out.append(f"moneyness {a.otm_pct * 100:+.0f}% outside −5%…+30%")
    if not DTE_RANGE[0] <= a.dte <= DTE_RANGE[1]:
        out.append(f"DTE {a.dte} outside 7–90")
    if a.issue_type not in GATE_TYPES:
        out.append(f"issue type {a.issue_type or 'unknown'}")
    elif a.issue_type == "ETF" and a.kind == "put":
        out.append("ETF put (likely hedge)")
    for o in same_day:
        if o.id == a.id or o.ticker != a.ticker or o.created_at > as_of or o.has_multileg:
            continue
        if (o.kind != a.kind and o.expiry == a.expiry and o.ask_share >= BUY_SHARE
                and o.total_premium >= VOL_PLAY_RATIO * a.total_premium
                and abs((o.created_at - a.created_at).total_seconds()) <= VOL_PLAY_SECONDS):
            out.append("call and put both bought (vol play)")
            break
    for o in same_day:
        if (o.id != a.id and o.ticker == a.ticker and o.kind == a.kind and o.bid_share >= BUY_SHARE
                and abs((o.created_at - a.created_at).total_seconds()) <= SPREAD_LEG_SECONDS):
            out.append("same-second sold leg (spread leg)")
            break
    return out


def _random_day(rng, n):
    """A busy ticker-day with prints bunched around the vol-play (900 s) and spread-leg (1 s) boundaries."""
    from dataclasses import replace
    from datetime import timedelta
    base, t0 = clean(), datetime(2026, 9, 25, 15, 0, tzinfo=timezone.utc)
    edges = [0, 0.5, 0.999999, 1.0, 1.000001, 899.999999, 900.0, 900.000001, 1800]
    out = []
    for i in range(n):
        off = rng.choice(edges) * rng.choice((-1, 1)) + rng.choice((0, 0, rng.uniform(-20000, 20000)))
        prem = rng.choice((100_000, 250_000, 500_000, 1_000_000))
        ask = rng.choice((0.0, 0.3, 0.7, 0.95, 1.0))
        bid = rng.choice((0.0, 1 - ask, 0.7, 0.95)) if ask < 0.7 else 1 - ask
        out.append(replace(base, id=f"x{i}", ticker=rng.choice(("AAA", "AAA", "AAA", "BBB")),
                           kind=rng.choice(("call", "put")), expiry=rng.choice((date(2026, 10, 16), date(2026, 10, 23))),
                           created_at=t0 + timedelta(seconds=off), total_premium=prem, ask_prem=prem * ask,
                           bid_prem=prem * min(bid, 1 - ask), has_multileg=rng.random() < 0.1))
    return out


def test_indexed_gate_matches_the_full_scan_on_random_busy_days():
    """Speed-up 10-16 (cold Sightings 93 s): the same-day checks look only at prints near in time. Same answer as the
    full scan for every alert, including prints exactly on the 1 s / 15 min edges and after the decision time."""
    import random
    rng = random.Random(1016)
    for trial in range(40):
        day = _random_day(rng, rng.choice((1, 2, 5, 30, 120)))
        as_of = datetime(2026, 9, 25, 15, 0, tzinfo=timezone.utc) + __import__("datetime").timedelta(
            seconds=rng.choice((0, 900, 30000)))
        for a in day:
            assert gate_failures(a, day, as_of) == _reference_gate_failures(a, day, as_of), (trial, a.id)


def test_indexed_gate_sees_a_list_that_grew_and_a_fresh_list():
    import random
    rng = random.Random(7)
    day = _random_day(rng, 40)
    first = [gate_failures(a, day, AS_OF) for a in day]
    day.append(_random_day(random.Random(8), 1)[0])           # grew after a call: the index must be rebuilt
    assert [gate_failures(a, day, AS_OF) for a in day] == [_reference_gate_failures(a, day, AS_OF) for a in day]
    assert first == [_reference_gate_failures(a, day[:-1], AS_OF) for a in day[:-1]]
    for _ in range(3):                                         # fresh lists every time, as callers build them
        fresh = list(_random_day(rng, 25))
        assert [gate_failures(a, fresh, AS_OF) for a in fresh] == [_reference_gate_failures(a, fresh, AS_OF) for a in fresh]
