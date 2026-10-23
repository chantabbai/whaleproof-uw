# WhaleProof Backtest — 2024-10-01 → 2025-09-30 (weights simple rules, train)

> **How to read this.** This is raw output from WhaleProof's first research engine, kept as the evidence for the
> practice-year numbers. There's a plain summary in [`METHODOLOGY.md`](METHODOLOGY.md#what-i-tried-first). In the
> tables, **n** is the number of trades (92.8K means 92,800). **all** is every one-way UW alert over $100K, **NOISE** is
> the alerts that failed the clean-buy check (hedges, closing trades, spread legs), **PURE** is the clean opening buys
> that passed, and **PUT_SALE** is puts sold for premium, which is a bullish trade. The **beat-SPY rate** is how often
> the stock beat the S&P 500 over the next five trading days, and the **95% CI** in brackets is the range the true
> figure most likely falls in. **Mean** and **median excess** are the average and typical five-day return minus the
> S&P's. **Profit factor** is total gains divided by total losses, so above 1 made money. The **hash** is a fingerprint
> of the rule version. Tables with 0 rows are old-engine features this run didn't use.

Entry = next session open after the alert day. Returns are in the trade's direction, underlying only, net of 5 bps slippage per side. Groups under 30 trades are flagged ⚠ low sample.
Sessions: 250 · skipped (no price data): 2.71K · hash `b25fdeea259e`

## Headline: 5-day return in excess of SPY (removes market beta)

| group | n | beat-SPY rate (95% CI) | mean excess | median excess |
|---|---|---|---|---|
| all | 92.8K | 48.7% (48–49) | -0.09% | -0.10% |
| NOISE | 72.9K | 48.8% (48–49) | -0.09% | -0.10% |
| PURE | 16.4K | 47.8% (47–49) | -0.16% | -0.10% |
| PUT_SALE | 3.4K | 50.6% (49–52) | +0.31% | +0.08% |
| bearish | 44.5K | 48.4% (48–49) | -0.49% | -0.10% |
| bullish | 48.2K | 49.0% (49–49) | +0.28% | -0.09% |

## Setups (pure-directional gate; no 5/day cap) — expectancy first

Win rate alone misleads: profit factor = total gains ÷ total losses (> 1 makes money).

| setup | n | trades/day | 5d win | mean 5d | mean vs SPY | profit factor | day-clustered vs SPY (95% CI) |
|---|---|---|---|---|---|---|---|
| pre_earnings | 1.38K | 5.5 | 48% | -0.03% | -0.04% | 0.99 | -1.39% … +0.60% |
| far_otm | 787 | 3.1 | 49% | -1.19% | -1.48% | 0.80 | -1.88% … +1.14% |
| whale_sweep | 166 | 0.7 | 48% | -0.47% | -0.42% | 0.85 | -1.51% … +1.46% |
| repeat_buyer | 5.19K | 20.8 | 50% | -0.15% | -0.17% | 0.95 | -0.36% … +0.02% |
| sweep | 2.28K | 9.1 | 48% | -0.24% | -0.20% | 0.92 | -0.58% … +0.11% |
| clean_other | 6.62K | 26.5 | 49% | +0.02% | +0.01% | 1.01 | -0.24% … +0.20% |
| pure_all | 16.4K | 65.7 | 49% | -0.14% | -0.16% | 0.96 | -0.30% … +0.02% |
| noise | 72.9K | 291.8 | 49% | -0.09% | -0.09% | 0.97 | -0.15% … -0.04% |
| put_sale | 3.4K | 13.6 | 53% | +0.77% | +0.31% | 1.27 | -0.13% … +0.81% |

Noise — first gate failure: DTE 5.58K, ETF put 804, call and put both bought 130, floor/cross trade 2.35K, issue type Structured Product 19, issue type Unit 2, moneyness 2.12K, not a buy 41.6K, not clearly opening 23.7K, same-second sold leg 44

## Raw 5-day return and plan exits (target / invalidation / time stop — same rules as live)

| group | 5d n | 5d hit (95% CI) | 5d mean | 5d median | plan n | plan hit (95% CI) | plan mean | plan median |
|---|---|---|---|---|---|---|---|---|
| all | 92.8K | 49.2% (49–50) | -0.07% | -0.09% | 0 | – | – | – |
| NOISE | 72.9K | 49.0% (49–49) | -0.09% | -0.10% | 0 | – | – | – |
| PURE | 16.4K | 49.1% (48–50) | -0.14% | -0.10% | 0 | – | – | – |
| PUT_SALE | 3.4K | 53.4% (52–55) | +0.77% | +0.52% | 0 | – | – | – |
| bearish | 44.5K | 45.1% (45–46) | -0.84% | -0.54% | 0 | – | – | – |
| bullish | 48.2K | 53.0% (53–53) | +0.65% | +0.35% | 0 | – | – | – |

