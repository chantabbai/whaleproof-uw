# Is the edge just market beta?

_Exploratory (after the one-time sealed test; nothing was tuned). Script `backend/scripts/research/beta_adjusted.py` →
`journal/research/beta-adjusted.json`. Cache-only._

## Method
- **Beta per signal:** the slope of the stock's daily returns against the S&P 500's (SPY), over the 120 sessions up to the flow day. It is
  point-in-time and needs at least 20 days. A few new listings are skipped (CRCL, CRWV, CBRS, FRMI, SKHY, SPCH, SPCX,
  ALAB early on: 2–7 signals per period).
- **Beta-adjusted return:** the five-day stock return in the signal direction, net of 0.10% costs, minus beta × the S&P
  500's return over the same days. The plain result assumes beta = 1 (the stock moves one-for-one with the S&P 500).
- **Ranges:** per-day 95% ranges from the same 5-day block bootstrap as the evidence table.

## Result (same rows for both columns)
| Period | Signals' average beta | Plain result | **Beta-adjusted** | Per-day 95% range | All alerts, beta-adjusted |
|---|---|---|---|---|---|
| Second sealed test, 2023-10 → 2024-09 | 2.12 | +1.83% | **+1.54%** | −0.37 … +3.42 | −0.08% |
| Practice year, 2024-10 → 2025-09 | 2.26 | +1.00% | **+0.79%** | −0.21 … +2.73 | −0.10% |
| Sealed test, 2025-10 → 2026-05 | 2.43 | +1.38% | **+0.57%** | −0.73 … +1.65 | −0.05% |
| Recent months, 2026-06 → 09-22 | 2.42 | −1.28% | **−0.73%** | −2.02 … +1.23 | −0.15% |

By signal type, beta-adjusted:

| Signal type | Second sealed test | Practice year | Sealed test | Recent months |
|---|---|---|---|---|
| Long shots | +1.95% | +0.90% | +0.85% | −1.13% |
| Whale-size bets | +0.43% | +0.40% | −0.27% | +0.17% |

## Reading
- **Signals are high-beta.** They swing 2.1–2.4× as much as the S&P 500; all alerts average 1.4–1.6×.
- **After adjusting for beta, signals still beat all alerts in the same 3 of 4 periods, but the edge shrinks.** In the
  sealed test it falls from +1.38% to +0.57%, so roughly 60% of the sealed-test gap was beta. The second sealed test holds up best.
- **Beta explains about 40% of the loss in the recent months.** Signals still lost −0.73% per trade after adjusting.
- **Whale-size bets are mostly beta.** Long shots keep a positive beta-adjusted result in 3 of 4 periods.
- **Every range includes 0.** The edge is still **not proven**.
- **New listings matter.** In the practice year, the 18 signals without 60 days of history (mostly recent IPOs) averaged about +17%
  each. A filter that buys fresh listings is partly a bet on IPO momentum.

Rerun the numbers: `cd backend && uv run python scripts/research/beta_adjusted.py`.
