# Buy after hours on the signal day instead of the next open? (EXPLORATORY, 2026-10-06)

**Question (owner, 10-06):** next-morning open interest didn't change the decision (`docs/OI-CONFIRM.md`), so why wait
for the next open? What if I buy after hours on the signal day?

**Method.** Every finished tracker signal (1,681). Same signals, same exit (close of the 5th session after the signal
day), same −0.10% cost; only the entry moves. *Next open* = the tested rule. *Same close* = the signal day's regular
close, used as the after-hours price. SPY is moved the same way (close→close vs open→close), so both versions are
measured against the market over matching windows. Ranges: 1,000× bootstrap over signal days. Cache only, no UW calls.
Post-holdout look; filter untouched.

| Period | Trades | Next open (tested) | Same-day close | Difference | Likely range of the difference |
|---|---|---|---|---|---|
| Second sealed test (2023–24) | 233 | +1.74% | +1.54% | −0.20% | −0.62% … +0.19% |
| Practice year | 488 | +1.23% | +1.46% | +0.24% | −0.07% … +0.56% |
| Sealed test | 628 | +1.43% | +1.60% | +0.17% | −0.10% … +0.45% |
| Recent months | 332 | −1.50% | −1.52% | −0.02% | −0.43% … +0.40% |
| All periods | 1,681 | +0.83% | +0.94% | +0.10% | −0.08% … +0.27% |

(per trade, stock vs SPY over the same days, after costs.) Overnight gap in the signal's direction: mean +0.15%, median
+0.09%, up 52% of the time; 8% of signals gapped more than 5% either way.

**Conclusion.** Buying the same evening would have done about the same: +0.10% a trade better on average, but two
periods better and two worse, and every range includes zero. That +0.10% is also a best case. After hours, spreads are
wider and books thinner (not measured here; no extended-hours quotes in the cache), and a spread of a few tenths of
a percent would eat the whole gap.
**Keep the next-open rule.** The reason isn't the open interest. The next open is what was tested, and it's the first
liquid price after the day's flow is final (4:15 PM ET).

If you do buy after hours anyway: use a limit order near the close, small size, and expect results close to the
tested ones, not better. About 1 in 12 signals moves more than 5% overnight, in either direction.

**Caveats.** The close stands in for after-hours prices (no extended-hours bars in the cache). The list is final only
after the session ends, so a buy *at* the 4:00 PM close couldn't use it; after hours (once the list is final) is the
realistic version. Exploratory, after the holdout, same signals as the tested rule.

**Reproduce.** Desk API up (`scripts/desk.sh up`), then
`cd backend && uv run python scripts/research/entry_timing.py` → `journal/research/entry-timing.json`.
