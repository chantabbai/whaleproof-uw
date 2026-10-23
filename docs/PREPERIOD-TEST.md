# Second sealed test: an independent test of the frozen filter

_Written 2026-09-30 ~16:50 ET, **before** any flow from this period was downloaded or looked at._
_Wording edited 2026-10-21 to match the app's names; rules, numbers and verdicts unchanged._

## Why
The two-year cache (practice year, sealed test, recent months) left the edge "not proven": the sealed test's 95% range
touches zero, and the recent months were negative. On 2026-09-30, UW said my API key can reach back to **2023-10-31** (a rolling 730 trading
days). The frozen filter has never seen that year, so running it once there is a genuine new test.

## Fixed in advance
- **Period:** 2023-10-31 → 2024-09-27, the sessions before the practice year, with five-day outcomes.
- **Filter:** the frozen WhaleProof filter, `FilterConfig` hash `84ef5cdce1cbe4e1`. No change of any kind.
- **Data:**
  - UW flow alerts ≥ $100K for each session;
  - daily bars (cached, or fetched for tickers not yet cached);
  - realized-vol history for long-shot candidates;
  - earnings from the cached `/earnings/{t}` payloads.
  - Same code as all other periods: `scripts/desk_build_rows.py` → `whaleproof evidence --preperiod`.
- **Known limitation, stated in advance:** IV rank history only reaches back 1 year. Where a ticker has no
  realized-vol history, the option-value check is "unknown", so that alert cannot be a long shot. This can only
  shrink the long-shot list, never add to it.
- **Primary metric:** signals' five-day return in the signal direction minus the S&P 500 (SPY; `x5`), entry at the next open,
  0.10% cost. Reported per trade and per day, with a 5-day block-bootstrap 95% range.
- **Comparison:** all one-way alerts in the same period.
- **Verdict rule:** "supports the edge" only if **both** hold:
  1. signals' per-trade mean beats all one-way alerts;
  2. the per-day 95% range lies entirely above 0.

  Otherwise the verdict is "does not support". Reported whatever it shows.
- **Runs once.** `whaleproof evidence --preperiod` refuses a second run.

## Result (run once, 2026-09-30 19:35 ET) → `journal/desk-preperiod.json`
**Verdict: does not support the edge.** Signals beat all one-way alerts, but the 95% range is wide and includes 0.

| Second sealed test 2023-10-31 → 2024-09-27 (229 sessions) | Trades | Per trade vs S&P 500 | Median | Per day (95% range) | Win |
|---|---|---|---|---|---|
| All one-way alerts | 61,833 | −0.07% | −0.10% | −0.06% (−0.12 … −0.01) | 49% |
| Clean opening buys | 10,888 | −0.04% | −0.10% | −0.04% (−0.20 … +0.11) | 47% |
| **Signals (all whale-size bets)** | **63** | **+0.59%** | +0.18% | +0.83% (**−2.12 … +3.09**) | 51% |

Why so few signals (0.3 a day, vs 2–4 in later periods):
- **Long shots were untestable.** UW's older alerts carry no implied volatility, and my IV-rank history starts in
  Sep 2024. The "option not rich" check was therefore "unknown" for all 253 long-shot candidates.
- The limitation was declared in advance, but it proved total rather than partial. The pre-registration text blamed
  missing realized-vol history; the actual cause is missing alert IV plus IV rank.
- So this test covers **whale-size bets only**: ≥ $1M on a strike > 5% OTM.

**Reading.** Whale-size bets are small and positive in every period, and significant in none:

| Period | Trades | Per trade |
|---|---|---|
| Second sealed test | 63 | +0.59% |
| Practice year | 106 | +0.39% |
| Sealed test | 153 | +0.59% |

Long shots carried most of the practice-year and sealed-test edge (+1.46% and +1.70% per trade) and are unconfirmed
outside those periods.

**Status.** Across four periods the filter never lost to blind alerts in the practice year or either sealed test, but
it did in the recent months. The edge is **not proven**, and this test does not change that.

A possible follow-up would be a *new* pre-registered test: backfill IV rank for 2023–24 (~250 calls), then test
long shots there once. It is not done, and it must be written down before any data is fetched.

**Correction (2026-09-30 ~20:00 ET):** the long-shot gap was not caused by "older alerts carry no IV". No period in my
cache has alert IV; practice-year and sealed-test long-shot values also came from the IV-rank fallback. The only gap
was that my IV-rank cache started 2024-09-26. The follow-up test is pre-registered in `docs/PREPERIOD-FAROTM-TEST.md`.
