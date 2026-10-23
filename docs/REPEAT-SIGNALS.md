# Repeat signals: same ticker again while the first hold is open (exploratory, 2026-10-19)

**Question (owner, 10-19):** Sightings showed EWY twice (day 1 and day 2). When a ticker signals again while its
first 5-session hold is still open, should you double down?

**Method.** Unit = one ticker-session (same ticker + same day share one entry, so they count once). "Repeat" = the
ticker already had a signal in the previous 4 sessions. Outcome = 5-session stock return in the signal direction minus
SPY, entry next open, 0.10% cost. Cache only. Run after the frozen filter's single holdout test, so this is exploratory.

| Period | First signal (no open hold) | Repeat (earlier hold open) |
|---|---|---|
| Second sealed test (Oct 2023–Sep 2024) | 211 · mean +1.83% · median +0.60% · win 53% | 22 · +0.92% · −0.62% · 45% |
| Practice year (Oct 2024–Sep 2025) | 411 · +0.86% · +0.34% · 53% | 77 · **+3.16%** · +3.02% · 60% |
| Sealed test (Oct 2025–May 2026) | 537 · +1.57% · +0.58% · 53% | 91 · +0.62% · +0.03% · 51% |
| Recent months (Jun–Sep 2026) | 280 · −1.45% · −1.97% · 41% | 44 · −2.06% · −2.30% · 39% |

**Conclusion.** No. Repeats beat first signals only in the practice year. They did worse in the other three periods,
including both sealed tests. Doubling down also doubles exposure to one name. The repeat counts are small (22–91),
so this does not prove repeats are worse either. Treat a repeat as the same bet, not a stronger one.

**Caveats.** Exploratory. Small repeat samples. Same-stock overlapping holds are correlated. Stock only (not options).
This matches the older alert-level check (repeat buyers +0.1% vs other clean buys +0.3%, `STOCK-VS-OPTIONS.md` §6).

**Reproduce:** `cd backend && PYTHONPATH=scripts/research uv run python scripts/research/repeat_signals.py` →
`journal/research/repeat-signals.json`
