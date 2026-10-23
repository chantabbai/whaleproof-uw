# Pre-registration — full 2-year backtest & redesign

_Written 2026-09-27 22:30 ET, **before** the full backfill finished and before any result on the windows below was seen.
Committed to local git for internal discipline (local commits can be rewritten, so this is not external proof). Any change after the holdout is run makes that result **exploratory**._

## Why
The partial backtest (Jul–Sep 2026) showed no edge and several surprises (SKIP beat GO, "support" checks looked
contrarian). With ~20 variants to try, testing them all and reporting the best would be cherry-picking. This file fixes
the questions, splits, metrics and pass rules in advance.

## Data windows
| window | dates | role |
|---|---|---|
| **Train** | 2024-10-01 → 2025-09-30 (~250 sessions) | fit weights, choose stop/target widths, pick signs. Look as much as needed. |
| **Holdout** | 2025-10-01 → 2026-05-29 (~165 sessions) | **run once**, after every choice is frozen. Pass/fail is decided here. |
| **Seen** | 2026-06-01 → latest backfilled session | already looked at (partial backtest, UW-unusual study). Reported, labelled "seen", **not** used for pass/fail. |
| **Forward** | 2026-09-28 → 2026-10-20 live journal picks | true out-of-sample; reported whatever it shows. |

## Common rules
- Point-in-time: candidates and checks use data known at D close + 15 min; entry = next session open.
- **Primary metric:** 5-session return in the trade's direction minus SPY's (`x5`), net 5 bps per side.
- **Unit = day.** Same-day picks are correlated → day-clustered bootstrap (resample days), 95% CI, two-sided p.
- **Multiple testing:** Holm correction at α = 0.05 across the primary hypotheses H1–H8.
- **"Tradeable"** requires all of: Holm-adjusted holdout p < 0.05; same sign on train; effect ≥ +0.20% per 5 days
  (≥ 2× round-trip cost); ≥ 60 holdout days with data. Everything else is "not proven" — including positive-looking ones.
- Secondary (reported, not pass/fail): hit rate, plan-exit return, follow-the-money return, drawdown, per-year split.

## Primary hypotheses
| # | Question | Test on holdout | Pass direction |
|---|---|---|---|
| H1 | Does v0.5 official-like top-5/day beat SPY? | mean daily `x5` of top-5 by `score_parity` | > 0 |
| H2 | Does a train-fitted v1 beat v0.5? | paired daily diff: v1 top-5 − v0.5 top-5 | > 0 |
| H3 | Does `uw_flagged` help? (definition below) | paired daily diff: flagged − unflagged candidates | ≠ 0 (follow if > 0, **fade** if < 0) |
| H4 | Fade the crowd: is SKIP better than GO? | paired daily diff: SKIP − GO (v0.5) | > 0 ⇒ invert-signal variant is valid |
| H5 | Are "support" checks contrarian? (`dark_pool`, `dp_blocks`, `ticker_flow`, `sector_flow`) | per check: top vs bottom tercile of check score, paired daily diff, sign chosen on train | same sign as train |
| H6 | Wider stops/targets? | plan-exit return with (stop, target) chosen on train from grid stop ∈ {0.75, 1.0, 1.5}×EM, target ∈ {1.25, 2.0}×EM vs current (0.75, 1.25) | > 0 |
| H7 | Follow-the-money exit vs plan exit? | paired per-trade diff, day-clustered | > 0 |
| H8 | OI-confirmed picks better? (`oi_ratio ≥ 0.5`) | paired daily diff: confirmed − not | > 0 |

### H3 definition (fixed now)
- **Flag = exact contract match**: the candidate's `option_chain` is in UW `/api/option-activity/unusual` for session D
  with premium ≥ $250K. Ticker+direction matching was rejected: it flags 77% of candidates and cannot discriminate.
- Fetch: 11 sector slices + 1 ETF slice per day, `limit=500`. If any slice returns 500 rows the day is **incomplete**:
  flagged contracts still count, but "not flagged" is treated as unknown (check unavailable).
