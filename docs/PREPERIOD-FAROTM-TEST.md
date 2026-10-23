# Second sealed test, part two: long shots, the last historical test of the frozen filter

_Written 2026-09-30 ~20:00 ET, **before** any IV-rank data for the candidate tickers was fetched, and before any
long-shot outcome in that year was looked at. Follow-up to `docs/PREPERIOD-TEST.md`. After this, historical
testing stops; the evidence from here on is the forward journal._
_Wording edited 2026-10-21 to match the app's names; rules, numbers and verdicts unchanged._

## Why
The first part of the second sealed test (2023-10-31 → 2024-09-27) could only test whale-size bets. Every long-shot
candidate had option value "unknown", so none could become a signal. Long shots carried most of the practice-year and
sealed-test edge (+1.46% and +1.70% per trade), and they had never been tested outside those periods.

**Corrected cause** (this replaces the explanation in PREPERIOD-TEST.md). No period has alert IV in my cache: 0 of
the long-shot candidates in the practice year and sealed test carry `iv` (only 11 alerts in the recent months do). So the option-value check
has always used the **IV-rank fallback** (`value_view`: rank ≤ 30 cheap, ≥ 70 rich, otherwise fair). The 2023–24
gap was only that my IV-rank cache started 2024-09-26. Once that history is backfilled, this year uses **the same
basis as the practice year and the sealed test**.

## Probe (done before writing this; SPY only, not a candidate)
`/api/stock/SPY/iv-rank?date=2024-09-27&timespan=1y` returns 200, 252 rows from 2023-09-28 → 2024-09-27, with
`iv_rank_1y` non-null in Nov 2023. So one call per ticker covers the whole period. UW count 34,096 after the probe.

## Fixed in advance
- **Period:** 2023-10-31 → 2024-09-27, the same 229 sessions as PREPERIOD-TEST.
- **Filter:** frozen, `FilterConfig` hash `84ef5cdce1cbe4e1`, with no change of any kind. Long shot = clean bullish
  opening buy, stock ≥ $5, no earnings in the hold, strike > 15% out of the money, option cheap or fair, and not already
  a whale-size bet.
- **Data to fetch:** IV rank (`date=2024-09-27&timespan=1y`, 1 call each) for every ticker with a clean bullish buy
  more than 15% out of the money in the period. That is 140 unique tickers, before the price and earnings stages, so the set does not
  depend on later filter stages. Nothing else is fetched. Script: `backend/scripts/research/preperiod_ivrank_backfill.py`.
- **Point-in-time:** the value is `latest_metric(on_or_before = flow day)`. That is the flow day's own end-of-day IV
  rank (UW `updated_at` ≈ 18:35 ET), which is a slight same-day lookahead. It is **identical to the practice year and the sealed test**,
  where the same code was used, and entry is still the next open.
- **Rows:** rebuild only the three 2023–24 pickles with `scripts/desk_build_rows.py`. The old pickles are backed up
  first, because they reproduce `desk-preperiod.json`. Practice-year pickles are not rebuilt.
- **Sanity check before the run (no outcomes printed):** only `value` may change between the old and new pickles. The
  whale-size bet count must stay 63. Anything else changing → stop and report.
- **Primary set:** long shots (`tier == "far_otm"`) in the period.
- **Primary metric:** `x5` = five-day return in the signal direction minus the S&P 500 (SPY), entry at the next open, 0.10% cost.
  Reported per trade and per day, with a 5-day block-bootstrap 95% range (same code as all periods).
- **Verdict rule:**
  - Fewer than 30 long shots → **"inconclusive"**, whatever the numbers.
  - Otherwise **"supports the far-OTM edge"** only if **both** hold:
    1. the long shots' per-trade mean beats all one-way alerts;
    2. the long shots' per-day 95% range lies entirely above 0.
  - Otherwise **"does not support"**.
- **Secondary (descriptive):** the whole filter (whale-size bets + long shots) in the period. The earlier
  `desk-preperiod.json` verdict (whale-size bets only, "does not support") stands and is never rewritten.
- **Runs once.** `whaleproof evidence --preperiod-farotm` writes `journal/desk-preperiod-farotm.json` and refuses a
  second run.

## Result
Run once 2026-09-30 ~20:15 ET → `journal/desk-preperiod-farotm.json`. IV rank was fetched for 140 tickers (140
calls, UW count 34,236). Sanity check passed: across 61,850 rows only `value` changed, and whale-size bets stayed 63.

**Verdict: does not support** (by a hair). The long-shot mean beats all one-way alerts by a wide margin, but the
per-day 95% range starts at −0.03%, just below 0.

| Second sealed test 2023-10-31 → 2024-09-27 | Trades | Per trade vs S&P 500 | Median | Per day (95% range) | Win |
|---|---|---|---|---|---|
| All one-way alerts | 61,833 | −0.07% | −0.10% | −0.06% (−0.12 … −0.01) | 49% |
| **Long shots** | **170** | **+2.17%** | +0.73% | +1.97% (**−0.03 … +4.51**) | 53% |
| Whale-size bets (unchanged) | 63 | +0.59% | +0.18% | +0.83% (−2.12 … +3.09) | 51% |
| Whole filter (secondary) | 233 | +1.74% | +0.53% | +1.59% (−0.18 … +3.96) | 52% |

The whole filter makes ~1.0 signals/day. Monthly means were positive in 8 of 11 months (Jan, Apr and Aug 2024 negative).

**Exploratory (post-hoc, `journal/research/farotm-preperiod-robustness.json`):**
- The edge is skewed: drop the top 5 trades and the mean is +1.09%; trim 5 off each side and it is +1.84%.
- It is spread across 102 tickers (COIN 11, SMCI 6, SOXL/AFRM/PLTR 5). Ticker-weighted mean +2.03%; 55 of 102 tickers
  were positive.
- By value: cheap +2.65% (67 trades), fair +1.86% (103 trades).
- The period was a strong momentum and high-beta rally (2023-11 → 2024-03). The metric subtracts the S&P 500, but it does not
  remove beta above 1, so part of this may be beta.

**Reading.** Long shots were positive in all three periods where they could be tested:

| Period | Trades | Per trade | Per-day 95% range |
|---|---|---|---|
| Practice year (rules tuned here) | 382 | +1.46% | +0.03 … +3.26 |
| Sealed test | 475 | +1.70% | −0.00 … +2.90 |
| Second sealed test | 170 | +2.17% | −0.03 … +4.51 |

Both sealed-test ranges sit right at 0 (the practice year's barely clears it), so the pre-registered verdict is
"does not support". The edge is
still **not proven**. It is the most consistent pattern I have, but fat-tailed, and possibly high-beta exposure.
Historical testing stops here; the forward journal is the remaining evidence.

Rerun the numbers: `uv run python scripts/research/preperiod_ivrank_backfill.py` (cached) → rebuild the three 2023–24 pickles
with `scripts/desk_build_rows.py` → `whaleproof evidence --preperiod-farotm` (refuses if the JSON exists).
