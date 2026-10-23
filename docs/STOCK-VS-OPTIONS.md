# Stock or options? How to trade a whale-flow signal

**Question.** When WhaleProof flags a bullish whale signal, should you buy the stock or copy the whale's option, and
does any option approach work better? This note answers that with two years of real Unusual Whales data. Every number
below can be rerun from the local cache: see [Rerun the numbers](#rerun-the-numbers).

**Answer.** Best way to act on a signal: the stock. Buying the whale's option lost money for the typical trade in every period I tested. That
held whether you entered early, took profits early, or held longer. On real prices, spreads and 60-day calls I picked myself
lost too, and selling puts was only about breakeven. The stock was the only approach that didn't lose on
the typical trade in both the practice year and the sealed test. It is still not proven: it lost in the recent months (Jun–Sep 2026).

## Why
- **The edge is small.** A filtered whale signal moved the stock about +1% against the S&P 500 over the next week, in the
  practice year and the sealed test.
- **Options cost more than that edge.**
  - The bid/ask spread on these contracts is often 5–15% of the option price.
  - Most whale contracts are short-dated and out of the money, so they lose value every day (time decay).
  - A +1% stock move doesn't cover those costs, so the typical option trade loses about 20–25% in 5 days.
- **Direction alone doesn't rescue the option.** When the stock moved the wrong way, the whale's call lost about 58%
  (median). When it moved the right way, the call gained a median of about +19% (practice year and sealed test), but about 1 in 3
  still lost to spread and time decay. In the recent months, right-way calls had a median of −1%. Exploratory:
  `scripts/research/options_when_right.py` → `journal/research/options-when-right.json`.
- **Most whale option bets lose even for the whale.** 58–75% expire worthless. A few huge winners carry the average.
- **Taking profit early raises the win rate but lowers the money.** With a +20% target you win 58–68% of trades.
  Losers still lose 50–100%, so the average per trade stays negative.

## Data and method
- **Data.**
  - UW flow alerts ≥ $100K: 1.77M alerts, 499 sessions, 2024-10-01 → 2026-09-29.
  - Cached daily stock bars.
  - Cached UW per-contract option history (`/api/option-contract/{id}/historic`: daily open/high/low/last, closing
    bid/ask, IV).
- **Signals.** Alerts that pass the frozen WhaleProof filter (see [`METHODOLOGY.md`](METHODOLOGY.md) and the How it works page):
  - clean opening call buys;
  - stock ≥ $5;
  - no earnings before the exit;
  - either a whale-size bet (≥ $1M, > 5% out of the money) or a long shot (> 15% out of the money at a fair option price).
- **Periods.** Practice year 2024-10-01 → 2025-09-30 · sealed test 2025-10-01 → 2026-05-29 · recent months 2026-06-01 → 2026-09-22.
- **Status.** The filter was frozen and its sealed test run **once** before any study below. These studies came after that,
  so they are **exploratory**: they describe results, they did not tune the filter.
- **Stock metric.** Five-day return in the signal's direction, entering at the next open, minus 0.10% costs. It is shown
  either as raw return or vs the S&P 500, as labelled.
- **Option fills (conservative unless stated).** Buy at the entry day's opening trade plus half the bid/ask gap. Sell at
  the exit day's closing bid. "Mid" = best case at mid prices. "Wide" = 1.5× the gap.

Table cells read **median / mean / win rate (trades)**. The median is the typical trade; the mean is what a basket of every
trade averaged.

## 1. Stock vs the whale's own option (five-day hold)
| | Practice year | Sealed test | Recent months |
|---|---|---|---|
| **Stock, vs S&P 500** | **+0.6% / +1.2% / 54% (488)** | **+0.5% / +1.4% / 53% (628)** | −2.0% / −1.5% / 41% (318) |
| Whale's option, mid fills (best case) | −16.7% / +5.3% / 39% (469) | −11.4% / +23.9% / 43% (597) | −32.6% / −11.9% / 29% (291) |
| Whale's option, normal fills | −25.0% / −4.6% / 36% (469) | −22.8% / +8.8% / 36% (597) | −47.3% / −27.1% / 20% (291) |
| Whale's option, wide fills | −29.5% / −9.0% / 34% (469) | −27.3% / +2.5% / 34% (597) | −52.0% / −33.1% / 18% (291) |

The option's sealed-test mean is positive (+8.8%) only because of a few very large winners. The typical trade lost 23%.

## 2. Taking profit early on the whale's option
A resting sell order at +X% fills if the option trades that high on a later day. Otherwise the trade exits at the end.
| Rule | Practice year | Sealed test | Recent months |
|---|---|---|---|
| Hold 5 days, no target | −25% / −5% / 36% | −23% / +9% / 36% | −47% / −27% / 20% |
| **Take profit +20%, max 5 days** | +20% / **−12%** / **58%** | +20% / **−10%** / **60%** | −27% / −27% / 42% |
| Take profit +30%, max 5 days | +25% / −10% / 53% | +30% / −8% / 55% | −35% / −25% / 38% |
| Take profit +20% with a −50% stop | +20% / −13% / 54% | +20% / −12% / 56% | −50% / −27% / 38% |
| **Take profit +20%, max 10 days** | +20% / **−10%** / **67%** | +20% / **−9%** / **68%** | +20% / −24% / 52% |
| Hold 10 days, no target | −38% / +20% / 36% | −39% / +19% / 35% | −55% / −35% / 21% |

A higher win rate did not mean more money. Every take-profit rule has a **negative average per trade**. The only rows
with a positive average are the ones that never take profit early: a few huge winners pay for many losers, and that
collapses in a bad stretch.

## 3. What happened to the whales' own trades, held to expiry
Each whale's price is taken as premium ÷ contracts, and the value at expiry comes from the stock's close. This covers
every clean opening buy that has already expired.
| | Trades | Expired worthless | Made money | Median | Mean | Mean without the best 1% | Best single trade |
|---|---|---|---|---|---|---|---|
| WhaleProof signals | 1,343 | 75% | 21% | −100% | +146% | **+15%** | +93,809% |
| Other clean call buys | 22,975 | 58% | 30% | −100% | +134% | **+0.5%** | +368,965% |
| Clean put buys | 16,438 | 60% | 28% | −100% | +60% | +2.6% | +39,044% |

Whales are not magic. Most of their option bets lose everything. Many are hedges, volatility bets, or one leg of a
bigger position, so the option can lose while the whale is fine overall. The flow is useful as **information about
where big money is betting**, not as a trade to copy. WhaleProof signals keep a positive edge even without the top 1%
(+15% vs +0.5% for other call buys).

## 4. Entry timing: does entering sooner help?
| Entry | Practice year | Sealed test | Recent months |
|---|---|---|---|
| Stock, next open (the tested rule) | +0.8% / 55% | +0.8% / 54% | −1.6% / 40% |
| Stock, at the alert's price | +1.5% / 57% | +1.0% / 55% | −1.5% / 41% |
| **Stock, same-day close** | **+1.2% / 57%** | **+1.0% / 55%** | −1.8% / 42% |
| Option, next open, hold 5 | −23.5% / 37% | −20.0% / 37% | −44.3% / 21% |
| Option, seconds after the whale (whale fill + half spread), hold 5 | −24.7% / 36% | −19.2% / 39% | −46.7% / 22% |
| Option, same-day close at the ask, hold 5 | −22.8% / 37% | −20.4% / 39% | −44.4% / 22% |
| Option, any of those entries, take profit +20% | mean −9% to −13%, win 57–62% | | |

Stock cells here are median / win rate. For "at the alert's price" the mean is unreliable: some alerts carry a pre-split
stock price while the bars are split-adjusted. Use the median.

Entering before the close adds about +0.2 to +0.4 points per stock trade. **Earlier entry does not rescue options.**

## 5. Other option structures and picking my own contract, on real prices
Real UW daily history was fetched on 2026-09-30 for every leg: 7,758 contracts, `scripts/desk_fetch_legs.py`. Only trades
where every leg had the needed prices are counted, so the trade count is smaller than the signal count. Guessed strikes that were not
listed are skipped. Fills are conservative: buy legs at the opening trade + half the gap, sell short legs at the opening
trade − half the gap, close longs at the bid and shorts at the ask.

Returns are on capital at risk: the debit paid, the max loss for credit spreads, or the cash that secures a short put.
Output: `journal/desk-structures.json`.

| Structure (real prices) | Practice year | Sealed test | Recent months |
|---|---|---|---|
| **Stock (raw, not vs S&P 500)** | **+0.9% / +1.6% / 55% (474)** | **+0.8% / +2.0% / 54% (599)** | −1.6% / −1.5% / 41% (295) |
| Sell a put 5% out of the money (cash-secured) | +0.8% / +0.3% / 64% (283) | +0.6% / 0.0% / 59% (329) | −0.3% / −1.4% / 45% (168) |
| My own call: at the money, ~60 days | −1.5% / +8.9% / 47% (207) | −8.8% / +0.4% / 38% (183) | −23.2% / −17.1% / 24% (140) |
| My own call: 10% in the money, ~60 days | −4.2% / −0.4% / 42% (191) | −8.5% / −0.2% / 39% (160) | −15.3% / −9.6% / 30% (93) |
| Call debit spread (ATM → +10%) | −22.4% / −16.1% / 33% (230) | −28.2% / −26.0% / 23% (244) | −46.9% / −41.6% / 15% (121) |
| Bull put spread (sell 5% / buy 15% out of the money) | −3.2% / n/m / 46% (216) | −7.4% / n/m / 38% (242) | −18.6% / n/m / 23% (111) |
| Whale's own call | −25.0% / −4.6% / 36% (469) | −22.8% / +8.8% / 36% (597) | −47.4% / −27.2% / 20% (287) |

"n/m" means not meaningful: a few spreads had almost no risk (the credit was nearly the full width), so the mean blows
up. Use the median.

**Result.** On real prices nothing beat the stock:
- Buying options lost for the typical trade, whether the whale's contract or my own at-the-money or 10% in-the-money
  call ~60 days out.
- Both spreads lost.
- Selling a put 5% out of the money was about breakeven (mean ≈ 0%, win 59–64%) and lost in the recent months.

The model estimates I used before the fetch had been too optimistic by about 5–15 points. Option research
stops here.

## 6. Related checks (why the filter is built this way)
| Check | Result | Decision |
|---|---|---|
| **Put buys as bearish signals** (five-day vs S&P 500; median / mean / win) | All clean put buys: practice year −0.3% / −0.7% / 48%, sealed test +0.1% / −0.6% / 50%, recent months +0.5% / +0.4% / 54%. Whale-size puts flip-flop: +2.4% (38 trades) → −1.8% (76 trades) → +1.1% (85 trades) | Not a signal; shown as a labelled "Bearish watch" list |
| **Next-morning OI confirmation** (practice-year signals; mean / win) | Confirmed: +1.1% / 54% (462 trades). Not confirmed: +4.6% / 67% (18 trades). No OI data: −0.3% (8 trades) | Shown on cards as context; not a filter |
| **Repeat buying / accumulation** (practice-year clean buys; mean / win) | Repeat buyer +0.1% / 46% (3,539 trades) vs other clean buy +0.3% / 50% (3,885 trades) | Shown on cards; not a filter |

## Caveats
- **Exploratory.** Every study here ran after the frozen filter's single sealed test, so none of it may be used to
  re-tune the filter without labelling that.
- **Stock isn't proven either.** It lost in the recent months. Much of the gain over the S&P 500 is beta: signals swing 2.1–2.4× as
  much as the S&P 500, and the beta-adjusted sealed-test edge is +0.57% vs +1.38% plain ([`BETA-CHECK.md`](BETA-CHECK.md)).
- **Option fills use daily data.** Intraday quotes aren't available, so take-profit fills assume the daily high was
  tradable: optimistic.
- **Whale-to-expiry assumes the average alert price** and no costs.
- **Leg coverage:** real-price rows cover about 40–60% of signals (legs with prices on both dates); unlisted guessed strikes are skipped.
- **Not financial advice.**

## Rerun the numbers
```bash
cd backend
uv run python scripts/desk_build_rows.py 2024-10-01 2025-01-31   # … one run per date chunk (cache → data/desk/*.pkl)
uv run whaleproof evidence                          # filter evidence (practice year + recent months) → journal/desk-evidence.json
uv run python scripts/research/vehicle_study.py     # sections 1–4 and 6 → journal/research/vehicle-study.json
uv run python scripts/desk_structures.py            # section 5 → journal/desk-structures.json
uv run python scripts/desk_fetch_legs.py 9000       # optional: real leg prices (UW calls; run after the 20:00 ET reset)
```