- Minimum: ≥ 300 flagged candidates and ≥ 60 days on holdout, else H3 = "insufficient data".
- Also reported: complete-days-only result, and ≥ $1M-premium flags.

## Frozen before the holdout run
- v1 fit: L2 logistic on train, **signs allowed to flip** (current `fit.py` clips coef ≥ 0 — must change before H2),
  features = backtestable checks incl. `uw_flagged`.
- H5/H6 choices from train only. Candidate prefilter (top 40/day) and 5 bps cost unchanged.

## Exploratory results already seen (NOT evidence — disclosed so the holdout can be judged fairly)
UW-unusual study, 2026-06-01 → 09-17 (seen window):
- UW-unusual list alone, as a trade signal: hit 49.1%, −0.12% vs SPY → no edge. List truncated to top-500 by volume on
  58/76 days (docs/uw-unusual-study.md).
- Our candidates, flagged vs unflagged (391 vs 2,648): `x5` +0.39% vs −0.02%; paired daily diff +0.41%
  (CI −0.47% to +1.29%) → not significant. Complete (untruncated) days only: flagged +1.57% (15 days, n = 62) — too small.
- Partial backtest Jul–Sep 2026: see docs/backtest-report.md (GO −0.19% vs SPY, SKIP +1.05%).

## Amendment 1 — 2026-09-27 23:00 ET (before any 2y uw_unusual data fetched)
- H3 "≥ 60 days" means **complete** days (list not truncated). Fewer complete days → H3 = "insufficient data".
- **Coverage precondition:** sector + ETF slices may miss tickers with no sector / other issue types, so "complete"
  could be wrong. Preferred fetch: `/api/screener/option-contracts?unusual=true&date=D&min_premium=250000` with `page`
  (spec lists `page`; unusual endpoint = this screener + preset). Probe must show: (a) paging returns distinct rows until
  exhausted, (b) union for one of the 18 uncapped cached days equals the cached unusual list. If neither paging nor slices
  reproduce the cached list, H3 is dropped.
- **Point-in-time precondition:** the preset uses volume > OI; a list fetched later for day D may differ from what was
  visible at D 16:30. Fetch D's list live at the scan and again next day (distinct cache key) and compare. Material
  difference → backtest H3 uses only live-captured lists or is reported as "not point-in-time".

## Amendment 2 — 2026-09-28 00:00 ET (before any data for these checks fetched)
- **H9 (one family, Holm counts it once per check):** `skew`, `option_sentiment`, `iv_rv`, `macro_event` — each weight 0,
  test = top vs bottom tercile (macro_event: event vs none) paired daily diff of `x5` on holdout, sign fixed on train.
  `option_sentiment` only if the probe shows point-in-time history; otherwise dropped (not backtestable).
- **Owner goal restated:** maximise the number of profitable trades (positive expectancy), not win rate. Primary metric
  stays mean `x5` per trade (= expectancy); add **profit factor** and **trades/day** to every headline table. A variant that
  keeps expectancy while adding trades beats one that raises hit rate on fewer trades.
- **Feature freeze:** no new checks/endpoints before the holdout run. Existing 20 checks are the full candidate set.

## Amendment 3 — 2026-09-28 00:30 ET: pure-directional gate + setups (before 2y data)
Owner: lift the 5-picks/day cap in research (live stays 5/day until a setup is proven); find pure directional plays;
different setups may carry different probabilities. Simple rules first, weighted score second.

**Gate — "pure directional buy"** (all must hold; otherwise the alert is *noise* and only kept as a control group):
1. Buying: ask-side premium ≥ 70% (bid-side "sold call/put" is not directional — covered calls, CSPs, closings).
2. Single leg; not a floor/cross trade.
3. Opening: all-opening trades, or volume > OI, or size > OI.
4. Moneyness: −5% (slightly ITM) to +15% OTM — excludes deep ITM (stock replacement / dividend capture) and lottos.
5. DTE 7–90.
6. Common Stock / ADR / ETF, but **no ETF puts** (mostly hedges).
7. No same-day opposite-type buying on the ticker (call and put both ask-side ≥ 70%, other premium ≥ 50% of this one,
   known by as_of) → volatility bet, not direction.
