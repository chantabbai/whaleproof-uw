from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from datetime import date, datetime

from whaleproof.core.checks import ALL_CHECKS, CheckResult
from whaleproof.core.data_layer.context import AlertContext

from .weights import BACKTESTABLE, V0, Weights

GO, WATCH = 70.0, 55.0
MIN_COVERAGE = 0.5
MAX_TIME_STOP = 10


@dataclass(frozen=True)
class TradePlan:
    direction: str
    contract: str
    entry_ref: float | None
    invalidation: float | None
    target: float | None
    time_stop_sessions: int
    structure: str


@dataclass(frozen=True)
class Verdict:
    alert_id: str
    ticker: str
    direction: int
    session_date: date
    as_of: datetime
    weights_version: str
    score: float
    label: str
    coverage: float
    checks: list[CheckResult]
    plan: TradePlan
    reasons_for: list[str]
    reasons_against: list[str]
    score_parity: float = 50.0   # score from backtestable checks only — comparable to backtest

    def to_dict(self) -> dict:
        d = asdict(self)
        d["session_date"] = self.session_date.isoformat()
        d["as_of"] = self.as_of.isoformat()
        return d


def _pick_level(candidates: list[float | None], spot: float, sign: int, lo: float, hi: float,
                fallback: float) -> float:
    """Nearest structural level on the `sign` side of spot whose distance lies in [lo, hi]; else fallback."""
    ok = [c for c in candidates if c is not None and lo <= (c - spot) * sign <= hi]
    return min(ok, key=lambda c: abs(c - spot)) if ok else fallback


def hold_em(spot: float, iv: float | None, stop_n: int) -> float:
    """Expected move over the holding period (not the option's life); bounds the plan's levels."""
    return spot * (iv or 0.4) * math.sqrt(stop_n / 252)


def _plan(ctx: AlertContext, results: dict[str, CheckResult]) -> TradePlan:
    a, g = ctx.alert, ctx.gex
    bull = a.direction > 0
    sign = 1 if bull else -1
    spot = ctx.ref_price or a.underlying_price
    stop_n = max(1, min(MAX_TIME_STOP, a.dte // 2))
    em_h = hold_em(spot, a.iv, stop_n)
    walls = [g.call_wall, g.put_wall, g.gamma_flip, g.gamma_magnet] if g else []
    target = _pick_level(walls, spot, sign, 0.5 * em_h, 2.0 * em_h, spot + sign * 1.25 * em_h)
    invalidation = _pick_level(walls, spot, -sign, 0.25 * em_h, 1.0 * em_h, spot - sign * 0.75 * em_h)
    vp = results.get("vol_price")
    rich = vp is not None and vp.available and vp.score <= -0.5
    leg = "call" if bull else "put"
    return TradePlan(direction="bullish" if bull else "bearish", contract=a.option_chain,
                     entry_ref=ctx.ref_price, invalidation=round(invalidation, 2), target=round(target, 2),
                     time_stop_sessions=stop_n,
                     structure=f"{leg} debit spread" if rich else f"long {leg}")


def evaluate(ctx: AlertContext, weights: Weights = V0) -> Verdict:
    results = {r.name: r for r in (fn(ctx) for fn in ALL_CHECKS)}
    # |w| in denominators: a negative weight (fitted sign flip) means "fade this check"; no-op for positive weights
    total_w = sum(abs(w) for w in weights.w.values())
    avail_w = sum(abs(w) for n, w in weights.w.items() if results[n].available)
    num = sum(w * results[n].score * results[n].confidence for n, w in weights.w.items() if results[n].available)
    score = 50 + 50 * (num / avail_w) if avail_w else 50.0
    par = {n: w for n, w in weights.w.items() if n in BACKTESTABLE and results[n].available}
    par_num = sum(w * results[n].score * results[n].confidence for n, w in par.items())
    par_den = sum(abs(w) for w in par.values())
    score_parity = 50 + 50 * par_num / par_den if par_den else 50.0
    coverage = avail_w / total_w if total_w else 0.0
    hard = any(r.hard_fail for r in results.values())
    # Labels use only backtestable checks so live GO means exactly what the backtest measured;
    # live-only checks (unusualness) still show in `score` and reasons.
    label = "SKIP" if hard else "GO" if score_parity >= GO else "WATCH" if score_parity >= WATCH else "SKIP"
    if label == "GO" and coverage < MIN_COVERAGE:
        label = "WATCH"
    ranked = sorted((r for r in results.values() if r.available and r.reason),
                    key=lambda r: r.score * weights.w.get(r.name, 0.05))
    reasons_for = [r.reason for r in reversed(ranked) if r.score > 0][:3]
    reasons_against = [r.reason for r in results.values() if r.hard_fail][:2] or \
                      [r.reason for r in ranked if r.score < 0][:2]
    a = ctx.alert
    return Verdict(alert_id=a.id, ticker=a.ticker, direction=a.direction, session_date=a.session_date,
                   as_of=ctx.as_of, weights_version=weights.version, score=round(score, 1), label=label,
                   coverage=round(coverage, 3), checks=list(results.values()), plan=_plan(ctx, results),
                   reasons_for=reasons_for, reasons_against=reasons_against,
                   score_parity=round(score_parity, 1))
