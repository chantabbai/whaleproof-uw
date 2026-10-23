# Earnings: is the implied move cheap or rich compared with the stock's own past moves?

_Exploratory (the frozen signal filter is untouched). Script `backend/scripts/research/earnings_moves.py` →
`journal/research/earnings-moves.json`. Cache-only, 0 UW calls. Run 2026-10-04. The method and thresholds below were
fixed before any outcome was computed._

## Short answer
- **The options market usually prices a bigger move than happens.** Across 28,048 reports (2022 → Oct 2026), the
  stock's next-day move beat UW's implied move only **34%** of the time. The typical move was **0.68×** the implied move.
- **Cheap vs rich sorts the outcomes, every year.** When the implied move was *cheap* (below 0.8× the stock's own
  median past move), the real move beat it **51%** of the time. For *fair* it was 41%, and for *rich* (above 1.25×) 29%.
  The gap held in every year 2023–2026: +29, +16, +11 and +13 points. The 95% range for the whole period is +18.7 to
  +24.7 points. By the rule declared in advance, that **supports** the label as a description.
- **It's not a trade signal.** Even cheap reports beat the implied move only about **40%** of the time in 2025 and 2026,
  and the gap is shrinking. The straddle profit proxy for cheap reports fell from +3.0% (2022) to +0.1% (2026). No
  real option prices, fills or time value were tested, so buying cheap straddles or selling rich ones is **not proven**.

## Method (pre-declared)
- **Data:** UW `/api/earnings/{t}`, already cached for 2,137 tickers. **Implied move** = `expected_move_perc` (UW
  glossary: front-month at-the-money straddle × 0.85). **Actual move** = `post_earnings_move_1d`. For a postmarket
  report it is close(D+1)/close(D) − 1; for premarket, close(D)/close(D−1) − 1. Checked against my own daily bars:
  **99.99% of 18,998 reports agree within 0.5 points.**
- **Past move** = median |actual move| of the ticker's earlier reports (before the report date, within 3 years, last
  8, **at least 4**). It uses nothing from the report itself.
- **Label:** implied ÷ past < 0.8 → **cheap** · 0.8–1.25 → **fair** · > 1.25 → **rich**.
- **Outcomes:** *beat* = |actual| > implied (primary) · median |actual| ÷ implied · *edge* = |actual| − implied. Edge is
  a rough at-expiry straddle proxy: it ignores leftover time value, spreads and fills, and overstates a long straddle's loss.
- **Range:** 5-day moving-block bootstrap over report dates, 2,000 draws.
- **Verdict rule:** "supports" only if cheap beats more often than rich in every year 2023–2026 **and** the whole-period
  range excludes 0.

## Results

| label | reports | beat implied | typical move ÷ implied | edge (proxy) |
|---|---|---|---|---|
| all | 28,048 | 34.4% | 0.68 | see sensitivity |
| cheap | 2,450 | 51.1% | 1.04 | +1.45% |
| fair | 7,445 | 41.2% | 0.82 | −0.21% |
| rich | 18,153 | 29.4% | 0.60 | −2.24%* |

\* Rich edge after dropping junk implied values (see Sensitivity). As declared it is −64.9%, which is distorted by those values.

**Beat rate by year**

| year | cheap | fair | rich | cheap − rich |
|---|---|---|---|---|
| 2022 | 63.7% (394) | 42.9% (907) | 28.3% (3,477) | +35.4 |
| 2023 | 59.1% (707) | 42.3% (1,557) | 30.0% (3,503) | +29.1 |
| 2024 | 48.0% (498) | 43.9% (1,765) | 31.6% (3,865) | +16.4 |
| 2025 | 40.6% (471) | 39.5% (1,835) | 29.1% (4,095) | +11.4 |
| 2026 | 40.3% (380) | 37.6% (1,381) | 27.7% (3,213) | +12.6 |

2022 is shown but doesn't count toward the verdict. Its past moves lean on 2019–20 reports, because 2021 is almost empty in UW's history.

**Report time:** premarket 34.7% beat (13,441) · postmarket 35.3% (13,987) · unknown 8.7% (620). Unknown-time rows look
unreliable, so the page shows their time as unknown and doesn't guess.

## Sensitivity (not pre-declared)
221 reports have implied moves above 50%. These are junk values on illiquid names; the largest is 4,034, i.e. 403,400%.
Dropping them leaves beat rates almost unchanged: cheap − rich = +21.4 points, range +18.3 to +24.3, positive every
year. The mean edge becomes sane: all −1.4%, cheap +1.45%, fair −0.21%, rich −2.24%. The page shows the declared beat rates (almost identical); the cleaned
version only matters for the mean edge, which the page doesn't show.

## Caveats
- **Point-in-time is assumed for the implied move.** UW doesn't document when `expected_move_perc` is captured. The
  past-move side is strictly point-in-time.
- The implied move is a **front-month** straddle, so it includes days other than the report day. "Beat" is therefore a
  conservative bar, and part of why only 34% beat.
- Report dates are UW's final dates. A report that was rescheduled shows only its final date, which can make the history slightly look-ahead.
- Same-day reports cluster by sector and market, so 28K reports are not 28K independent bets.
- **Capture timing on the live page.** The test assumes the implied move was set just before the report. The page's
  implied move can be up to 5 sessions earlier, so the straddle covers more ordinary days and leans toward "rich". The
  label is most comparable on the last session before the report.
- **Part of the gap is mechanical.** Any noise in the implied move puts unusually low values in "cheap", where they
  are easier to beat, and unusually high ones in "rich". That inflates cheap − rich and is one more reason this is a
  description, not a trade.
- Large, steady moves partly explain "cheap": a stock that moved a lot in the past tends to move a lot again. The label
  measures that persistence; it doesn't time anything.

## Rerun the numbers
`cd backend && uv run python scripts/research/earnings_moves.py` (about 35 s, cache only).
