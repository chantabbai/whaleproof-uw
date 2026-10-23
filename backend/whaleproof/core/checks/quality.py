"""Endpoint-review checks (docs/uw-endpoint-review.md): option-implied skew, options positioning sentiment,
implied-vs-realized vol, macro-event risk. All start at weight 0; the train fit + holdout decide
(docs/preregistration.md)."""
from __future__ import annotations

from datetime import date, datetime

from whaleproof import market_calendar as mc
from whaleproof.core.data_layer.context import AlertContext

from .base import CheckResult, clip, unavailable

SKEW_LOOKBACK = 252            # trailing observations for the ticker's own skew percentile
SKEW_MIN_HISTORY = 60
MAX_STALE_DAYS = 3             # latest value must be this close to D (calendar days)
SENTIMENT_SCALE = 1.0          # UW score → [-1, 1]; confirm scale at the probe
IV_RV_NEUTRAL, IV_RV_SPAN = 1.15, 0.5   # IV/RV ≈ 1.15 is typical; ±0.5 around it maps to ±1
HOLD_SESSIONS = 5              # matches the 5-session outcome horizon
MACRO_KEYWORDS = ("fomc", "federal funds", "interest rate decision", "fed interest rate", "cpi",
                  "consumer price index", "employment situation", "nonfarm", "non-farm", "pce")
CALENDAR_COVERAGE_DAYS = 10    # calendar counts as covering D only if it has an event within this many days


def _fresh(d_str: str, d: date) -> bool:
    return 0 <= (d - date.fromisoformat(d_str[:10])).days <= MAX_STALE_DAYS


def skew(ctx: AlertContext) -> CheckResult:
    """25Δ risk reversal (put IV − call IV) vs the ticker's own trailing year. Rich puts → bearish (Xing-Zhang-Zhao)."""
    d = ctx.alert.session_date
    pts = [(dt, v) for dt, v in (ctx.rr25 or []) if dt[:10] <= d.isoformat()]
    if len(pts) < SKEW_MIN_HISTORY or not _fresh(pts[-1][0], d):
        return unavailable("skew", "not enough skew history")
    v = pts[-1][1]
    hist = [x for _, x in pts[-SKEW_LOOKBACK - 1:-1]]
    pct = (sum(x < v for x in hist) + 0.5 * sum(x == v for x in hist)) / len(hist)
    word = "rich" if pct >= 0.8 else "cheap" if pct <= 0.2 else "normal"
    return CheckResult("skew", (0.5 - pct) * 2 * ctx.alert.direction,
                       reason=f"put skew {word} ({pct * 100:.0f}th pct of its year)")


def option_sentiment(ctx: AlertContext) -> CheckResult:
    """UW options positioning score (VWKS + AVAR): + bullish, − bearish; aligned with our direction."""
    s = ctx.opt_sentiment
    if s is None:
        return unavailable("option_sentiment")
    raw = clip(s / SENTIMENT_SCALE, -1, 1)
    return CheckResult("option_sentiment", raw * ctx.alert.direction,
                       reason=f"chain positioning {'bullish' if s > 0 else 'bearish' if s < 0 else 'neutral'} ({s:+.2f})")


def iv_rv(ctx: AlertContext) -> CheckResult:
    """30d IV on D vs the latest 21d realized vol whose window already ended by D (no look-ahead).
    Not directional: cheap options (IV ≤ RV) score +, rich −."""
    d = ctx.alert.session_date
    rows = ctx.vol_hist or []
    iv_today = [(dt, iv) for dt, iv, _, _ in rows if iv is not None and dt[:10] <= d.isoformat() and _fresh(dt, d)]
    trailing = [(end, rv) for _, _, rv, end in rows if rv and end and end[:10] <= d.isoformat()]
    if not iv_today or not trailing:
        return unavailable("iv_rv")
    iv, rv = max(iv_today)[1], max(trailing)[1]
    ratio = iv / rv
    return CheckResult("iv_rv", clip((IV_RV_NEUTRAL - ratio) / IV_RV_SPAN, -1, 1),
                       reason=f"IV {iv * 100:.0f}% vs RV {rv * 100:.0f}% (×{ratio:.2f})")


def _hold_end(d: date) -> datetime:
    s = mc.next_session(d)
    for _ in range(HOLD_SESSIONS - 1):
        s = mc.next_session(s)
    return mc.session_close(s)


def macro_event(ctx: AlertContext) -> CheckResult:
    """−1 when a major macro release (FOMC, CPI, jobs, PCE) falls inside the holding window. Direction-neutral."""
    d = ctx.alert.session_date
    events = [(datetime.fromisoformat(t), name) for t, name in (ctx.econ or [])]
    if not any(abs((t.date() - d).days) <= CALENDAR_COVERAGE_DAYS for t, _ in events):
        return unavailable("macro_event", "economic calendar doesn't cover this week")
    end = _hold_end(d)
    hits = [name for t, name in events
            if ctx.as_of < t <= end and any(k in name.lower() for k in MACRO_KEYWORDS)]
    if hits:
        return CheckResult("macro_event", -1.0, reason=f"macro event in hold: {', '.join(hits[:3])}",
                           tags=("macro_event",))
    return CheckResult("macro_event", 0.0, reason="no major macro event in hold")

