# UW API endpoint review — what else could raise pick quality?

_2026-09-27, from UW's OpenAPI spec (~237 paths). No API calls made. History depth on our Basic plan is **unverified**
for every endpoint below — see probe plan. Nothing here is proven; each item becomes a weight-0 check that the
train fit + holdout decide (docs/preregistration.md)._

## Already used
flow-alerts, gex-levels, darkpool (+price-levels), iv-rank, market-tide, net-prem-ticks, sector-tide, insider
ticker-flow, option-contract historic (OI), ohlc, earnings, unusualness (live-only), stock info, option-activity/unusual.

## Ranking rule
1. **Backtestable** (`date` param + history reaching 2024-10) — otherwise it can't be proven, only watched live.
2. **Evidence outside UW** that the signal predicts returns.
3. **Backfill cost.** Per-ticker-per-day endpoints ≈ 40 cands × ~500 days ≈ **20K calls** (half a day's budget).
   Daily market-wide lists ≈ **500**. Per-ticker endpoints that return full history ≈ **1 call per ticker** (~1–2K).

## Tier A — test first
| endpoint | what it gives | why it might help | est. 2y cost |
|---|---|---|---|
| `/stock/{t}/historical-risk-reversal-skew` (date, expiry, timeframe, delta 25/10) | put − call IV at 25Δ | Steep put skew predicts underperformance (Xing-Zhang-Zhao 2010) — a published, replicated option-implied signal. Check: skew level/change aligned with our direction | ~1 call/ticker if `timeframe` returns history |
| `/stock/{t}/volatility/option-sentiment` + `/volatility/option-sentiment/top` (date) | VWKS (where volume sits vs spot) + AVAR (call vs put IV asymmetry) → bullish/bearish score | Whole-chain positioning, not one print — confirms or contradicts the whale. `/top` also works as a candidate source | top: ~500 (1/day); per-ticker: history included? |
| `/stock/{t}/options-pulse` + `/options-pulse/top` (date) | Nasdaq opening-**buy** call/put transaction counts → sentiment | Opening buys are what we try to infer from flow; this is exchange-reported. Directly on-thesis | top: ~500 |
| `/stock/{t}/volatility/variance-risk-premium`, `/volatility/realized`, `/volatility/stats` (date) | IV vs realized vol | IV−RV spread predicts returns (Bali-Hovakimian 2009) and decides **structure**: rich IV → spread, cheap → long option. Improves option P&L even without direction | ~1 call/ticker (history) |
| `/screener/analysts` (ticker, action, newer_than/older_than) | upgrades/downgrades with timestamps | Post-revision drift is well documented. Catalyst check: whale + same-direction upgrade | small (paged by time) |
| `/shorts/{t}/interest-float/v2`, `/shorts/{t}/volume-and-ratio`, `/shorts/{t}/ftds` | short interest (FINRA, lagged), daily short-volume ratio, FTDs | High short interest predicts lower returns (Asquith-Pathak-Ritter; Rapach et al.); also squeeze fuel for bullish calls. **Must use FINRA publish date**, not settlement date | ~1 call/ticker each |

## Tier B — cheap daily context / risk filters
| endpoint | use |
|---|---|
| `/market/top-net-impact` (date) | Daily tickers driving market tide; 1 call/day. Feature: candidate is a top net-impact name in its direction |
| `/market/economic-calendar`, `/market/fda-calendar` | **Risk filters**: skip/size-down before FOMC/CPI/NFP; biotech PDUFA = binary. Cuts losses, doesn't predict direction |
| `/etfs/{t}/in-outflow` (3y per call) | Sector-ETF fund flows → sector check alternative to sector tide. ~11 calls for all history |
| `/stock/{t}/greek-exposure` (date, timeframe) | Daily GEX history: negative gamma → bigger moves, positive → pinning. Regime feature; may be cheap if timeframe returns history |
| `/stock/{t}/max-pain` (last 120 days) | Pin risk near expiry for short-DTE picks. Weak evidence |
| `/net-flow/expiry` (date) | Market net premium by moneyness/expiry (0DTE vs longer). Regime context |

## Tier C — live-only or low value (skip for now)
- `/volatility/anomaly/top`, `/volatility/character/top`: history only **3–4 weeks** → cannot backtest. Could show live.
- `/stock/{t}/option-stance`: descriptive contract picker (fit_score). Useful in Plan 2b/3 for choosing the contract,
  not for picking direction.
- `/stock/{t}/nope`: per-minute; research mostly on SPY. `/group-flow/*/greek-flow`: per-minute, heavy.
- Institutions (13F lag ~45 days), congress (disclosure lag up to 45 days; `unusual-trades` 422 on Basic), politicians,
  seasonality (weak), predictions/crypto/futures/FX/private markets (off-thesis).
- `/analytics/*`: **Advanced+ tier only**. Websockets: plan access unverified; not needed for daily picks.

## Probe plan (needs owner OK — ~45 calls)
For each Tier A/B endpoint: one call for a recent date and one for **2024-10-25** on one liquid ticker (NVDA), recording
status, row count, oldest date returned, whether history comes back in one call, and field names — appended to
`docs/endpoint-matrix.md` (derived metadata only, no raw data committed). Best run after Monday's 17:00 track
(spare ≈ 1.1K) or right after the 20:00 reset.
- Screeners with date fallback (`option-sentiment/top`, `options-pulse/top`): record each row's returned date; a row
  dated ≠ D means **no history** for D, not a hit.
- Also (~15 calls): `uw_flagged` coverage — screener `option-contracts` `unusual=true` + `page` vs sector slices vs
  cached list on one uncapped day (pre-registration Amendment 1).

## Recommendation
Probe Tier A first. Build weight-0 checks for those that are backtestable and cheap (full history in 1 call/ticker):
**risk-reversal skew, option-sentiment, VRP/IV-RV, short interest**, plus the **economic-calendar risk filter**.
Add them to the pre-registration as H9+ **before** the holdout is run.
