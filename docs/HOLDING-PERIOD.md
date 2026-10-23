# Holding period: why sell after 5 days? (exploratory)

**Status: exploratory.** The sealed test (Oct 2025 – May 2026) was already opened once for the 5-day rule, so nothing
here can change the official result. The 5-day exit and the frozen filter stay as they are.
Run 2026-10-01 at the owner's request ("why 5 days, not 10, 20, 30?").

## Method
- **Signals:** the same signals the evidence uses: the frozen filter over the cached history rows.
- **The trade:** buy the stock at the next session's open and sell at the close of session H, for H = 5, 10, 20 and 30.
  The result is the move in the signal's direction minus the S&P 500 (SPY) over the same days, minus 0.10% costs. This
  is the same definition as the official 5-day number; H = 5 reproduces it exactly in all four periods (max difference 0).
- **Same trades for every H:** a trade counts only if it has 30 sessions of prices after it. That drops 2 signals in
  2023–24 and 88 recent signals (from mid-August 2026 on). So the recent 5-day row here is 230 trades, not 318.
- **Likely range:** 95% range of the average signal day, by moving-block bootstrap with block = H (holds overlap).
  It is blank when there are too few days.
- **Earnings:** the filter only blocks reports inside the 5-day hold. The table shows the share of signals with a
  report inside the longer hold.
- **Baseline:** the same calculation for every directional UW alert.
- **Not covered:** this is not adjusted for beta. Signal stocks swing about 2.3× as much as the S&P 500
  (`docs/BETA-CHECK.md`), so in a rising market the longer holds pick up more of that extra swing.

## Results (signals; avg = average per trade vs S&P 500 after costs)

| Period | Hold | Trades | Avg | Avg per day held | Win rate | Likely range (avg signal day) | Every alert | Earnings inside |
|---|---|---|---|---|---|---|---|---|
| Second sealed test 2023–24 | 5 | 231 | +1.77% | +0.35% | 52% | −0.21% to +3.79% | −0.07% | 0% |
| | 10 | 231 | +3.25% | +0.33% | 53% | −0.69% to +5.20% | −0.07% | 6% |
| | 20 | 231 | +3.85% | +0.19% | 54% | −2.22% to +3.99% | 0.00% | 21% |
| | 30 | 231 | +5.48% | +0.18% | 50% | −3.87% to +6.37% | +0.04% | 34% |
| **Practice year 2024–25** | 5 | 488 | +1.22% | +0.25% | 54% | **+0.47% to +3.21%** | −0.09% | 0% |
| | 10 | 488 | +2.89% | +0.29% | 54% | **+0.72% to +6.64%** | −0.04% | 8% |
| | 20 | 488 | +3.59% | +0.18% | 49% | −1.20% to +10.31% | +0.07% | 19% |
| | 30 | 488 | +4.10% | +0.14% | 50% | −2.66% to +13.66% | +0.12% | 31% |
| Sealed test 2025–26 | 5 | 628 | +1.43% | +0.29% | 53% | −0.06% to +2.41% | −0.03% | 0% |
| | 10 | 628 | +1.74% | +0.17% | 51% | −0.60% to +5.06% | −0.04% | 7% |
| | 20 | 628 | +2.17% | +0.11% | 51% | −2.51% to +6.84% | −0.04% | 27% |
| | 30 | 628 | +3.00% | +0.10% | 47% | −1.78% to +9.50% | +0.14% | 41% |
| Recent months Jun–Sep 2026 | 5 | 230 | −1.95% | −0.39% | 40% | −3.23% to +1.28% | −0.17% | 0% |
| | 10 | 230 | −2.43% | −0.24% | 45% | −5.62% to +1.82% | −0.17% | 7% |
| | 20 | 230 | −5.57% | −0.28% | 40% | −14.85% to +2.01% | −0.28% | 17% |
| | 30 | 230 | −5.55% | −0.19% | 42% | too few days | −0.18% | 35% |

## Conclusion
- **Longer holds make more per trade but less per day held.** At 20 and 30 days the gain per day held is about half the
  5-day rate, and the win rate falls to about 50%.
- **Risk grows fast with the hold.** The likely range widens 3–5×. Only 5 and 10 days stay above zero, and only in the
  practice year; 20 and 30 days include zero in every period. Losses grow too: the recent months lose −5.6% per trade
  at 20 days vs −2.0% at 5.
- **Earnings sneak back in.** 20–41% of the longer holds include an earnings report, the event the filter was built to
  avoid.
- **Practice year (the only fair place to choose):** 5 and 10 are a tie. By average per trade, 10 earns slightly more
  per day held (+0.29% vs +0.25%). By the average signal day, 5 does (+0.36% vs +0.35%). Both ranges stay above zero.
  In the sealed test, 10 days did worse per day held than 5 (+0.17% vs +0.29%).
- **Recommendation: keep 5 days.** It is the one-week horizon the research describes. It earns the most or ties per day
  held, keeps earnings out, and has the narrowest range. A 10-day hold is a reasonable variant for someone who trades
  less often, but it is **not proven** better, and its sealed-test result is weaker.
- **Not proven at any length:** in the sealed test every hold's range includes zero.

## Caveats
- Exploratory and after the fact: every period here has been looked at before.
- The returns are not adjusted for beta. Longer holds of high-beta stocks in a rising market look better than they are.
- With 20 and 30 days, signals from the same weeks share most of their price path, so the counts overstate how much
  independent evidence there is (the block bootstrap only partly allows for this).
- The recent months lose 88 signals for lack of future prices.

## Reproduce
```bash
cd backend && uv run python scripts/research/holding_period.py   # → journal/research/holding-period.json (cache only)
uv run pytest -q tests/unit/test_research_holding_period.py
```