8. No same-kind bid-side print within 1 second (likely spread leg printed separately).

**Setups** (mutually exclusive, first match wins; gate passers only):
`pre_earnings` (earnings within the next 7 calendar days) → `whale_sweep` (sweep, premium ≥ $1M) →
`repeat_buyer` (≥ 2 other same-direction alerts in last 3 sessions) → `sweep` → `clean_other`.

**Report per setup and for noise:** n, trades/day, 5d win rate, mean `x5`, profit factor, day-clustered CI.
**H10:** gate passers beat noise (paired daily diff of `x5`) on holdout. Each setup's stats are its displayed
probability only if it passes the "tradeable" rule; otherwise shown as "not proven".
Known limitation: backtest sees only the top-40-by-premium candidates per day (what was backfilled).

## Amendment 4 — 2026-09-28 01:30 ET: definition fixes + primary engine (before any train/holdout run)
Corrections that follow from the rules' own logic, not from returns:
- **Vol play** = opposite-type ask-side buy, ≥ 50% of our premium, **same expiry, within 15 minutes**. The old any-expiry,
  any-time rule removed ordinary two-sided flow in busy names (only 11.5% of its cuts met the straddle/strangle shape).
- **repeat_buyer** counts only other **gate-passing buys** in the same direction (last 3 sessions, known by as_of). The old
  count included sold premium and closing prints — contradicting "not all ask/bid prints are directional buys".
- **Primary engine:** the simple-rules backtest (`backtest --simple`, all gate passers) decides H10 and setup "tradeable"
  status. The check-based backtest (top-40 pool) is secondary, for the weighted-score hypotheses (H1–H3, H5, H9).
- Live official picks stay **5/day** until a setup passes on holdout.

## Amendment 5 — 2026-09-28 02:00 ET: far-OTM setup + live pure-buys track (before any train/holdout run)
- Source: Pan & Poteshman (2006, RFS) — opening-buy option volume predicts next-week returns; **deep OTM** options carried
  the most information. Decided from the paper, not from our data.
- Gate moneyness widened to −5% … **+30%** OTM. New setup **`far_otm`** (+15% … +30% OTM), placed second:
  `pre_earnings` → `far_otm` → `whale_sweep` → `repeat_buyer` → `sweep` → `clean_other`.
- Considered and **dropped**: ticker-level opening-buy put:call ranking. We only see ≥$100K alerts (not all opening volume);
  most tickers have one alert per day, so it would duplicate the pure-buys list. No new information.
- **Live forward track "pure"**: every gate passer at the 16:30 scan → separate hash-chained `journal/pure.jsonl`
  (official journal untouched). Outcome = next open → close of 5th session (same as `r5`). Reconstructed days (written
  after the entry open) are flagged and excluded from forward stats.

## Amendment 6 — 2026-09-28 03:00 ET: next-morning OI confirmation for pure buys (forward track only)
- 08:30 ET each pure buy entering today gets the same check as official picks: (OI on D+1 − OI on D) / size →
  confirmed (≥ 0.5) / unconfirmed / closed / unavailable, appended pre-open to `journal/pure.jsonl`.
- Forward scorecard reports stats by confirmation status. **H8 extension:** confirmed pure buys beat unconfirmed
  (paired daily diff, forward + backtest where contract OI exists). Measured only; entry rule unchanged until proven.

## Correction — timestamps (appended 2026-09-27 23:17 ET)
The clock times in the headers of Amendments 1–6 were estimated and are wrong (they read 22:30–03:00 ET on 09-28).
All were actually written on **2026-09-27 between ~22:00 and 23:10 ET**. The authoritative times are the git commit
timestamps (`git log docs/preregistration.md`). Order and content are unchanged, and every amendment still predates
any train/holdout run.

