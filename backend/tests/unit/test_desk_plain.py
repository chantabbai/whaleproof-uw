from datetime import date
"""Plain-words layer: the engine's terse reason/why strings (which logic and stored history depend on) are rewritten
only on the way out of the API. Unknown text passes through unchanged, so nothing can be lost."""
from whaleproof.desk import plain


def test_gate_and_filter_reasons_read_as_sentences():
    cases = {
        "not a buy (ask-side 0% < 70%)": "Looks like a sale, not a buy: none of it traded at the asking price. We only count trades where 70% or more was bought at the ask.",
        "not a buy (ask-side 23% < 70%)": "Looks like a sale, not a buy: only 23% traded at the asking price. We only count trades where 70% or more was bought at the ask.",
        "not a buy (ask-side 55% < 70%)": "Mixed buying and selling: 55% traded at the asking price. We only count trades where 70% or more was bought at the ask.",
        "floor/cross trade": "A floor or cross trade, not a buyer on the open market.",
        "not clearly opening": "Can't tell that it opened a new position.",
        "multi-leg": "Part of a multi-leg trade.",
        "moneyness -15% outside −5%…+30%": "15% in the money. We only take 5% in to 30% out of the money.",
        "moneyness +42% outside −5%…+30%": "42% out of the money. We only take 5% in to 30% out of the money.",
        "DTE 168 outside 7–90": "Expires in 168 days. We only take 7 to 90 days.",
        "issue type Index": "Not a stock, ADR or ETF (Index).",
        "ETF put (likely hedge)": "A put on an ETF, which is usually a hedge.",
        "call and put both bought (vol play)": "Calls and puts bought together, a bet on a big move rather than a direction.",
        "same-second sold leg (spread leg)": "One leg of a spread: another leg was sold in the same second.",
        "bearish buy — put buys lost money on train (mostly hedges)":
            "Bearish. We only take bullish bets: most big put buys are insurance on stock people already own, not bets on a drop.",
        "stock $3.20 < $5 — thin, wide fills": "The stock is $3.20, under $5, where fills are thin and wide.",
        "earnings 2026-10-08 (postmarket) before the planned exit — IV crush risk":
            "Earnings on Oct 8 (after the close) land before the planned sell.",
        "far OTM but the option is rich vs the stock's realized move":
            "A long shot, but the option was expensive next to how much the stock really moves.",
        "below the bar: $3.0M, 0% OTM (needs ≥ $1.0M and > 5% OTM, or > 15% OTM at a fair price)":
            "Not big enough: $3.0M at the money. A signal needs $1.0M or more on a strike over 5% out, "
            "or a strike over 15% out at a fair price.",
        "Whale conviction bet": "Whale-size bet",
        "Far-OTM buy at a fair price": "Long shot, not overpriced",
        "below the bar: $5.8M, -1% OTM (needs ≥ $1.0M and > 5% OTM, or > 15% OTM at a fair price)":
            "Not big enough: $5.8M at 1% in the money. A signal needs $1.0M or more on a strike over 5% out, "
            "or a strike over 15% out at a fair price.",
    }
    for raw, want in cases.items():
        assert plain.reason(raw) == want, raw


