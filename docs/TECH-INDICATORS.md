# Signal results by the stock's own RSI and 50-day trend (EXPLORATORY, 2026-10-11)

**Question (owner, parked 10-07):** can classic technical indicators on the signal stock add a confluence note to the
card? Two were tested: RSI and "stock above its own 50-day average". Prior (old WhaleProof engine, train): SPY
above/below its 50-day made no difference (46.6% vs 46.9% beat SPY); the old engine's price-stretch check
(`chase_guard`, not part of the WhaleProof filter) did help (55.1%).

**Method.** Finished tracker signals, stored daily bars only (no UW calls), closes up to and including the signal day
(known at that close; entry is the next open). Groups fixed and committed before any outcome was looked at (`f8d0b1d`):
- **RSI(14), Wilder, read in the bet's direction** (bearish bet → 100 − RSI): *stretched* ≥ 70 (stock already ran
  hard the bet's way) vs *rest* < 70. Also counted, as info: *washed out* ≤ 30.
- **50-day trend:** *with* = close on the bet's side of its 50-day average (bullish above, bearish below) vs *against*.

Outcome = the tested trade (next open → 5th-session close, −0.10%) vs SPY. Ranges: 1,000× bootstrap over signal days.
Pre-declared read: a split counts only if it points the same way in the practice year and the sealed test, with the
sealed-test range of the gap excluding zero. Filter untouched.

**Coverage.** 1,687 of 1,696 finished signals have an RSI; 1,645 have a 50-day average (51 had under 50 bars).

| Split | Practice year | Sealed test | Recent months | Second sealed test |
|---|---|---|---|---|
| RSI stretched / rest | +1.72% (147) / +0.69% (339) | **−0.05% (134) / +1.85% (493)** | −1.29% (31) / −1.37% (298) | +3.09% (49) / +1.47% (183) |
| 50-day with / against | +0.42% (356) / +1.23% (118) | +1.39% (418) / +1.25% (206) | −1.28% (180) / −1.57% (143) | +1.48% (151) / +1.96% (60) |
| RSI washed out (info) | −0.27% (8) | +10.32% (7) | +0.23% (6) | +1.34% (6) |

(average per trade vs SPY, trades in brackets.) Sealed-test gaps: RSI stretched − rest −4.69% … +0.92%;
50-day with − against −1.73% … +1.94%. Every gap range in every period includes zero.

**Conclusion.**
- **RSI: no pattern.** Stretched did better in the practice year and the second sealed test, worse in the sealed test,
  the same in the recent months. Flips sign → noise.
- **50-day trend: no pattern.** Against the trend did a bit better in the practice year, with the trend a bit better in
  the sealed test; gaps are tiny next to their ranges.
- **Washed out:** 6–8 trades per period, far too few to read anything into the +10% sealed-test number.

**So no card note.** Neither indicator says anything about how a signal will do once it has passed the filter. That
fits the old engine's SPY-50-day null. The old engine's price-stretch check helped on train, but RSI stretch on
WhaleProof signals shows no consistent effect. The tested rule (buy every signal at the next open) stays.

**Reproduce.** Desk API up (`scripts/desk.sh up`), then
`cd backend && uv run python scripts/research/tech_indicators.py` → `journal/research/tech-indicators.json`
(historical rows stay fixed; Live and All-periods rows shift as live signals finish) (or pass a saved `/api/desk/tracker` JSON; this run used a cache-only API, `whaleproof serve --port 8199 --no-live`).