## Amendment 7 — 2026-09-28 17:27 ET: analysis mechanics (before any train/holdout run; history backfill still incomplete)
Fixes choices the rules above left open, so the analysis is one command (`whaleproof analyze --phase train|holdout`).
No train or holdout result has been computed.

**Test family (Holm, α = 0.05).** Every member counts separately (stricter than one test per H):
H1 · H2 · H3 · H4 · H5 × {dark_pool, dp_blocks, ticker_flow, sector_flow} · H6 (only if train picks a cell other than
the current one; otherwise "no change chosen", not a member) · H7 · H8 · H9 × {skew, iv_rv, macro_event, option_sentiment
— the last only if point-in-time history exists, see Amendment 2} · H10 · S × each setup in `SETUPS` (one-sample: mean
daily `x5` > 0 — needed for a setup's "tradeable" status). There is no H11. A member with too little data
(< 60 days, or H3's minimums) stays in the family with p = 1 and is reported "insufficient data".

**Populations.** H1/H2: top 5 GO per day by `score_parity` (v0.5 / v1). H4, H5, H6, H7, H8, H9: the top-40 candidate pool
(v0.5 labels). H10 and S: simple backtest (all gate passers; noise = gate failures).

**Statistics.** Unit = day. One-sample tests use the daily mean; paired tests use days where both sides have data and
the daily difference of means (H7: daily mean of per-trade differences). Bootstrap: 10,000 resamples of days, fixed
seed 42. p (two-sided) = share of null-centred bootstrap means (daily values minus their mean) at least as far from 0
as the observed mean, floored at 1/(B+1). CI = 2.5/97.5 percentiles of the uncentred bootstrap.

**Train-phase choices (frozen to `journal/analysis-freeze.json` with this file's SHA-256):**
- v1 fit: L2 logistic (C = 0.5) on train rows only, label `x5 > 0` (the primary metric), features = backtestable checks
  of v0.5, **signs allowed**; weights = coef scaled so Σ|w| equals v0.5's backtestable budget. Scoring with signed weights
  divides by Σ|w| of available checks (identical to today for positive weights). The clip-at-0 fit is kept as a flag and
  reported on train for comparison only. No holdout rows are scored during the train phase.
- H3 direction, H5/H9 signs: sign of the train effect (follow if > 0, fade if < 0); holdout effect is oriented by it.
- H5/H9 terciles: cutoffs = train 33rd/67th percentiles of the check score (available rows). Top = score ≥ upper cut,
  bottom = score ≤ lower cut; if the cuts are equal (binary / mostly-zero checks), top = score > cut, bottom = score ≤ cut.
- H6: plan exits with fixed levels, stop k_s × EM and target k_t × EM (EM = the plan's holding-period expected move,
  same time stop as live), grid k_s ∈ {0.75, 1.0, 1.5}, k_t ∈ {1.25, 2.0}; choice = best mean daily return on train.
  Test = chosen cell − (0.75, 1.25) cell, paired daily. The wall-based plan is not the baseline.

**Holdout guard.** The holdout phase refuses unless: the freeze file exists; this file's hash equals the frozen hash (any
later edit ⇒ re-run train and re-freeze first); every holdout session is backfilled and the price fill is complete.
The train phase always writes its report but only freezes on complete train data. It then writes a run marker **before** computing; a second run is refused. If it crashes before printing any
result the owner may delete the marker by hand — this is logged in SESSION_LOG.

**"Tradeable"** (unchanged): Holm-adjusted holdout p < 0.05, same sign on train, effect ≥ +0.20% per 5 days in the pass
direction, ≥ 60 holdout days.

## Amendment 8 — 2026-09-28 17:48 ET: two Holm families + enrich inputs (before any train/holdout run)
Owner delegated the choice ("choose whatever is best to find the best trades"). No train/holdout result has been seen.
- **Holm families.** Family **A** = what we trade: the 6 setups (S.*) + H10 — the primary engine (Amendment 4).
  Family **B** = the weighted-score hypotheses (H1–H9 members). Holm at α = 0.05 within each family. Reason: one
  22-member family made the setup tests compete with 15 unrelated score questions (smallest threshold ≈ 0.0023); per-
  question families are the usual convention and still control false positives inside what we would trade.
- **H3 fetch** (Amendment 1 precondition met by the 2026-09-28 probe: paging and slices both reproduced the cached list,
  390/390): unusual screener with `page`, complete only if paging ends on a short page. The point-in-time caveat of
  Amendment 1 remains: lists fetched later may differ from what was visible at D 16:30 → H3 is reported with that label.
- **H9 inputs:** iv_rv from `/volatility/realized` (3y history, one call per ticker). skew (`rr_skew` ≈ 2 weeks of history)
  and macro_event (`economic-calendar` has no past dates) are **not backtestable** → stay in family B at p = 1.
  option_sentiment: not backtestable (no parser/history) → same.
- The holdout guard also requires these inputs fetched for every holdout session.

## Amendment 9 — 2026-09-28 18:10 ET: gated official picks (v0.6), put-sale setup, premium buckets (before any train/holdout run)
- **Live official picks v0.6** = v0.5 weights, but candidates must pass the pure-directional gate *before* the
  biggest-per-(ticker, direction) pick and the top-40 cut (live scan + intraday). Reason: the v0.5 pool was 55% sold premium; e.g. a 100% bid-side 2-DTE put became a
  "long call" pick. v0.5 picks already journaled stay as they are. Official-like backtest for v0.6: `backtest --gate`.
- **`put_sale` setup (research, simple backtest only):** fails the gate *only* because it is not a buy, and is a
  bid-side (≥ 70%) opening put, 7–90 DTE, 0 … +15% OTM → bullish. Reported separately; **not** part of `pure_all`,
  not traded live. Natural trade structure if it ever passes: bull put spread (not a long call).
- **Premium:** no new cutoff. Buckets fixed now: $100K–250K, $250K–1M, $1M–5M, >$5M (existing breakdown). Any
  cutoff is chosen on train only and confirmed on holdout.
- **Hypotheses unchanged.** H1/H2/H4 stay on the ungated v0.5 check engine as pre-registered; `backtest --gate` is
  descriptive only (no new hypothesis). put_sale is **not** in Holm family A (not in `SETUPS`). H10's noise group =
  gate failures that are not put_sale.

## Amendment 10 — 2026-09-28 19:04 ET: one pick per ticker per day (before any train/holdout run)
Owner: "one pick per ticker per day, pick the one with most edge".
- **Live official (v0.6) and intraday:** at most one pick per ticker per session. Among a ticker's GO candidates the
  highest `score_parity` wins (the only pre-holdout edge estimate); the other direction/contract is dropped. Intraday
  skips a ticker that already has an intraday pick that session. Past journal records unchanged.
- **Backtest:** the descriptive "official-like top 5" (`top_n_per_day`) mirrors this rule. **H1/H2 are unchanged** (as
  pre-registered on the ungated v0.5 top-5; no new hypothesis).

## Amendment 11 — 2026-09-28 20:48 ET: strategy combinations + risk-first ranking (before any train/holdout result)
Owner: evaluate strategies alone and combined, find the best odds; goal = "make money with little risk without blowing
out the account". Written before the train analysis has produced any result.
- **Building blocks** (simple backtest rows; gate passers only): setup (each of `SETUPS`), next-morning OI confirmed
  (ratio ≥ 0.5), option cheap / not rich (value view), days to expiry ≤ 30 / 31–90, whale premium ≥ $1M, direction
  long / short, SPY above / below its 50-day average, OTM 0–5% vs > 5%.
- **Search on TRAIN only:** every single block, every pair, and triples of blocks from different families. A combination
  needs ≥ 100 trades and ≥ 60 days, else it is not ranked.
- **Measures per combination:** trades/day, win rate, mean `x5` (vs market), profit factor, day-clustered 95% range;
  **risk:** max drawdown and worst day of the daily-cohort equity (1/5 capital per day), longest run of losing days.
  **Shrunk mean** = mean × n_days / (n_days + 60) so thin groups are pulled toward zero.
- **Stability:** train split into two halves by date (2024-10-01 → 2025-03-31, 2025-04-01 → 2025-09-30); a combination
  must have positive mean `x5` in **both** halves.
- **Ranking (risk first):** among stable combinations, rank by shrunk mean ÷ |max drawdown| (return per unit of the worst
  fall); ties → more trades/day. Simplest (fewest blocks) wins when within 10% of the best.
- **Finalists:** at most 3, written into a dated amendment **before** the holdout run. On holdout they form **family C**
  (Holm across the finalists only) and use the same "tradeable" rule. Families A and B unchanged.
- **Live use:** only a finalist that is tradeable on holdout may change live picks; sizing = fixed $ risk per trade.

## Amendment 12 — 2026-09-28 21:37 ET: finalists (after the train review, BEFORE any holdout data is opened)
Owner confirmed three finalists from the train Strategy lab (Amendment 11). Holdout has not been run.
- **F1** = OI confirmed + 31–90 days to expiry + over 5% OTM. (Live ordering only: bigger whale premium first.)
- **F2** = option cheap + long only.
- **F3** = setup: far OTM + option not rich + long only.
Block definitions exactly as in `core/backtest/combos.py` (`BLOCKS`) at this commit. On holdout each finalist is a
one-sample test of mean daily `x5` > 0 on the simple-backtest rows it matches (gate passers only), **family C** = Holm
across F1–F3, same "tradeable" rule. **Benchmark:** from now on any new idea is judged against the finalists; ideas added
after the holdout run are exploratory and can only be confirmed on the live forward record.

## Amendment 13 — 2026-09-29 12:30 ET: official picks hold overnight (day-1 rule), train-only comparison
Owner: WhaleProof is for swing traders — hold at least one night; a same-day exit is fine only when something breaks.
Today the official plan checks the stop and target from the entry day's own high/low (e.g. GLD 09-28 stopped out day 1).
The finalists / simple backtest (fixed 5-session hold, no stops) and intraday picks (exits from the next session) are
unchanged. Written before any run of the variant; holdout is not touched.
- **Variant "overnight":** on the entry day, the target and the normal stop are **not** checked. Only an **emergency stop**
  applies: level = entry_ref − 2 × direction × |entry_ref − invalidation| (twice the planned stop distance from the
  plan's reference price; entry open if entry_ref is missing); fill = that level, or the open if it gaps through.
  From day 2 on: the normal plan rules (stop first, gap-through fills at the open; then target; then time stop).
- **Comparison (TRAIN only, 2024-10-01 → 2025-09-30):** `backtest --gate` (v0.6 weights), official-like top-5 GO per day,
  current rule vs overnight on the same rows. Reported: approx. portfolio max drawdown (1/5 capital per daily cohort),
  total, mean and median plan return per trade, worst single trade, share of day-1 exits.
- **Decision rule:** smaller portfolio max drawdown wins; if the two are within 0.5 percentage points, the higher mean
  plan return per trade wins; if that is also within 0.05 pp, keep the current rule (no change without a reason).
- **If "overnight" wins:** it becomes the live official exit rule (tracker + scorecard) for new picks from the next
  16:30 scan; past journal records are not rewritten. The result and the choice are appended as a dated note.

## Amendment 14 — 2026-09-29 15:45 ET: liquidity rule at the 9:45 after-open check (live only)
Owner approved. Found live on 09-29: some of our suggested contracts are thin (COHR Nov 280C bid/ask 35.9/40.7, 12.5% of
mid; ADI 17%), so buying at the ask and selling at the bid loses that much before the stock moves.
- **Rule:** at the 9:45 ET after-open check, if our contract's (ask − bid) ÷ mid > **10%**, or it has no two-sided quote,
  the decision is **"skip: wide spread"** (not bought). Order: past the stop → already moved → price ran → wide spread →
  still a buy. Applies to every live fill (official, pure, finalists) from the next entry day (09-30).
- **Not backtestable** for our contract (no historical quotes of it), so it changes nothing in train/holdout results or the
  finalists' tests. The forward record keeps each skipped pick's would-be result (dashboard "would be"), so the rule can
  be judged on live data: skipped-for-spread vs bought, same exit rules. No other threshold will be tried before that.

## Amendment 14a — 2026-09-29 16:05 ET: "no two-sided quote" is NOT a skip (before any 09-30 data)
Checked on 09-29's 9:45 capture: 24 of 79 bought contracts had no bid/ask, and every one had 0 volume that day —
including liquid names (XOM, VOO, HD, ORCL, open interest up to ~2K). UW's per-expiry chain appears to omit the quote for
contracts not yet traded that day, so a missing quote is not evidence of a thin contract. **Change:** only a measured
(ask − bid) ÷ mid > 10% skips; a missing quote keeps the other checks' decision and is flagged "no quote at 9:45".
Everything else in Amendment 14 unchanged.

## Correction — timestamps of Amendments 13, 14, 14a (appended 2026-09-29 15:41 ET)
The headings' times were estimates. Git commit times are authoritative: Amendment 13 committed 15:33 ET (before the
day-1 backtest was started), Amendment 14 at 15:38 ET, Amendment 14a at 15:40 ET — all on 2026-09-29, before the 09-30
9:45 capture they affect. Content unchanged.

## Result — Amendment 13 (appended 2026-09-29 ~15:50 ET): keep the current day-1 rule
Train, `backtest --gate` v0.6, official-like top 5 (1,249 trades, 250 days) — docs/backtest-day1-train.md:
current rule mean −0.05%, max drawdown −16.1%, sold on day 1 17%; hold overnight mean −0.17%, max drawdown −23.6%,
day 1 4%. Smaller drawdown wins → **current rule stays** for official picks. Finalists (fixed 5-session hold) unaffected.
(Timestamp note: the "Result — Amendment 13" entry above was committed 15:44 ET, not ~15:50.)

## Amendment 15 — 2026-09-29 17:00 ET: complete F1's open-interest data (before the holdout run)
Found in review: F1's "OI confirmed" block needs the whale contract's open interest on D and D+1, which was fetched only
for top-40 candidates and the F2/F3 contract fetch. Train: 211 of 2,177 F1-shaped rows (31–90 DTE, > 5% OTM, gate
passers, not put sales) had it (10%), 96% of them confirmed; holdout 157 of 2,339 (7%). So F1 was scored on "rows we
happened to fetch", not on the live population (every pure buy is OI-checked). Counted from alert fields and OI presence
only — no returns looked at.
- **Fix:** fetch `/option-contract/{id}/historic` for every F1-shaped row missing OI on D or D+1, in train and holdout
  (~4.1K calls, hourly backfill, budget-limited, before the F2/F3 contract fill). F1's definition is unchanged
  (Amendment 12, `combos.BLOCKS`). Rows whose contract history UW does not return stay "unknown" (not confirmed).
- **Then:** re-run `analyze --phase train` (re-freeze). Corrected F1 train stats and trades/day are reported and replace
  the old ones on the dashboard. **Finalists stay F1–F3 — no re-selection.** If corrected F1 fails the Amendment 11
  stability rule (positive mean x5 in both train halves), F1 is dropped from family C and Holm runs over F2–F3 only.
- The holdout still runs once, only after this fill is complete and the owner says go.

## Amendment 16 — 2026-09-29 17:13 ET: position cap — the "Take" list (owner chose option A)
Owner: we cannot hold ~150 open trades. A sizing overlay picks what to actually trade; every trade is still recorded.
- **Source:** pure buys that match a finalist (F1–F3, Amendment 12 blocks). Official picks are not in the Take list
  (still "not proven"). After the holdout only finalists that pass stay in the source.
- **Per entry day, in order:** one per stock (biggest whale premium wins); rank by number of finalists matched (more
  first), then whale premium (bigger first). Each trade is counted against the first of its finalists (F1, F2, F3 order)
  with room: **≤ 3 new trades per finalist per day**; **≤ 10 taken trades open at once** (taken, entry < that day ≤
  planned exit). A trade the 9:45 check skips does not use a slot — the next in line takes it. Days before the 9:45 check
  existed (entry 09-28) use the list order only.
- **Record:** "taken" trades get their own scorecard line (5-session hold, same exits), beside all finalist trades. The cap
  numbers (3, 10) are fixed; they are a risk choice, not tuned on returns.

## Amendment 17 — 2026-09-29 18:56 ET: our contract must be a traded strike (live only, before any 09-30 data)
Found 09-29: the live chooser snapped our contract to the nearest *listed* strike, some with 0–5 open interest that
never traded all day (GKOS, VSXY OI 0; SNX OI 5; AGQ). With no quote, 14a made them "still a buy" on a contract nobody
trades. Owner said "fix dead strike" (18:55). Decided on contract structure only — no returns looked at.
- **Rule:** our contract = the listed strike (same expiry and call/put as the chooser's) with **open interest ≥ 100**
  nearest to the chooser's strike, **within 10% of the stock price** (ties → slightly in the money, as before).
  Missing OI counts as 0.
- **None qualifies:** the 9:45 check says **"skip: no liquid strike"** (advisory, like Amendment 14; a skip frees the Take
  slot, Amendment 16). Marks still record the stock price.
- **Lock:** once a trade has a 9:45 decision, its contract never changes (OI moves daily; re-snapping could swap it
  mid-trade). Trades without a decision keep the first contract their marks recorded.
- **Scope:** live tracking only (`marks`). Backtests, finalists, the Take list order and dashboard estimates are unchanged.
  Trades already open keep their recorded contracts (journal is append-only); applies to entries from 09-30.
- Numbers 100 and 10% are fixed liquidity choices, not tuned on returns.

## Amendment 18 — 2026-09-29 19:18 ET: cost comparison for the finalists (report only, before the holdout run)
Owner asked (19:15) to show how results change with trading cost, fixed before any holdout data is seen. No rules,
finalists, picks, tests or pass/fail thresholds change; this only adds a table. Decided without looking at any returns.
- **What:** for each finalist (F1–F3) and the Take list, in train and holdout, the real option results
  (`option_prices.real_option_return`, whale contract, 5-session hold) at three fill levels, all from the same daily rows:
  | Level | Buy | Sell |
  |---|---|---|
  | **Mid** (best case) | entry-day open | exit-day mid ((bid+ask)/2; else last trade) |
  | **Normal** (as now — the pre-registered one) | open + ½ spread | exit-day bid (else last − ½ spread) |
  | **Wide** (bad day) | open + ¾ spread | exit-day mid − ¾ spread (else last − ¾ spread) |
  Spread = entry-day closing (ask − bid) / mid, as now. Rows without quotes are "not measured" at every level, same rows.
- **Shown per level:** trades measured, win rate, average and median result, and worst 5-session result.
- **Practical rule (live use only, not the statistical test):** a finalist that passes the holdout (Holm, as registered)
  goes into the live Take list only if its **normal-level** holdout average is above 0 with ≥ 30 measured trades; fewer
  than 30 → "cost check unknown", paper only. Wide level is reported, never a gate.
- ¾ = 1.5 × the normal half spread (common "bad fill" stress). Fixed now, not tuned.
