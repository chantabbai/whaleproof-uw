# WhaleProof analysis — train (2024-10-01 → 2025-09-30)

> **How to read this.** This is raw output from WhaleProof's first research engine: the statistical tests I wrote down
> in advance and ran on the practice year. There's a plain summary in
> [`METHODOLOGY.md`](METHODOLOGY.md#what-i-tried-first). Each row asks one question, for example whether alerts with
> heavy dark-pool buying did better than those with little. **days** is the number of trading days with data, and
> **effect** is how much better the first group did over five days against the S&P 500. The **95% CI** is the likely
> range of that effect; if it includes 0, the effect could be luck. **p** is how likely a result this big would be by
> luck alone, and **Holm p** is the same thing made stricter because so many questions were asked at once. Below 0.05
> counts as a real result. **x5** is the five-day return minus the S&P 500. Rows marked *not backtestable* had no
> history to test.

Pre-registered tests (docs/preregistration.md, Amendments 7–8). Unit = day; day-clustered bootstrap (10,000 resamples), two-sided p, Holm within family A (setups + H10) and family B (the rest). Effects are oriented by the train sign (H3/H5/H9). **Tradeable** = Holm p < 0.05, same sign on train, effect ≥ +0.20%/5d, ≥ 60 days. **Train = in-sample: choices were made on these rows, so no verdict here — only the holdout decides.**

| test | question | days | effect | 95% CI | p | Holm p | train effect | in-sample, not a verdict |
|---|---|---|---|---|---|---|---|---|
| F.1 | finalist Confirmed bold bet (1–3 months, >5% OTM): OI confirmed + 31–90 days to expiry + over 5% OTM (x5) | 248 | +0.05% | -0.40% … +0.50% | 0.8248 | 0.8248 | +0.05% | in-sample |
| F.2 | finalist Cheap option, long: option cheap + long only (x5) | 245 | +0.90% | +0.46% … +1.36% | 0.0001 | 0.0003 | +0.90% | in-sample |
| F.3 | finalist Far out-of-the-money buy, fair price, long: setup: far OTM + option not rich + long only (x5) | 190 | +1.99% | +0.68% … +3.36% | 0.0044 | 0.0088 | +1.99% | in-sample |
| H1 | v0.5 top-5/day vs SPY (x5) | 250 | +0.06% | -0.41% … +0.51% | 0.7981 | 1.0000 | +0.06% | in-sample |
| H2 | v1 top-5 − v0.5 top-5 (x5) | 1 | +2.13% | +2.13% … +2.13% | 1.0000 | 1.0000 | +2.13% | insufficient data |
| H3 | UW-flagged − unflagged (x5, oriented) | 250 | +0.09% | -0.38% … +0.59% | 0.7055 | 1.0000 | +0.09% | in-sample |
| H4 | SKIP − GO, v0.5 labels (x5) | 250 | -0.48% | -1.07% … +0.11% | 0.1104 | 1.0000 | -0.48% | in-sample |
| H5.dark_pool | dark_pool: top − bottom tercile (x5, oriented) | 250 | +0.49% | +0.06% … +0.91% | 0.0257 | 0.3598 | +0.49% | in-sample |
| H5.dp_blocks | dp_blocks: top − bottom tercile (x5, oriented) | 250 | +0.42% | -0.05% … +0.88% | 0.0790 | 0.9480 | +0.42% | in-sample |
| H5.sector_flow | sector_flow: top − bottom tercile (x5, oriented) | 228 | +0.82% | -0.04% … +1.70% | 0.0640 | 0.8320 | +0.82% | in-sample |
| H5.ticker_flow | ticker_flow: top − bottom tercile (x5, oriented) | 250 | +0.08% | -0.37% … +0.54% | 0.7381 | 1.0000 | +0.08% | in-sample |
| H6 | chosen stop/target cell − (0.75, 1.25)×EM (plan exit) | 250 | +0.12% | +0.04% … +0.19% | 0.0018 | 0.0270 | +0.12% | in-sample |
| H7 | follow-the-money − plan exit (per trade) | 250 | +0.01% | -0.01% … +0.03% | 0.3618 | 1.0000 | +0.01% | in-sample |
| H8 | OI-confirmed − unconfirmed (x5) | 250 | +0.08% | -0.24% … +0.38% | 0.6319 | 1.0000 | +0.08% | in-sample |
| H9.iv_rv | iv_rv: top − bottom tercile (x5, oriented) | 227 | +0.42% | -0.15% … +0.98% | 0.1450 | 1.0000 | +0.42% | in-sample |
| H9.macro_event | macro_event: top − bottom tercile (x5, oriented) | 0 | – | – | 1.0000 | 1.0000 | – | not backtestable |
| H9.option_sentiment | option_sentiment: top − bottom tercile (x5, oriented) | 0 | – | – | 1.0000 | 1.0000 | – | not backtestable |
| H9.skew | skew: top − bottom tercile (x5, oriented) | 0 | – | – | 1.0000 | 1.0000 | – | not backtestable |
| H10 | pure gate passers − noise (x5, simple backtest) | 250 | -0.04% | -0.24% … +0.15% | 0.7153 | 1.0000 | -0.04% | in-sample |
| S.clean_other | setup clean_other vs SPY (x5, simple backtest) | 250 | -0.02% | -0.23% … +0.19% | 0.8236 | 1.0000 | -0.02% | in-sample |
| S.far_otm | setup far_otm vs SPY (x5, simple backtest) | 233 | -0.18% | -1.77% … +1.23% | 0.7993 | 1.0000 | -0.18% | in-sample |
| S.pre_earnings | setup pre_earnings vs SPY (x5, simple backtest) | 202 | -0.36% | -1.32% … +0.62% | 0.4590 | 1.0000 | -0.36% | in-sample |
| S.repeat_buyer | setup repeat_buyer vs SPY (x5, simple backtest) | 250 | -0.17% | -0.37% … +0.02% | 0.0779 | 0.5453 | -0.17% | in-sample |
| S.sweep | setup sweep vs SPY (x5, simple backtest) | 250 | -0.25% | -0.60% … +0.10% | 0.1586 | 0.9516 | -0.25% | in-sample |
| S.whale_sweep | setup whale_sweep vs SPY (x5, simple backtest) | 120 | -0.13% | -1.50% … +1.38% | 0.8529 | 1.0000 | -0.13% | in-sample |

*Not investment advice. Past performance does not guarantee future results.*
