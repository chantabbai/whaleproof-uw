"""Plan 1.5 confluence checks: dark-pool blocks, ticker net premium, sector tide, insiders, next-morning OI."""
from __future__ import annotations

from whaleproof.core.data_layer.context import AlertContext

from .base import CheckResult, clip, human, money, unavailable

INSIDER_BUY_SCORE = 0.8
INSIDER_SELL_SCORE = -0.3


def dp_blocks(ctx: AlertContext) -> CheckResult:
    b = ctx.dp_blocks
    if b is None:
        return unavailable("dp_blocks")
    sided = b["buy"] + b["sell"]
    if sided == 0:
        return CheckResult("dp_blocks", 0.0, 0.5, reason=f"{b['n']} $1M+ dark-pool blocks, none at bid/ask")
    raw = (b["buy"] - b["sell"]) / sided
    return CheckResult("dp_blocks", raw * ctx.alert.direction,
                       reason=f"$1M+ dark-pool blocks: {money(b['buy'])} at ask vs {money(b['sell'])} at bid")


def ticker_flow(ctx: AlertContext) -> CheckResult:
    n = ctx.net_prem
    if n is None or not n["gross"]:
        return unavailable("ticker_flow")
    raw = clip((n["call"] - n["put"]) / n["gross"], -1, 1)
    return CheckResult("ticker_flow", raw * ctx.alert.direction,
                       reason=f"ticker net premium today: calls {money(n['call'])}, puts {money(n['put'])}")


def sector_flow(ctx: AlertContext) -> CheckResult:
    t = ctx.sector_tide
    if t is None or not t["gross"]:
        return unavailable("sector_flow")
    raw = clip(t["net"] / t["gross"], -1, 1)
    return CheckResult("sector_flow", raw * ctx.alert.direction, 0.6,
                       reason=f"sector tide {'bullish' if t['net'] > 0 else 'bearish'} (net {money(t['net'])})")


def insider(ctx: AlertContext) -> CheckResult:
    # discretionary = total premium minus pre-scheduled 10b5-1 plan trades; sign: + buys, − sells
    disc = sum(p - p10 for _, p, p10 in ctx.insider)
    if disc > 0:
        return CheckResult("insider", INSIDER_BUY_SCORE * ctx.alert.direction, 0.5,
                           reason=f"insiders bought {money(disc)} (discretionary, last 90d)")
    if disc < 0:
        return CheckResult("insider", INSIDER_SELL_SCORE * ctx.alert.direction, 0.5,
                           reason=f"insiders sold {money(-disc)} (discretionary, last 90d)")
    return CheckResult("insider", 0.0, 0.5, reason="no discretionary insider trades in 90d")


def oi_confirm(ctx: AlertContext) -> CheckResult:
    a = ctx.alert
    size = a.total_size or a.volume
    if ctx.oi_next is None or not size:
        return unavailable("oi_confirm", "next-morning OI not published yet")
    before, after = ctx.oi_next
    ratio = (after - before) / size
    word = "opened (position held)" if ratio >= 0.5 else "not confirmed" if ratio >= 0 else "closed"
    return CheckResult("oi_confirm", clip(ratio, -1, 1),
                       reason=f"next-morning OI {human(before)}→{human(after)} vs {human(size)} traded — {word}")


def uw_flagged(ctx: AlertContext) -> CheckResult:
    """Same contract on UW's ≥$250K unusual list for D. Sign-neutral 1/0; the fit may flip it (fade)."""
    u = ctx.uw_unusual
    if u is None:
        return unavailable("uw_flagged", "UW unusual list not fetched")
    if ctx.alert.option_chain in set(u["symbols"]):
        return CheckResult("uw_flagged", 1.0, reason="contract on UW's unusual list today", tags=("uw_unusual",))
    if not u.get("complete"):
        return unavailable("uw_flagged", "UW unusual list truncated — absence unknown")
    return CheckResult("uw_flagged", 0.0, reason="not on UW's unusual list")
