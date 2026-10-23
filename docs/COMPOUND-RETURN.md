# What would compounding the signals in stock have returned?

_Exploratory (owner question, 2026-09-30). This is a portfolio simulation of the frozen filter; it did not tune anything.
Script `backend/scripts/research/compound_stock_signals.py` → `journal/research/compound-stock-signals.json`._

## Method
- **Capital:** split into 5 equal sleeves (20% each). The sleeve used on flow day *i* is used again on day *i*+5.
- **Trades:** buy the stock at the next open and sell at the close of the 5th session. A day's signals share their
  sleeve equally. On a day with no signals, the sleeve stays in cash at 0%.
- **Returns:** raw stock return, net 0.10% round trip, booked on the day each trade is sold (when the money arrives).
  There are no taxes, no extra slippage and no leverage.
- **Benchmark:** SPY bought at the first trade's entry and sold at the last trade's exit.
- **Coverage:** flow days through 2026-09-22, the last day with a complete 5-session outcome.

## Result ($1 start)
| Window | Signals (all) | Max DD | Whale only | Far-OTM only | SPY hold |
|---|---|---|---|---|---|
| Pre-period 2023-10-31 → 2024-09-27 (out-of-sample) | **+64%** (n 233) | −17% | +14% | +60% | +37% |
| Train 2024-10 → 2025-09 (in-sample, tuned) | **+161%** (n 488) | −14% | +12% | +112% | +18% |
| Holdout 2025-10 → 2026-05 (out-of-sample) | **+53%** (n 628) | −15% | +9% | +65% | +10% |
| Post-period 2026-06 → 09-22 (seen) | **−17%** (n 318) | −25% | −6% | −24% | +1% |
| **All, ~2.9 years** | **+492% (CAGR ~86%)** | −25% | +26% | +352% | +82% (CAGR ~23%) |

## Caveats (read before believing it)
- **Compounding magnifies a small, unproven edge.** About 50 trade cycles a year on each sleeve turn ~+2% a week into
  triple digits. The per-trade 95% ranges still touch 0, so the compounded figure is just as unproven.
- **Recent months lost.** Jun–Sep 2026 was −17% while SPY was flat. Any live start date can land in a period like that.
- **The train window is in-sample.** The filter was chosen on that window, so +161% is optimistic.
- **Beta.** These are high-beta stocks (signals average about 2.1–2.4× SPY's moves): COIN, SMCI, SOXL, PLTR. This
  simulation does not remove that. Per trade, beta-adjusted holdout returns are about 40% of the plain ones
  ([`BETA-CHECK.md`](BETA-CHECK.md)).
- **Concentration.** A day with a single signal puts 20% of capital into one stock for a week.
- **Drawdowns are understated.** Equity is marked only when trades close. Marking open trades daily would show deeper dips.
- **Fat tails.** In the pre-period, removing the top 5 far-OTM trades halves that tier's mean. The compounded result
  leans on a few big winners.
- **Not modelled:** taxes on short-term gains, extra slippage on open orders, and position-size limits on thin names.

**Reading.** The historical stock path made large gains in 3 of 4 windows and lost in the most recent one. It is a
reason to paper-trade, not proof.

Shown on the Methodology page ("If you had traded every signal in stock"), labelled exploratory, per window, never as
a headline. Reproduce: `cd backend && uv run python scripts/research/compound_stock_signals.py` (cache-only).