def test_why_lines_read_as_sentences():
    cases = {
        "$1.8M calls bought at the ask (91% ask-side), single leg, opening position":
            "$1.8M in calls, 91% of it paid at the ask, one leg, a new position.",
        "Whale size: $1.8M on a strike 5% out of the money — a bold directional bet, not a hedge":
            "Whale-size: $1.8M on a strike 5% out of the money. That's a bet on direction, not a hedge.",
        "Far out of the money (23%) — deep OTM buying carries the most information (Pan & Poteshman 2006)":
            "A long shot: the strike is 23% out of the money.",
        "Sweep: filled across exchanges — urgency": "Swept across exchanges, so the buyer was in a hurry.",
        "49 days to expiry": "49 days until it expires.",
        "1 days to expiry": "1 day until it expires.",
        "Repeat buying: 10 other clean buy(s) same direction in the last 3 sessions":
            "Someone kept buying: 10 other clean buys the same way in the last 3 sessions.",
        "Repeat buying: 1 other clean buy(s) same direction in the last 3 sessions":
            "Someone kept buying: 1 other clean buy the same way in the last 3 sessions.",
        "No earnings before the planned exit (2026-10-09)": "No earnings before the planned sell on Oct 9.",
        "Earnings date not available — check before trading": "No earnings date on file, so check before trading.",
        "Option fair: IV rank 32 (0 = cheapest of the past year, 100 = richest); option IV 18% vs stock's recent "
        "realized move 16% (×1.15) — info only":
            "The option was fairly priced: IV rank 32 of 100 over the past year. Implied vol 18% vs 16% realized "
            "lately (1.15×), about in line with how much the stock moves.",
        "Option cheap: IV rank 3 (0 = cheapest of the past year, 100 = richest); option IV 83% vs stock's recent "
        "realized move 53% (×1.57) — info only":
            "The option was cheap: IV rank 3 of 100 over the past year. But implied vol 83% vs 53% realized "
            "lately (1.57×) is pricey next to how much the stock moves.",   # two views disagree: say so (trader 10-20)
        "Option rich: IV rank 80 (0 = cheapest of the past year, 100 = richest); option IV 30% vs stock's recent "
        "realized move 40% (×0.75) — info only":
            "The option was expensive: IV rank 80 of 100 over the past year. But implied vol 30% vs 40% realized "
            "lately (0.75×) is cheap next to how much the stock moves.",
        "Option rich: IV rank 100 (0 = cheapest of the past year, 100 = richest)":
            "The option was expensive: IV rank 100 of 100 over the past year.",
        "Option cheap": "The option was cheap.",
    }
    for raw, want in cases.items():
        assert plain.why(raw) == want, raw


def test_option_value_note_reads_plainly():
    assert plain.reason("IV rank 100 (0 = cheapest of the past year, 100 = richest); option IV 44% vs stock's recent "
                        "realized move 24% (×1.83) — info only") == (
        "IV rank 100 of 100 over the past year. Implied vol 44% vs 24% realized lately (1.83×), pricey next to how much "
        "the stock moves.")
    assert plain.reason("IV rank 3 (0 = cheapest of the past year, 100 = richest)") == "IV rank 3 of 100 over the past year."


def test_whale_bet_with_an_expensive_option_says_price_was_not_checked():
    out = plain.humanize({"why": ["Whale size: $1.2M on a strike 5% out of the money — a bold directional bet, not a hedge",
                                  "Option rich: IV rank 100 (0 = cheapest of the past year, 100 = richest)"]})
    assert out["why"][1] == ("The option was expensive: IV rank 100 of 100 over the past year. Whale-size bets pass "
                             "whatever the option costs.")


def test_unknown_text_passes_through():
    assert plain.reason("something new") == "something new"
    assert plain.why("Another line") == "Another line"


def test_humanize_rewrites_only_known_keys_and_keeps_shape():
    payload = {"day": "2026-10-02", "label": "train",
               "signals": [{"ticker": "QQQ", "label": "Whale conviction bet", "reason": "Whale conviction bet",
                            "why": ["49 days to expiry"], "tier": "whale"}],
               "rejected_top": [{"reason": "floor/cross trade", "premium": 1}],
               "bets": [{"reason": "", "bet_kind": "clean buy"}]}
    out = plain.humanize(payload)
    assert out["label"] == "train"                                 # not a tier label: untouched
    s = out["signals"][0]
    assert s["label"] == "Whale-size bet" and s["tier"] == "whale" and s["why"] == ["49 days until it expires."]
    assert out["rejected_top"][0] == {"reason": "A floor or cross trade, not a buyer on the open market.", "premium": 1}
    assert out["bets"][0]["reason"] == "" and out["bets"][0]["bet_kind"] == "clean buy"
    assert payload["signals"][0]["why"] == ["49 days to expiry"]   # input not mutated


def test_plain_dates_outside_this_year_carry_the_year():
    from whaleproof.desk.plain import _md
    assert _md("2027-01-15", today=date(2026, 12, 30)) == "Jan 15, 2027"
    assert _md("2026-10-09", today=date(2026, 10, 13)) == "Oct 9"
