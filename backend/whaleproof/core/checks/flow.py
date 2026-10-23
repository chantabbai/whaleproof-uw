from __future__ import annotations

import math

from whaleproof.core.data_layer.context import AlertContext

from .base import CheckResult, clip, money, unavailable

MIN_LIQUIDITY = 500


def flow_quality(ctx: AlertContext) -> CheckResult:
    a = ctx.alert
    if a.direction == 0:
        return CheckResult("flow_quality", 0.0, hard_fail=True,
                           reason="direction ambiguous (mixed sides or multi-leg)")
    s_prem = clip(math.log10(a.total_premium / 100_000), 0, 1)           # $100k→0, $1M→1
    side = max(a.ask_share, a.bid_share)
    s_side = clip((side - 0.6) / 0.3, 0, 1)                               # 60%→0, 90%→1
    opening = a.all_opening or (a.volume_oi_ratio or 0) > 1 or (
        a.total_size is not None and a.open_interest is not None and a.total_size > a.open_interest)
    s_dte = 1.0 if 7 <= a.dte <= 90 else (0.5 if a.dte > 90 else 0.0)
    m = a.otm_pct
    s_otm = 1.0 if 0 <= m <= 0.15 else 0.5 if -0.05 <= m < 0 else 0.3 if 0.15 < m <= 0.30 else 0.0
    raw = 0.30 * s_prem + 0.25 * s_side + 0.25 * opening + 0.10 * s_dte + 0.10 * s_otm + (0.10 if a.has_sweep else 0)
    raw = clip(raw, 0, 1)
    side_word = "ask" if a.ask_share >= a.bid_share else "bid"
    reason = (f"{money(a.total_premium)} {a.kind}s, {side*100:.0f}% {side_word}-side, "
              f"{'opening' if opening else 'not clearly opening'}, {a.dte} DTE, {m*100:+.1f}% OTM"
              f"{', sweep' if a.has_sweep else ''}")
    return CheckResult("flow_quality", 2 * raw - 1, reason=reason)


def persistence(ctx: AlertContext) -> CheckResult:
    n = ctx.same_dir_recent
    return CheckResult("persistence", min(n, 3) / 3,
                       reason=f"{n} other same-direction alerts in last 3 sessions")


def liquidity(ctx: AlertContext) -> CheckResult:
    a = ctx.alert
    if a.open_interest is None and a.volume is None:
        return unavailable("liquidity", "OI and volume unknown")
    depth = max(a.open_interest or 0, a.volume or 0)
    ok = depth >= MIN_LIQUIDITY
    return CheckResult("liquidity", 0.0, hard_fail=not ok,
                       reason=f"OI {a.open_interest}, vol {a.volume}" + ("" if ok else " — too thin to trade"))


def chase_guard(ctx: AlertContext) -> CheckResult:
    if ctx.ref_price is None:
        return unavailable("chase_guard", "no entry price yet")
    a = ctx.alert
    move = (ctx.ref_price - a.underlying_price) * a.direction / ctx.expected_move
    if move > 1.0:
        return CheckResult("chase_guard", -1.0, hard_fail=True,
                           reason=f"already moved {move:.1f}× expected move — late")
    return CheckResult("chase_guard", clip(-move, -1, 0.5),
                       reason=f"entry {move:+.2f}× EM vs whale's price")
