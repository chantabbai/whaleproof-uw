# Signal results by gamma position (EXPLORATORY, 2026-10-06)

**Question (owner, looking at AMAT 10-05):** close 529.98, just under the 532.18 gamma flip, call wall 560, put wall
520. Can the dashboard say "enter" or "wait" based on gamma?

**Method.** Finished tracker signals that have UW `gex-levels` for the signal day (stamped ~15:59 ET, so known before
the next-open entry). Three splits, thresholds fixed before looking: price **above / below the gamma flip**; **call
wall** within 3% above the close (*near*) or further (*far*); **put wall** within 3% below (*near*) or further (*far*).
Outcome = the tested trade (next open → 5th-session close, −0.10%) vs SPY. Ranges: 1,000× bootstrap over signal days.
Pre-declared read: a split counts only if it points the same way in the practice year and the sealed test, with the
sealed-test range of the gap excluding zero. Cache only. Filter untouched.

**Coverage.** 507 of 1,681 finished signals (30%). UW keeps levels mostly on big-flow days, and none before Oct 2024,
so the second sealed test is missing and the groups are small.

| Split | Practice year | Sealed test | Recent months |
|---|---|---|---|
| Above flip / below flip | +0.25% (141) / +1.83% (55) | +1.62% (141) / +1.08% (48) | +0.30% (57) / +0.27% (43) |
| Call wall near / far | −2.10% (63) / +2.04% (130) | +1.61% (67) / +1.45% (120) | −0.18% (32) / +0.35% (69) |
| Put wall near / far | +0.89% (95) / +0.28% (93) | **+2.69% (100) / −0.17% (82)** | +0.07% (47) / +0.20% (46) |

(average per trade vs SPY, trades in brackets.) Sealed-test gap, put wall near − far: +0.40% … +5.36%.

**Conclusion.**
- **Gamma flip: no pattern.** Below the flip did better in the practice year and worse in the sealed test.
- **Call wall close above: no pattern.** Clearly worse in the practice year, about the same in the sealed test.
- **Put wall close below: a hint, not a rule.** Better in the practice year and clearly better in the sealed test, so it
  passes the pre-declared check. But it reverses (slightly) in the recent months. It's one hit out of three splits,
  on 30% of signals, after the holdout. That's how chance findings look too.

**So the dashboard should not say enter or wait from gamma.** The tested rule buys every signal at the next open.
Levels stay on the ticker page as reference points. **Owner decision 10-06:** the put-wall hint is NOT shown on the
signal card (too weak; it would invite second-guessing the tested rule). It lives in this note only.

**Reproduce.** Desk API up (`scripts/desk.sh up`), then
`cd backend && uv run python scripts/research/gamma_position.py` → `journal/research/gamma-position.json`.
