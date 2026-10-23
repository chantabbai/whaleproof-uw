"""Conviction filter: one pure classifier for history rows and live alerts.

Stages, in order (the first failure is the reason shown on screen):
  gate        not a pure directional opening buy (hedge, spread leg, sold premium, closing, lotto …) — core/verdict/setups
  direction   bearish buys (train: put buys lost money, largely hedges)
  liquidity   stock under $5
  earnings    a report lands between the flow and our exit (IV crush / gap risk)
  conviction  neither a whale-size OTM bet nor a far-OTM buy at a fair price
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal

from whaleproof import market_calendar as mc
from whaleproof.core.data_layer.models import FlowAlert
from whaleproof.core.verdict.setups import gate_failures

from .config import DEFAULT_FILTER, HOLD_SESSIONS, FilterConfig

TIER_LABEL = {"whale": "Whale conviction bet", "far_otm": "Far-OTM buy at a fair price"}


@dataclass(frozen=True)
class Context:
    """Facts known at decision time besides the alert itself."""
    same_day: list[FlowAlert] = field(default_factory=list)   # the ticker's alerts that session (gate checks)
    earnings: list[tuple[date, str]] = field(default_factory=list)  # (report_date, report_time)
    value: str = "unknown"                                  # cheap / fair / rich / unknown (IV vs trailing RV)
    value_reason: str = ""
    repeat: int = 0                                         # other clean buys, same direction, last 3 sessions


@dataclass(frozen=True)
class Result:
    passed: bool
    stage: str                      # "signal" when passed, else the failing stage
    reason: str                     # first failure (plain English) or the tier label
    tier: str | None = None
    why: tuple[str, ...] = ()


def _money(v: float) -> str:
    """Same as the UI's money(): .5 rounds up (Python's own rounding is half-to-even, so a row said $879K and its
    reason $878K), and $999.6K reads $1.0M, not $1000K."""
    m = Decimal(str(v / 1e6)).quantize(Decimal("0.1"), ROUND_HALF_UP)
    if m >= 1:
        return f"${m}M"
    return f"${Decimal(str(v / 1e3)).quantize(Decimal('1'), ROUND_HALF_UP)}K"


def exit_session(d: date) -> date:
    """Close of the HOLD_SESSIONS-th session after the flow day (entry at the next open counts as day 1)."""
    x = mc.next_session(d)
    for _ in range(HOLD_SESSIONS - 1):
        x = mc.next_session(x)
    return x


def earnings_in_hold(d: date, earnings: list[tuple[date, str]]) -> tuple[date, str] | None:
    """A report after the flow day's close and before our exit close. Flow-day postmarket counts (it lands before
    entry); exit-day postmarket does not (we are out at the close)."""
    end = exit_session(d)
    for e, when in sorted(earnings):
        if (e == d and when == "postmarket") or (d < e < end) or (e == end and when != "postmarket"):
            return e, when
    return None


def _why(a: FlowAlert, c: Context, tier: str) -> tuple[str, ...]:
    lines = [f"{_money(a.total_premium)} {a.kind}s bought at the ask ({a.ask_share * 100:.0f}% ask-side), "
             "single leg, opening position"]
    if tier == "whale":
        lines.append(f"Whale size: {_money(a.total_premium)} on a strike {a.otm_pct * 100:.0f}% out of the money — "
                     "a bold directional bet, not a hedge")
    else:
        lines.append(f"Far out of the money ({a.otm_pct * 100:.0f}%) — deep OTM buying carries the most information "
                     "(Pan & Poteshman 2006)")
    if a.has_sweep:
        lines.append("Sweep: filled across exchanges — urgency")
    lines.append(f"{a.dte} days to expiry")
    if c.value in ("cheap", "fair", "rich"):
        lines.append(f"Option {c.value}: {c.value_reason}" if c.value_reason else f"Option {c.value}")
    if c.repeat:
        lines.append(f"Repeat buying: {c.repeat} other clean buy(s) same direction in the last 3 sessions")
    if c.earnings:
        lines.append(f"No earnings before the planned exit ({exit_session(a.session_date).isoformat()})")
    elif a.issue_type != "ETF":
        lines.append("Earnings date not available — check before trading")
    return tuple(lines)


def decide(direction: int, price: float, premium: float, otm_pct: float, value: str, session_date: date,
           earnings: list[tuple[date, str]], cfg: FilterConfig = DEFAULT_FILTER) -> tuple[str, str, str | None]:
    """Post-gate stages on plain facts → (stage, reason, tier). Shared by live alerts and history rows."""
    if cfg.longs_only and direction < 0:
        return "direction", "bearish buy — put buys lost money on train (mostly hedges)", None
    if price < cfg.min_stock_price:
        return "liquidity", f"stock ${price:.2f} < ${cfg.min_stock_price:.0f} — thin, wide fills", None
    if cfg.block_earnings_in_hold and (e := earnings_in_hold(session_date, earnings)):
        return "earnings", f"earnings {e[0].isoformat()} ({e[1]}) before the planned exit — IV crush risk", None
    if premium >= cfg.whale_premium and otm_pct > cfg.whale_min_otm:
        return "signal", TIER_LABEL["whale"], "whale"
    if otm_pct > cfg.far_otm and value in _allowed_values(cfg.far_otm_max_value):
        return "signal", TIER_LABEL["far_otm"], "far_otm"
    if otm_pct > cfg.far_otm and value == "rich":
        return "conviction", "far OTM but the option is rich vs the stock's realized move", None
    return "conviction", (f"below the bar: {_money(premium)}, {otm_pct * 100:.0f}% OTM (needs ≥ {_money(cfg.whale_premium)} "
                          f"and > {cfg.whale_min_otm * 100:.0f}% OTM, or > {cfg.far_otm * 100:.0f}% OTM at a fair price)"), None


def classify(a: FlowAlert, c: Context, as_of: datetime, cfg: FilterConfig = DEFAULT_FILTER) -> Result:
    fails = gate_failures(a, c.same_day, as_of)
    if fails:
        return Result(False, "gate", fails[0])
    stage, reason, tier = decide(a.direction, a.underlying_price, a.total_premium, a.otm_pct, c.value,
                                 a.session_date, c.earnings, cfg)
    if tier is None:
        return Result(False, stage, reason)
    return Result(True, stage, reason, tier, _why(a, c, tier))


def _allowed_values(max_value: str) -> set[str]:
    return {"cheap"} if max_value == "cheap" else {"cheap", "fair"}
