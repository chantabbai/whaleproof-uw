# Next-morning open interest vs signal results (EXPLORATORY, 2026-10-05)

**Question (owner, pre-open 10-05):** MXL 10-02 signal: whale bought 1,496 Oct 16 $125 calls, but contract OI went
656 → 560 the next morning. Should a signal whose OI didn't grow still be bought?

**Method.** Every tracker signal (1,694; history + live). Groups by the dashboard's existing rule (`desk/oi.py`,
`CONFIRM_RATIO = 0.5`, set before this look): *confirmed* = OI(next session) − OI(flow day) ≥ 0.5 × whale size;
*weak* = grew by less; *fell* = went down; *unknown* = OI missing in cache. Outcome = tracker stock trade (next open →
5th close, −0.10%) minus SPY, closed rows only. Ranges: 1,000× bootstrap over signal days. Cache only, no UW calls.
Post-holdout look; filter untouched.

| Window | Confirmed | Weak | Fell | Unknown |
|---|---|---|---|---|
| Practice year | 462 · +1.12% | 8 · −0.86% | 10 · +9.05% | 8 · −0.30% |
| Sealed test | 596 · +1.58% | 11 · −2.98% | 3 · +2.12% | 18 · −0.73% |
| Recent months | 306 · −1.39% | 6 · −6.41% | 4 · +3.65% | 13 · −4.95% |
| All periods | 1,366 · +0.76% | 25 · −3.12% | 17 · +6.56% | 270 · +1.20% |

(trades · average vs SPY.) Unconfirmed (weak + fell), all periods: 42 trades, +0.80% vs confirmed +0.76%; difference
range −3.8% … +3.5%. Second sealed test (2023–24) has almost no OI in cache (231 of 233 unknown).

**Conclusion.** Unconfirmed is rare (≈2.5%) and indistinguishable from confirmed. "Fell" did *better* (17 trades),
"weak" worse (25), both too few and pointing opposite ways → noise. **Keep as card context, not a filter. Not proven
either way.** Rule unchanged: the tested trade buys MXL anyway.

**UI.** Signal card (OI fact) shows the record line when OI didn't grow; Methodology → details `#oi` shows the table.

**Caveats.** Exploratory, after the holdout; groups tiny; OI coverage partial before 2024-10; recent months overall negative.

**Reproduce.** Desk API up (`scripts/desk.sh up`), then `cd backend && uv run python scripts/research/oi_confirm.py`
→ `journal/research/oi-confirm.json`.
