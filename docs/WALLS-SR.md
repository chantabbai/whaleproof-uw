# Do call/put walls act as support and resistance?

_Exploratory (after the one-time holdout; nothing in the frozen filter changed). Script
`backend/scripts/research/walls_sr.py` → `journal/research/walls-sr.json`. Cache-only, 0 UW calls. Run 2026-10-03._

## Short answer
**No effect shows up on daily closes.** When price reaches a UW put wall, it holds there about as often as at a nearby
plain strike: 51.7% vs 51.1%. Call walls: 51.9% vs 51.0%. The held difference falls within about ±3 points, which rules
out a big support or resistance effect. Smaller effects, or intraday ones, weren't tested.
Bounces and follow-through after a break look the same as at plain strikes. The one steady difference is that walls get
**reached a little more often**, by 1.4–1.7 points. That reads more like a weak pull toward the level than a barrier,
and it is not proven (see Caveats).

## Method
- **Walls:** daily UW `gex-levels` (`source=oi`, stamped about 15:59 ET on day D), so they are known by D's close. They
  are tested on the next 5 sessions, D+1 to D+5, using daily bars only.
- **Events:** put wall below D's close = support candidate; call wall above = resistance candidate. Distance is in
  14-day ATR units. Walls more than 3 ATR away are dropped (6,229, e.g. AAPL put wall at 100). So are walls on the
  wrong side of the close (740). Walls barely move, so there is one event per ticker and side until the level changes
  or 5 sessions pass (5,212 repeats removed). **15,118 events** remain from 933 tickers, 2024-10 → 2026-09.
- **Control (placebo):** up to 3 fake levels per event, on the same ticker, day and side. Their distance is drawn
  from the real walls' distances, and each is **snapped to the wall's own strike grid**, so round numbers are compared
  with round numbers. Each sits at least 0.25 ATR from either wall, the gamma flip and the magnet. Real and placebo are
  compared within 8 distance buckets (0–0.25 … 2.5–3 ATR), weighted by the real counts.
- **Measures:** *reached* = low ≤ level (support) / high ≥ level (resistance) within 5 sessions · *held* = on the first
  day it is reached, the close stays on the original side (an open already through the level is a gap, left out:
  daily bars can't tell; about 34% of reached days are gaps) · *bounce 3d* = close 3 sessions after that day vs the level, in the bounce direction ·
  *after a break* = close 3 sessions after the first close through the level, in the break direction.
- **Ranges:** 95% ranges of real − placebo from a 5-day block bootstrap over event dates.

## Result — all events
| | Reached in 5 days | Held when reached | Bounce 3 days later | After a break, 3 days |
|---|---|---|---|---|
| **Put wall (support)** wall vs plain strike | 68.8% vs 67.2% | 51.7% vs 51.1% | +0.40% vs +0.04% | −0.37% vs −0.39% |
| difference (95% range) | **+1.7 pts (+0.4 … +2.9)** | +0.6 pts (−1.7 … +3.1) | +0.36% (−0.14 … +0.86) | +0.02% (−0.35 … +0.40) |
| **Call wall (resistance)** wall vs plain strike | 55.1% vs 53.7% | 51.9% vs 51.0% | −0.32% vs −0.35% | +0.03% vs +0.10% |
| difference (95% range) | **+1.4 pts (+0.5 … +2.5)** | +0.9 pts (−1.5 … +3.3) | +0.03% (−0.33 … +0.41) | −0.07% (−0.41 … +0.25) |

Put walls: 8,019 events, about 5,520 reached within 5 sessions, and 3,623 hold tests after gap days were removed.
Call walls: 7,099 events, about 3,910 reached, and 2,555 hold tests.

## By period and group (difference wall − plain strike; range in brackets)
| Group | Put: reached | Put: held | Put: bounce 3d | Call: reached | Call: held | Call: bounce 3d |
|---|---|---|---|---|---|---|
| Train 2024-10 → 2025-09 | +1.7 (+0.2…+3.2) | +0.6 (−2.7…+3.7) | +0.18% (−0.43…+0.82) | +1.9 (+0.5…+3.3) | +2.5 (−1.2…+6.0) | −0.13% (−0.62…+0.36) |
| Holdout 2025-10 → 2026-05 | +0.8 (−1.4…+2.9) | +1.0 (−3.0…+4.7) | +0.48% (−0.35…+1.34) | +0.7 (−1.0…+2.7) | −0.4 (−4.6…+3.4) | +0.21% (−0.46…+0.77) |
| Post 2026-06 → 09 | +3.7 (+0.2…+7.7) | +0.3 (−7.5…+7.4) | +0.67% (−0.87…+1.41) | +1.6 (−0.7…+4.1) | −2.9 (−9.8…+2.3) | +0.20% (−0.81…+1.43) |
| Index ETFs (SPY, QQQ, IWM…) | +4.9 (−0.6…+11.5) | −8.6 (−19.4…+2.1) | +0.03% (−1.25…+1.31) | +4.8 (+1.2…+8.1) | −0.4 (−8.8…+7.0) | +0.41% (−0.33…+0.99) |
| Single stocks | +1.5 (+0.3…+2.8) | +1.2 (−1.3…+3.8) | +0.43% (−0.08…+0.95) | +1.0 (+0.0…+2.1) | +1.5 (−1.0…+3.9) | −0.06% (−0.41…+0.34) |

Counting each ticker equally (tickers with ≥ 10 hold tests), walls hold more often than plain strikes on 48% of
tickers for puts (65 tickers) and 56% for calls (55). That is about a coin flip.

## Reading
- **Not support or resistance on daily closes.** Once price gets to a wall, it closes through it about as often as
  through any nearby round strike, in every period and group. Every "held" range includes zero. On index ETFs, put
  walls actually held less often (−8.6 points, range still includes zero).
- **Slightly "sticky".** Walls get reached 1–2 points more often than plain strikes at the same distance, and about 5
  points more on index ETFs. That fits gamma pinning, a pull toward heavy-OI strikes, more than a barrier. It is small,
  the holdout range touches zero, and residual distance mismatch could explain part of it.
- **For the dashboard:** don't use walls as stop or target levels. The ticker page note now says this was tested and didn't
  hold up.

## Caveats
- **Daily bars only.** Intraday touches and reversals are invisible, and gap opens through the level are excluded.
- **Selection:** most tickers have GEX only on days with big flow, because the backfill fetched it for flow tickers.
  SPY, QQQ, NVDA and TSLA have ~470–497 days each; most others have far fewer.
- **Distance matching** is good but not perfect. Real walls sit about 0.01–0.03 ATR closer than placebos in the same
  bucket, which slightly favours "reached" for walls.
- The by-distance tables in the JSON have 8 buckets × 5 measures × 2 sides. A few cells look good by chance (for
  example, put walls at 0.75–1.5 ATR). Those are post-hoc and not findings.
- Walls are OI-based (previous close OI). Volume-based or intraday walls weren't tested. Gamma flip and magnet levels
  weren't tested either (possible follow-up).

## Reproduce
`cd backend && uv run python scripts/research/walls_sr.py` (about 20 s, cache only).