## Next-morning OI confirmation (measured pre-open; not used by the 16:30 decision)

| group | n | beat-SPY rate (95% CI) | mean excess | median excess |
|---|---|---|---|---|
| GO_confirmed | 0 | – | – | – |
| GO_unconfirmed | 0 | – | – | – |
| all_confirmed | 12.6K | 48.2% (47–49) | +0.11% | -0.10% |
| all_unconfirmed | 5.09K | 48.1% (47–50) | -0.08% | -0.10% |

## Exit rule comparison: fixed plan vs plan + follow the money

| group | plan n | plan hit (95% CI) | plan mean | plan median | follow n | follow hit (95% CI) | follow mean | follow median |
|---|---|---|---|---|---|---|---|---|
| all | 0 | – | – | – | 0 | – | – | – |
| official-like | 0 | – | – | – | 0 | – | – | – |
| NOISE | 0 | – | – | – | 0 | – | – | – |
| PURE | 0 | – | – | – | 0 | – | – | – |
| PUT_SALE | 0 | – | – | – | 0 | – | – | – |

## Official-like: top 5 GO per day (what is traded live)

| measure | n | hit rate (95% CI) | mean | median |
|---|---|---|---|---|
| vs SPY, 5 days | 0 | – | – | – |
| plan exits | 0 | – | – | – |

## Reward : risk

| bucket | n | beat-SPY (95% CI) | mean excess | median excess | plan n | plan hit | plan mean | plan median |
|---|---|---|---|---|---|---|---|---|
| n/a | 92.8K | 48.7% (48–49) | -0.09% | -0.10% | 0 | – | – | – |

## Score (backtestable checks)

| bucket | n | beat-SPY (95% CI) | mean excess | median excess | plan n | plan hit | plan mean | plan median |
|---|---|---|---|---|---|---|---|---|
| 0–5 | 92.8K | 48.7% (48–49) | -0.09% | -0.10% | 0 | – | – | – |

## Days to expiry

| bucket | n | beat-SPY (95% CI) | mean excess | median excess | plan n | plan hit | plan mean | plan median |
|---|---|---|---|---|---|---|---|---|
| 15–45 | 25.6K | 49.1% (48–50) | -0.10% | -0.10% | 0 | – | – | – |
| 46–90 | 14.7K | 48.4% (48–49) | -0.16% | -0.10% | 0 | – | – | – |
| >90 | 34.3K | 48.8% (48–49) | +0.01% | -0.10% | 0 | – | – | – |
| ≤14 | 18.1K | 48.3% (48–49) | -0.20% | -0.10% | 0 | – | – | – |

## Alert premium

| bucket | n | beat-SPY (95% CI) | mean excess | median excess | plan n | plan hit | plan mean | plan median |
|---|---|---|---|---|---|---|---|---|
| $100K–250K | 59K | 48.8% (48–49) | -0.10% | -0.10% | 0 | – | – | – |
| $1M–5M | 4.74K | 46.4% (45–48) | -0.07% | -0.10% | 0 | – | – | – |
| $250K–1M | 28.8K | 49.0% (48–50) | -0.08% | -0.10% | 0 | – | – | – |
| >$5M | 261 | 42.1% (36–48) | -0.24% | -0.10% | 0 | – | – | – |

## IV rank

| bucket | n | beat-SPY (95% CI) | mean excess | median excess | plan n | plan hit | plan mean | plan median |
|---|---|---|---|---|---|---|---|---|
| n/a | 92.8K | 48.7% (48–49) | -0.09% | -0.10% | 0 | – | – | – |

## Sector

| bucket | n | beat-SPY (95% CI) | mean excess | median excess | plan n | plan hit | plan mean | plan median |
|---|---|---|---|---|---|---|---|---|
| Basic Materials | 2.08K | 49.0% (47–51) | -0.23% | -0.08% | 0 | – | – | – |
| Communication Services | 6.38K | 49.8% (49–51) | +0.01% | -0.02% | 0 | – | – | – |
| Consumer Cyclical | 10.6K | 49.3% (48–50) | -0.10% | -0.09% | 0 | – | – | – |
| Consumer Defensive | 3.21K | 47.8% (46–49) | -0.18% | -0.18% | 0 | – | – | – |
| Energy | 2.83K | 48.2% (46–50) | -0.17% | -0.16% | 0 | – | – | – |
| Financial Services | 7.75K | 49.1% (48–50) | -0.07% | -0.06% | 0 | – | – | – |
| Healthcare | 6.14K | 48.8% (48–50) | -0.08% | -0.13% | 0 | – | – | – |
| Industrials | 5.8K | 48.7% (47–50) | -0.17% | -0.14% | 0 | – | – | – |
| Real Estate | 512 | 48.4% (44–53) | -0.30% | -0.20% | 0 | – | – | – |
| Technology | 23.9K | 49.2% (49–50) | -0.06% | -0.10% | 0 | – | – | – |
| Utilities | 1.68K | 49.8% (47–52) | -0.06% | -0.05% | 0 | – | – | – |
| n/a | 21.9K | 47.6% (47–48) | -0.09% | -0.10% | 0 | – | – | – |

