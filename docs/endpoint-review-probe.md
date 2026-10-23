# Endpoint-review probe (metadata only)

Run 2026-09-28 17:31 ET · ticker NVDA · history target 2024-10-25. `stale` = asked for a past date but got only newer rows (screener fallback → no history).

| endpoint | when | status | rows | oldest | newest | stale | fields / error |
|---|---|---|---|---|---|---|---|
| rr_skew | today | 200 | 11 | 2026-09-14 | 2026-09-28 |  | date, delta, risk_reversal, ticker |
| realized_vol | today | 200 | 751 | 2023-09-29 | 2026-09-28 |  | date, implied_volatility, implied_volatility_days, price, realized_volatility, realized_volatility_days, unshifted_rv_date |
| vrp | today | 200 | 231 | 2025-09-29 | 2026-08-28 |  | date, implied_volatility, implied_volatility_days, rank, realized_date, realized_volatility, realized_volatility_days, risk_premium, ticker |
| vol_stats | today | 200 | 1 | 2026-09-28 | 2026-09-28 |  | date, iv, iv_high, iv_low, iv_rank, rv, rv_high, rv_low, ticker |
| vol_stats | 2024-10-25 | 200 | 1 | 2024-10-25 | 2024-10-25 |  | date, iv, iv_high, iv_low, iv_rank, rv, rv_high, rv_low, ticker |
| option_sentiment | today | 200 | 1 |  |  |  | history, latest |
| option_sentiment | 2024-10-25 | 200 | 1 |  |  |  | history, latest |
| option_sentiment_top | today | 200 | 5 | 2026-09-28 | 2026-09-28 |  | avar, components, date, direction, sample_size, score, ticker, updated_at, vwks |
| option_sentiment_top | 2024-10-25 | 200 | 5 | 2024-10-25 | 2024-10-25 |  | avar, components, date, direction, sample_size, score, ticker, updated_at, vwks |
| options_pulse | today | 200 | 1 |  |  |  | intraday, latest |
| options_pulse | 2024-10-25 | 200 | 1 |  |  |  | intraday, latest |
| options_pulse_top | today | 200 | 5 |  |  |  | call_txn, hr_min, intvl_sntm_score, put_call_ratio, put_txn, sntm_score, ticker, trd_dt |
| options_pulse_top | 2024-10-25 | 200 | 0 |  |  |  |  |
| econ_calendar | today | 200 | 84 | 2026-09-29 | 2026-10-09 |  | event, forecast, prev, reported_period, time, type |
| analysts | today | 200 | 5 | 2024-08-29 | 2024-10-20 |  | action, analyst_name, firm, recommendation, sector, target, ticker, timestamp |
| short_interest | today | 200 | 126 | 2021-06-15 | 2026-08-31 |  | days_to_cover, fee_rate, market_date, rebate_rate, short_interest, short_shares_available, si_float, si_float_with_synth_long_pct_of_total_shares, symbol, total_float |
| short_volume | today | 200 | 500 | 2024-09-27 | 2026-09-25 |  | market_date, short_volume, short_volume_ratio, total_volume |
| ftds | today | 200 | 786 | 2021-11-16 | 2026-08-31 |  | date, price, quantity |
| top_net_impact | today | 200 | 5 |  |  |  | net_premium, ticker |
| top_net_impact | 2024-10-25 | 200 | 5 |  |  |  | net_premium, ticker |
| etf_flow | today | 200 | 498 | 2024-10-01 | 2026-09-25 |  | change, change_prem, close, date, expiration_cycle, is_fomc, volume |
| greek_exposure | today | 200 | 751 | 2023-09-29 | 2026-09-28 |  | call_charm, call_delta, call_gamma, call_vanna, date, put_charm, put_delta, put_gamma, put_vanna |

## uw_unusual coverage (pre-registration Amendment 1)

```
{
  "day": "2026-09-15",
  "cached_symbols": 390,
  "pages": 2,
  "paging_symbols": 390,
  "paging_matches_cached": true,
  "paging_missing": 0,
  "paging_extra": 0,
  "slices_symbols": 390,
  "slices_matches_cached": true,
  "slices_missing": 0,
  "slices_extra": 0
}
```
