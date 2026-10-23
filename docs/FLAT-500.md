# $500 per trade, stock only — exploratory (owner question 2026-10-02, not in UI)

**Label: exploratory.** Signals = frozen filter (no change). Periods mixed: practice year was used to tune.

**Method.** Every bet = $500 of the stock bought at the next session open, sold at the close of the 5th session
(`r5`, net 0.10% round trip). Same unit as tracker/lookup: one bet per ticker+direction+kind per day (biggest alert).
No compounding, no position cap — each trade is its own $500. "SPY same $" = the same $500 in SPY over the same 5
sessions (long). Signals are bullish-only by design, so "buy" = "with direction" for them.
Ways to act on all bets: *with direction* (bullish → buy, bearish → short), *buy bullish only*, *buy every alert*
(bearish bets bought anyway).

| Group | Period | Trades | Total P/L | Avg / trade | Win | SPY same $ |
|---|---|---:|---:|---:|---:|---:|
| **Signals** | Second sealed test (2023–24) | 233 | +$2,527 | +$10.85 | 56% | +$497 |
| | Practice year (tuned here) | 488 | +$3,777 | +$7.74 | 55% | +$788 |
| | Sealed test | 628 | +$6,003 | +$9.56 | 54% | +$1,505 |
| | Recent months | 318 | −$2,701 | −$8.49 | 40% | −$244 |
| | **All** | **1,667** | **+$9,606** | **+$5.76** | 52% | +$2,546 |
| All bets · with direction | All | 275,187 | −$90,140 | −$0.33 | 49% | — |
| All bets · buy bullish only | All | 142,990 | +$266,407 | +$1.86 | 51% | +$248,576 |
| All bets · buy every alert | All | 275,187 | +$490,758 | +$1.78 | 51% | +$480,525 |

1,681 signals in history; 14 (Sep 21–29 2026) have no finished 5-session result yet → 1,667 here
(tracker counts differ by the same cache edge).

(Per-period rows for all-bets groups: `journal/research/flat-500-per-trade.json`.)

**Capital needed (computed from rows).** Open signal positions per session: average 11.5 (≈ $5.7K), peak 59
(≈ $29.5K). SPY buy-and-hold over the same span (2023-11-02 open → 2026-09-23 close) = +80.0%.

**Conclusion.** Signals beat SPY on the *same 5-day windows* (+$9.6K vs +$2.5K) but **lose to simply holding SPY on
the cash you'd need**: $29.5K peak capital in SPY → ≈ +$23.6K; even the average $5.7K → ≈ +$4.6K while the rest sits
idle. Recent months lost $2.7K. Blindly trading every alert = market beta: buying all ≈ SPY on the same days
(+$491K vs +$481K); following direction loses (shorts lose in an up market). Not proven.

**Caveats.** No slippage beyond 0.10%; no capital limit (overlapping trades); all-bets groups count every flagged bet,
not something a person could execute.

Reproduce: `cd backend && uv run python scripts/research/flat_500_per_trade.py` (cache only, ~20 s).
