# UW Endpoint Matrix (Basic plan)

Derived metadata only — no market data values.

| endpoint | when | status | rows | first_date | last_date | keys | error |
|---|---|---|---|---|---|---|---|
| flow_alerts | today | 200 | 5 | 2026-09-25 | 2026-09-25 | alert_rule, all_opening_trades, ask, bid, created_at, delta, end_time, er_time, expiry, expiry_count, gamma, has_floor, has_multileg, has_singleleg, has_sweep, id, issue_type, iv, iv_end, iv_start, marketcap, missing_periscope, next_earnings_date, open_interest, option_chain |  |
| flow_alerts | 2026-03-27 | 200 | 5 | 2026-03-27 | 2026-03-27 | alert_rule, all_opening_trades, ask, bid, created_at, delta, end_time, er_time, expiry, expiry_count, gamma, has_floor, has_multileg, has_singleleg, has_sweep, id, issue_type, iv, iv_end, iv_start, marketcap, missing_periscope, next_earnings_date, open_interest, option_chain |  |
| flow_alerts | 2025-09-26 | 200 | 5 | 2025-09-26 | 2025-09-26 | alert_rule, all_opening_trades, ask, bid, created_at, delta, end_time, er_time, expiry, expiry_count, gamma, has_floor, has_multileg, has_singleleg, has_sweep, id, issue_type, iv, iv_end, iv_start, marketcap, next_earnings_date, open_interest, option_chain, price |  |
| flow_alerts | 2024-10-25 | 200 | 5 | 2024-10-25 | 2024-10-25 | alert_rule, all_opening_trades, ask, bid, created_at, delta, end_time, er_time, expiry, expiry_count, gamma, has_floor, has_multileg, has_singleleg, has_sweep, id, issue_type, iv, iv_end, iv_start, marketcap, next_earnings_date, open_interest, option_chain, price |  |
| stock_flow_alerts | today | 200 | 5 | 2026-09-25 | 2026-09-25 | alert_rule, all_opening_trades, created_at, delta, expiry, expiry_count, gamma, has_floor, has_multileg, has_singleleg, has_sweep, iv, iv_end, iv_start, open_interest, option_chain, price, rho, strike, theo, theta, ticker, total_ask_side_prem, total_bid_side_prem, total_premium |  |
| option_activity_unusual | today | 200 | 5 |  |  | ask_side_perc_7_day, ask_side_volume, avg_price, bid_side_perc_7_day, bid_side_volume, chain_prev_close, close, cross_volume, days_of_oi_increases, days_of_vol_greater_than_oi, delta, er_time, expiry, floor_volume, gamma, high, is_new, issue_type, iv_change, last_fill, low, mid_volume, multileg_volume, next_earnings_date, no_side_volume |  |
| option_activity_unusual | 2026-03-27 | 200 | 5 |  |  | ask_side_perc_7_day, ask_side_volume, avg_price, bid_side_perc_7_day, bid_side_volume, chain_prev_close, close, cross_volume, days_of_oi_increases, days_of_vol_greater_than_oi, delta, er_time, expiry, floor_volume, gamma, high, is_new, issue_type, iv_change, last_fill, low, mid_volume, multileg_volume, next_earnings_date, no_side_volume |  |
| option_activity_unusual | 2025-09-26 | 200 | 5 |  |  | ask_side_perc_7_day, ask_side_volume, avg_price, bid_side_perc_7_day, bid_side_volume, chain_prev_close, close, cross_volume, days_of_oi_increases, days_of_vol_greater_than_oi, delta, er_time, expiry, floor_volume, gamma, high, is_new, issue_type, iv_change, last_fill, low, mid_volume, multileg_volume, next_earnings_date, no_side_volume |  |
| option_activity_unusual | 2024-10-25 | 200 | 5 |  |  | ask_side_perc_7_day, ask_side_volume, avg_price, bid_side_perc_7_day, bid_side_volume, chain_prev_close, close, cross_volume, days_of_oi_increases, days_of_vol_greater_than_oi, delta, er_time, expiry, floor_volume, gamma, high, is_new, issue_type, iv_change, last_fill, low, mid_volume, multileg_volume, next_earnings_date, no_side_volume |  |
| gex_levels | today | 200 | 1 | 2026-09-25 | 2026-09-25 | call_wall, date, gamma_flip, gamma_magnet, nearby_flips, put_wall, source, time |  |
| gex_levels | 2026-03-27 | 200 | 1 | 2026-03-27 | 2026-03-27 | call_wall, date, gamma_flip, gamma_magnet, nearby_flips, put_wall, source, time |  |
| gex_levels | 2025-09-26 | 200 | 1 | 2025-09-26 | 2025-09-26 | call_wall, date, gamma_flip, gamma_magnet, nearby_flips, put_wall, source, time |  |
| gex_levels | 2024-10-25 | 200 | 1 | 2024-10-25 | 2024-10-25 | call_wall, date, gamma_flip, gamma_magnet, nearby_flips, put_wall, source, time |  |
| spot_exposures_strike | today | 200 | 273 | 2026-09-25 | 2026-09-25 | call_charm_ask, call_charm_bid, call_charm_oi, call_charm_vol, call_delta_ask, call_delta_bid, call_delta_oi, call_delta_vol, call_gamma_ask, call_gamma_bid, call_gamma_oi, call_gamma_vol, call_vanna_ask, call_vanna_bid, call_vanna_oi, call_vanna_vol, date, price, put_charm_ask, put_charm_bid, put_charm_oi, put_charm_vol, put_delta_ask, put_delta_bid, put_delta_oi |  |
| spot_exposures_strike | 2026-03-27 | 200 | 261 | 2026-03-27 | 2026-03-27 | call_charm_ask, call_charm_bid, call_charm_oi, call_charm_vol, call_delta_ask, call_delta_bid, call_delta_oi, call_delta_vol, call_gamma_ask, call_gamma_bid, call_gamma_oi, call_gamma_vol, call_vanna_ask, call_vanna_bid, call_vanna_oi, call_vanna_vol, date, price, put_charm_ask, put_charm_bid, put_charm_oi, put_charm_vol, put_delta_ask, put_delta_bid, put_delta_oi |  |
| spot_exposures_strike | 2025-09-26 | 200 | 307 | 2025-09-26 | 2025-09-26 | call_charm_ask, call_charm_bid, call_charm_oi, call_charm_vol, call_delta_ask, call_delta_bid, call_delta_oi, call_delta_vol, call_gamma_ask, call_gamma_bid, call_gamma_oi, call_gamma_vol, call_vanna_ask, call_vanna_bid, call_vanna_oi, call_vanna_vol, date, price, put_charm_ask, put_charm_bid, put_charm_oi, put_charm_vol, put_delta_ask, put_delta_bid, put_delta_oi |  |
| spot_exposures_strike | 2024-10-25 | 200 | 328 | 2024-10-25 | 2024-10-25 | call_charm_ask, call_charm_bid, call_charm_oi, call_charm_vol, call_delta_ask, call_delta_bid, call_delta_oi, call_delta_vol, call_gamma_ask, call_gamma_bid, call_gamma_oi, call_gamma_vol, call_vanna_ask, call_vanna_bid, call_vanna_oi, call_vanna_vol, date, price, put_charm_ask, put_charm_bid, put_charm_oi, put_charm_vol, put_delta_ask, put_delta_bid, put_delta_oi |  |
| dp_price_levels | today | 200 | 19 |  |  | dark_pool_volume, price, regular_volume |  |
| dp_price_levels | 2026-03-27 | 200 | 27 |  |  | dark_pool_volume, price, regular_volume |  |
| dp_price_levels | 2025-09-26 | 200 | 14 |  |  | dark_pool_volume, price, regular_volume |  |
| dp_price_levels | 2024-10-25 | 200 | 9 |  |  | dark_pool_volume, price, regular_volume |  |
| darkpool_ticker | today | 200 | 500 | 2026-09-25 | 2026-09-25 | canceled, executed_at, ext_hour_sold_codes, market_center, nbbo_ask, nbbo_ask_quantity, nbbo_bid, nbbo_bid_quantity, premium, price, sale_cond_codes, size, ticker, tracking_id, trade_code, trade_settlement, trf_executed_at, volume |  |
| darkpool_ticker | 2026-03-27 | 200 | 500 | 2026-03-27 | 2026-03-27 | canceled, executed_at, ext_hour_sold_codes, market_center, nbbo_ask, nbbo_ask_quantity, nbbo_bid, nbbo_bid_quantity, premium, price, sale_cond_codes, size, ticker, tracking_id, trade_code, trade_settlement, trf_executed_at, volume |  |
| darkpool_ticker | 2025-09-26 | 200 | 500 | 2025-09-26 | 2025-09-26 | canceled, executed_at, ext_hour_sold_codes, market_center, nbbo_ask, nbbo_ask_quantity, nbbo_bid, nbbo_bid_quantity, premium, price, sale_cond_codes, size, ticker, tracking_id, trade_code, trade_settlement, trf_executed_at, volume |  |
| darkpool_ticker | 2024-10-25 | 200 | 500 | 2024-10-25 | 2024-10-25 | canceled, executed_at, ext_hour_sold_codes, market_center, nbbo_ask, nbbo_ask_quantity, nbbo_bid, nbbo_bid_quantity, premium, price, sale_cond_codes, size, ticker, tracking_id, trade_code, trade_settlement, trf_executed_at, volume |  |
| iv_rank | today | 200 | 5 | 2026-09-21 | 2026-09-25 | close, date, iv_rank_1y, updated_at, volatility |  |
| iv_rank | 2026-03-27 | 200 | 251 | 2025-09-26 | 2026-09-25 | close, date, iv_rank_1y, updated_at, volatility |  |
| iv_rank | 2025-09-26 | 200 | 251 | 2025-09-26 | 2026-09-25 | close, date, iv_rank_1y, updated_at, volatility |  |
| iv_rank | 2024-10-25 | 200 | 251 | 2025-09-26 | 2026-09-25 | close, date, iv_rank_1y, updated_at, volatility |  |
| vol_anomaly | today | 200 | 1 |  |  | history, latest |  |
| vol_anomaly | 2026-03-27 | 200 | 1 |  |  | history, latest |  |
| vol_anomaly | 2025-09-26 | 200 | 1 |  |  | history, latest |  |
| vol_anomaly | 2024-10-25 | 200 | 1 |  |  | history, latest |  |
| vrp | today | 200 | 231 | 2025-09-26 | 2026-08-27 | date, implied_volatility, implied_volatility_days, rank, realized_date, realized_volatility, realized_volatility_days, risk_premium, ticker |  |
| unusualness | today | 200 | 1 | 2026-09-25 | 2026-09-25 | date, opt_samples, opt_vol_decile, opt_vol_pctile, stock_samples, stock_vol_decile, stock_vol_pctile |  |
| option_stance | today | 422 | 0 |  |  |  | 422 /api/stock/NVDA/option-stance: {"error":"stance query parameter is required"} |
| ohlc_1d | today | 200 | 600 | 2025-12-09 | 2026-09-25 | close, date, high, low, market_time, open, total_volume, volume |  |
| market_tide | today | 200 | 81 | 2026-09-25 | 2026-09-25 | date, net_call_premium, net_put_premium, net_volume, timestamp |  |
| market_tide | 2026-03-27 | 200 | 81 | 2026-03-27 | 2026-03-27 | date, net_call_premium, net_put_premium, net_volume, timestamp |  |
| market_tide | 2025-09-26 | 200 | 81 | 2025-09-26 | 2025-09-26 | date, net_call_premium, net_put_premium, net_volume, timestamp |  |
| market_tide | 2024-10-25 | 200 | 81 | 2024-10-25 | 2024-10-25 | date, net_call_premium, net_put_premium, net_volume, timestamp |  |
| earnings_hist | today | 200 | 107 | 1999-05-18 | 2026-11-18 | actual_eps, ending_fiscal_quarter, expected_move, expected_move_perc, long_straddle_1d, long_straddle_1w, post_earnings_move_1d, post_earnings_move_1w, post_earnings_move_2w, post_earnings_move_3d, pre_earnings_move_1d, pre_earnings_move_1w, pre_earnings_move_2w, pre_earnings_move_3d, report_date, report_time, short_straddle_1d, short_straddle_1w, source, street_mean_est |  |
| stock_info | today | 200 | 1 |  |  | announce_time, avg30_volume, beta, full_name, has_dividend, has_earnings_history, has_investment_arm, has_options, issue_type, logo, marketcap, marketcap_size, next_earnings_date, outstanding, sector, short_description, short_name, symbol, uw_tags |  |
| net_prem_ticks | today | 200 | 390 | 2026-09-25 | 2026-09-25 | call_volume, call_volume_ask_side, call_volume_bid_side, date, net_call_premium, net_call_volume, net_delta, net_put_premium, net_put_volume, put_volume, put_volume_ask_side, put_volume_bid_side, tape_time |  |
| net_prem_ticks | 2026-03-27 | 200 | 390 | 2026-03-27 | 2026-03-27 | call_volume, call_volume_ask_side, call_volume_bid_side, date, net_call_premium, net_call_volume, net_delta, net_put_premium, net_put_volume, put_volume, put_volume_ask_side, put_volume_bid_side, tape_time |  |
| net_prem_ticks | 2025-09-26 | 200 | 390 | 2025-09-26 | 2025-09-26 | call_volume, call_volume_ask_side, call_volume_bid_side, date, net_call_premium, net_call_volume, net_delta, net_put_premium, net_put_volume, put_volume, put_volume_ask_side, put_volume_bid_side, tape_time |  |
| net_prem_ticks | 2024-10-25 | 200 | 390 | 2024-10-25 | 2024-10-25 | call_volume, call_volume_ask_side, call_volume_bid_side, date, net_call_premium, net_call_volume, net_delta, net_put_premium, net_put_volume, put_volume, put_volume_ask_side, put_volume_bid_side, tape_time |  |
| multi_leg | today | 200 | 5 | 2026-09-25 | 2026-09-25 | all_opening_legs, all_otm, avg_iv, bid_ask_spread, breakevens, code, diff_expirations, diff_strikes, diff_types, direction, executed_at, id, iv_term_spread, ivs, leg_count, max_dte, max_loss, max_profit, max_strike, min_dte, min_strike, net_ask, net_bid, net_delta, net_gamma |  |
| daily_report | today | 200 | 1 | 2026-09-25 | 2026-09-25 | catalysts, date, flow, skew, stock_movers, tide, unusual_options, vol |  |
| daily_report | 2026-03-27 | 200 | 1 | 2026-03-27 | 2026-03-27 | catalysts, date, flow, skew, stock_movers, tide, unusual_options, vol |  |
| daily_report | 2025-09-26 | 200 | 1 | 2025-09-26 | 2025-09-26 | catalysts, date, flow, skew, stock_movers, tide, unusual_options, vol |  |
| daily_report | 2024-10-25 | 200 | 1 | 2024-10-25 | 2024-10-25 | catalysts, date, flow, skew, stock_movers, tide, unusual_options, vol |  |
| option_contracts | today | 200 | 5 |  |  | ask_volume, avg_price, bid_volume, delta, floor_volume, gamma, high_price, implied_volatility, last_price, last_tape_time, low_price, mid_volume, multi_leg_volume, nbbo_ask, nbbo_bid, no_side_volume, open_interest, option_symbol, prev_oi, rho, stock_multi_leg_volume, sweep_volume, theta, total_premium, vega |  |
| insider_ticker | today | 200 | 34 |  |  | cik, display_name, id, is_person, logo_url, name, name_slug, social_links, ticker |  |
| congress_unusual | today | 422 | 0 |  |  |  | 422 /api/congress/unusual-trades: {"path":"/api/congress/unusual-trades","msg":"Missing access for unusual trades. This  |
| full_tape | today | skipped | 0 |  |  |  | large download — test manually |

## Decisions (2026-09-27, Basic plan)

1. **Flow alerts are historical** — `newer_than`/`older_than` with ISO dates return alerts back to at least 2024-10-25. Backtest sample source = flow alerts. Each alert has a UUID `id`.
2. **Backtestable:** `gex_levels` (by `date`), `dp_price_levels` (by `date`), `market_tide` (by `date`), `iv_rank` (`date` + `timespan=1y` returns the year ending at `date` → two calls cover 2 years). All checks except `unusualness` are backtestable.
3. **OHLC:** `/ohlc/1d?timeframe=3Y&limit=2500` returns ~754 regular-session bars (back to 2023-09) plus pre/post rows; filter `market_time == "r"`; the day is in the `date` field (no `start_time`).
4. **Rate limits:** 40,000/day; per-minute limit effectively unbounded (header reports 1,000,000).
5. **Live-only:** `unusualness` (no date param). `option_stance` needs a `stance` param (Plan 3). `congress/unusual-trades` is **not included** in Basic (422) → C11 smart-money uses `insider` instead if built.