## Stock vs ETF

| bucket | n | beat-SPY (95% CI) | mean excess | median excess | plan n | plan hit | plan mean | plan median |
|---|---|---|---|---|---|---|---|---|
| ADR | 5.64K | 49.6% (48–51) | -0.11% | -0.05% | 0 | – | – | – |
| Common Stock | 73K | 49.1% (49–49) | -0.07% | -0.10% | 0 | – | – | – |
| ETF | 13.9K | 46.5% (46–47) | -0.16% | -0.10% | 0 | – | – | – |
| Structured Product | 102 | 50.0% (40–60) | -0.26% | +0.01% | 0 | – | – | – |
| Unit | 92 | 55.4% (45–65) | +0.22% | +0.25% | 0 | – | – | – |

## Earnings

| bucket | n | beat-SPY (95% CI) | mean excess | median excess | plan n | plan hit | plan mean | plan median |
|---|---|---|---|---|---|---|---|---|
| n/a | 92.8K | 48.7% (48–49) | -0.09% | -0.10% | 0 | – | – | – |

## Market trend

| bucket | n | beat-SPY (95% CI) | mean excess | median excess | plan n | plan hit | plan mean | plan median |
|---|---|---|---|---|---|---|---|---|
| SPY above 50d | 69.8K | 48.7% (48–49) | -0.07% | -0.10% | 0 | – | – | – |
| SPY below 50d | 23K | 48.7% (48–49) | -0.16% | -0.10% | 0 | – | – | – |

## Weekday

| bucket | n | beat-SPY (95% CI) | mean excess | median excess | plan n | plan hit | plan mean | plan median |
|---|---|---|---|---|---|---|---|---|
| Fri | 19.2K | 48.6% (48–49) | -0.08% | -0.10% | 0 | – | – | – |
| Mon | 17.6K | 48.7% (48–49) | -0.07% | -0.10% | 0 | – | – | – |
| Thu | 18.1K | 48.9% (48–50) | -0.07% | -0.09% | 0 | – | – | – |
| Tue | 19.4K | 48.9% (48–50) | -0.07% | -0.10% | 0 | – | – | – |
| Wed | 18.5K | 48.5% (48–49) | -0.15% | -0.10% | 0 | – | – | – |

## Year

| bucket | n | beat-SPY (95% CI) | mean excess | median excess | plan n | plan hit | plan mean | plan median |
|---|---|---|---|---|---|---|---|---|
| 2024 | 20.3K | 48.1% (47–49) | -0.13% | -0.11% | 0 | – | – | – |
| 2025 | 72.4K | 48.9% (49–49) | -0.08% | -0.10% | 0 | – | – | – |

## By check (5-day)

| check | side | n | hit rate (95% CI) | mean | median |
|---|---|---|---|---|---|

## By month (5-day)

| month | n | hit rate (95% CI) | mean | median |
|---|---|---|---|---|
| 2024-10 | 7.26K | 48.6% (47–50) | -0.13% | -0.11% |
| 2024-11 | 7.04K | 48.7% (48–50) | -0.03% | -0.13% |
| 2024-12 | 6.01K | 48.4% (47–50) | -0.23% | -0.21% |
| 2025-01 | 6.97K | 49.3% (48–50) | -0.19% | -0.07% |
| 2025-02 | 8.03K | 49.4% (48–50) | -0.09% | -0.13% |
| 2025-03 | 8.06K | 49.1% (48–50) | -0.15% | -0.10% |
| 2025-04 | 8.56K | 49.9% (49–51) | -0.10% | -0.01% |
| 2025-05 | 7.68K | 49.2% (48–50) | +0.05% | -0.07% |
| 2025-06 | 6.98K | 49.3% (48–50) | -0.07% | -0.08% |
| 2025-07 | 8.42K | 49.7% (49–51) | -0.06% | -0.02% |
| 2025-08 | 8.29K | 49.2% (48–50) | +0.01% | -0.10% |
| 2025-09 | 9.45K | 49.4% (48–50) | +0.07% | -0.07% |

*Not investment advice. Past performance does not guarantee future results.*
