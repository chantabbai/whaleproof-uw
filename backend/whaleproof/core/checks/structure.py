from __future__ import annotations

from whaleproof.core.data_layer.context import AlertContext

from .base import CheckResult, clip, human, money, unavailable

DP_BAND = 0.03
TIDE_SCALE = 5e8
EVENT_WINDOW_DAYS = 7


def gamma_room(ctx: AlertContext) -> CheckResult:
    g = ctx.gex
    if g is None:
        return unavailable("gamma_room")
    a, s, em = ctx.alert, ctx.alert.underlying_price, ctx.expected_move
    wall = g.call_wall if a.direction > 0 else g.put_wall
    regime_txt = ""
    conf = 0.8
    if g.gamma_flip is not None:
        if s < g.gamma_flip:
            regime_txt, conf = "; spot below flip → negative gamma, moves amplify", 1.0
        else:
            regime_txt = "; spot above flip → positive gamma, moves dampen"
    if wall is None:
        return CheckResult("gamma_room", 0.0, conf, reason="no wall on this side" + regime_txt)
    room = (wall - s) / em if a.direction > 0 else (s - wall) / em
    room = max(room, 0.0)
    side = "call wall" if a.direction > 0 else "put wall"
    return CheckResult("gamma_room", clip((room - 0.5) / 0.5, -1, 1), conf,
                       reason=f"{side} {wall:g} is {room:.1f}× expected move away{regime_txt}")


def dark_pool(ctx: AlertContext) -> CheckResult:
    if not ctx.dp_levels:
        return unavailable("dark_pool")
    s = ctx.alert.underlying_price
    below = sum(v for p, v in ctx.dp_levels if s * (1 - DP_BAND) <= p <= s)
    above = sum(v for p, v in ctx.dp_levels if s < p <= s * (1 + DP_BAND))
    if below + above == 0:
        return CheckResult("dark_pool", 0.0, 0.5, reason="no dark-pool volume within ±3% of spot")
    raw = (below - above) / (below + above)
    where = "support below" if raw > 0 else "supply above"
    return CheckResult("dark_pool", raw * ctx.alert.direction,
                       reason=f"dark-pool {where} spot ({human(below)} vs {human(above)} shares within 3%)")


def vol_price(ctx: AlertContext) -> CheckResult:
    if ctx.iv_rank is None:
        return unavailable("vol_price")
    r = ctx.iv_rank
    score = clip((50 - r) / 40, -1, 1)
    hint = " — premium rich, prefer a debit spread" if r >= 70 else " — premium cheap" if r <= 30 else ""
    return CheckResult("vol_price", score, reason=f"IV rank {r:.0f}{hint}")


def unusualness(ctx: AlertContext) -> CheckResult:
    if ctx.unusual_pct is None:
        return unavailable("unusualness")
    p = ctx.unusual_pct
    return CheckResult("unusualness", clip((p - 50) / 40, -1, 1),
                       reason=f"option volume at {p:.0f}th percentile of its 90-day history")


def regime(ctx: AlertContext) -> CheckResult:
    if ctx.tide is None:
        return unavailable("regime")
    s = clip(ctx.tide / TIDE_SCALE, -1, 1) * ctx.alert.direction
    word = "bullish" if ctx.tide > 0 else "bearish"
    return CheckResult("regime", s, 0.6, reason=f"market tide {word} (net {money(ctx.tide)})")


def catalyst(ctx: AlertContext) -> CheckResult:
    a = ctx.alert
    upcoming = [e for e in ctx.earnings if a.session_date < e <= a.expiry]
    if not upcoming:
        return CheckResult("catalyst", 0.2, reason="no earnings before expiry")
    e = upcoming[0]
    if (a.expiry - e).days <= EVENT_WINDOW_DAYS:
        return CheckResult("catalyst", 0.0, reason=f"earnings {e} just before expiry — event bet",
                           tags=("event_trade",))
    return CheckResult("catalyst", -0.5, reason=f"earnings {e} inside option life — IV crush risk")
