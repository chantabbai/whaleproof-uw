"""History lookup: "how did bets like this do?" — descriptive bucket stats over the history rows, point-in-time,
split by period, with the all-bets baseline. Never a filter."""
from datetime import date, timedelta

import pytest

from whaleproof.desk.lookup import MIN_MATCHES, Bet, LookupIndex, bands, bet_from_raw


def bet(d=date(2025, 3, 3), x5=0.01, **kw):
    base = dict(session_date=d, ticker="AAA", direction=1, opt_type="call", kind="clean buy", premium=600_000,
                dte=20, otm_pct=0.08, sweep=True, sector="Technology", x5=x5)
    return Bet(**(base | kw))


def many(n, start=date(2025, 1, 6), **kw):
    return [bet(d=start + timedelta(days=i % 200), **kw) for i in range(n)]


def test_bands_cover_edges():
    assert bands(premium=99_999, dte=7, otm_pct=-0.01) == ("<100K", "≤7d", "ITM")
    assert bands(premium=100_000, dte=8, otm_pct=0.0) == ("100K–500K", "8–30d", "0–5% OTM")
    assert bands(premium=999_999, dte=90, otm_pct=0.05) == ("500K–1M", "31–90d", "5–15% OTM")
    assert bands(premium=1_000_000, dte=91, otm_pct=0.15) == ("≥1M", ">90d", ">15% OTM")


def test_bet_from_raw_maps_labels_and_sweep():
    r = {"session_date": date(2025, 3, 3), "ticker": "AAA", "direction": -1, "label": "NOISE", "premium": 2e5,
         "dte": 12, "otm_pct": 0.03, "sector": None, "x5": -0.02, "gate_fail": "not a buy (ask-side 0% < 70%)"}
    b = bet_from_raw(r, {"has_sweep": True, "type": "call"})
    assert (b.kind, b.opt_type, b.sweep, b.direction, b.gate_fail) == ("not a clean buy", "call", True, -1,
                                                                      "not a buy (ask-side 0% < 70%)")
    assert bet_from_raw(r | {"label": "PURE"}, {}).kind == "clean buy"
    assert bet_from_raw(r | {"label": "PUT_SALE"}, {}).kind == "put sale"


def test_full_match_used_when_enough():
    idx = LookupIndex(many(40, x5=0.02) + many(40, x5=-0.01, sector="Energy"))
    out = idx.lookup(bet(), before=date(2026, 1, 1))
    assert out["matches"] == 40 and out["traits_dropped"] == []
    assert out["win_share"] == 1.0 and out["avg"] == pytest.approx(0.02)
    assert out["thin"] is False


def test_back_off_drops_sector_then_sweep():
    rows = many(20, x5=0.01) + many(20, x5=0.03, sector="Energy") + many(5, x5=-0.05, sweep=False)
    idx = LookupIndex(rows)
    out = idx.lookup(bet(), before=date(2026, 1, 1))
    assert out["traits_dropped"] == ["sector"] and out["matches"] == 40
    out2 = idx.lookup(bet(sector="Utilities", sweep=False), before=date(2026, 1, 1))
    assert out2["traits_dropped"] == ["sector", "sweep"] and out2["matches"] == 45


def test_point_in_time_excludes_outcomes_not_known_yet():
    d = date(2025, 6, 2)                                   # Monday; 5-session hold ends the next Monday
    rows = many(MIN_MATCHES, x5=0.01) + [bet(d=d, x5=0.5)]
    idx = LookupIndex(rows)
    assert idx.lookup(bet(), before=d + timedelta(days=3))["matches"] == MIN_MATCHES
    assert idx.lookup(bet(), before=d + timedelta(days=10))["matches"] == MIN_MATCHES + 1


def test_thin_when_even_coarsest_bucket_small():
    idx = LookupIndex(many(5))
    out = idx.lookup(bet(), before=date(2026, 1, 1))
    assert out["thin"] is True and out["matches"] == 5


def test_period_split_and_agreement_and_baseline():
    practice = many(40, start=date(2024, 11, 4), x5=0.02)
    sealed = many(40, start=date(2025, 11, 3), x5=-0.01)
    other = many(40, start=date(2024, 11, 4), x5=-0.03, direction=-1, opt_type="put")
    idx = LookupIndex(practice + sealed + other)
    out = idx.lookup(bet(), before=date(2026, 9, 1))
    names = {p["period"]: p for p in out["periods"]}
    assert names["Practice year (Oct 2024–Sep 2025, rules chosen here)"]["avg"] == pytest.approx(0.02)
    assert names["Sealed test (Oct 2025–May 2026)"]["avg"] == pytest.approx(-0.01)
    assert out["periods_agree"] is False
    assert out["baseline"]["matches"] == 120
    assert out["baseline"]["avg"] == pytest.approx((40 * 0.02 - 40 * 0.01 - 40 * 0.03) / 120)
    assert "in_plain_words" in out and "bets like this" in out["in_plain_words"]


def test_rows_without_outcome_are_ignored():
    idx = LookupIndex(many(MIN_MATCHES) + many(10, x5=None))
    assert idx.lookup(bet(), before=date(2026, 1, 1))["matches"] == MIN_MATCHES


def test_plain_words_use_the_true_minus():
    from whaleproof.desk.lookup import _pct
    assert _pct(-0.005) == "−0.5%" and _pct(0.012) == "+1.2%"


def test_a_move_that_rounds_to_zero_has_no_sign():
    """Copy guard (owner 10-13): an average like −0.04% read "−0.0%" on All bets; it reads "0.0%", as in the MCP."""
    from whaleproof.desk.lookup import _pct
    assert _pct(-0.0004) == "0.0%" and _pct(0.0004) == "0.0%" and _pct(0.0) == "0.0%"
    assert _pct(-0.0006) == "−0.1%" and _pct(0.0006) == "+0.1%"


def test_no_sector_given_means_any_sector_not_the_unknown_sector():
    """Owner 10-12 (by-hand check showed 'Matched on … Unknown'): a lookup without a sector must pool every sector,
    not only history bets whose sector happens to be unknown, and must not claim sector was dropped."""
    idx = LookupIndex(many(40, x5=0.02) + many(40, x5=-0.01, sector="Energy") + many(35, x5=0.05, sector=None))
    out = idx.lookup(bet(sector=None), before=date(2026, 1, 1))
    assert out["matches"] == 115 and "sector" not in out["traits"] and out["traits_dropped"] == []


def test_one_voting_period_is_named_with_the_rule():
    """'Only one test period has enough bets to judge' sat above a table of four periods (owner 10-13 sweep)."""
    from whaleproof.desk.lookup import plain_words
    base = {"matches": 33, "win_share": 0.36, "avg": -0.029, "baseline": {"avg": -0.001}, "thin": False, "periods_agree": None}
    one = plain_words(base | {"periods": [{"period": "Practice year", "matches": 9}, {"period": "Sealed test (Oct 2025–May 2026)", "matches": 12}]})
    assert one.endswith("Only Sealed test (Oct 2025–May 2026) has 10 or more of them, so there's no second period to compare it with.")
    none = plain_words(base | {"periods": [{"period": "Practice year", "matches": 9}]})
    assert none.endswith("No test period has 10 or more of them on its own, so the periods can't be compared.")
