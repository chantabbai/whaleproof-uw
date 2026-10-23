"""Noise funnel and performance stats over history rows (primary metric: 5-session return vs SPY, net of costs)."""
from __future__ import annotations

import random
import statistics
from collections import defaultdict
from datetime import date

from .history import HistRow

BLOCK = 5            # overlapping 5-day holds → resample 5-day blocks of daily means
BOOT = 2000


def _daily(rows: list[HistRow]) -> dict[date, float]:
    by: dict[date, list[float]] = defaultdict(list)
    for r in rows:
        if r.x5 is not None:
            by[r.session_date].append(r.x5)
    return {d: statistics.fmean(v) for d, v in sorted(by.items())}


def block_ci(vals: list[float], seed: int = 7, level: float = 0.95) -> tuple[float, float]:
    """Moving-block bootstrap CI of the mean (blocks of BLOCK consecutive days)."""
    if len(vals) < BLOCK * 2:
        return (float("nan"), float("nan"))
    rng = random.Random(seed)
    n, starts = len(vals), len(vals) - BLOCK + 1
    means = []
    for _ in range(BOOT):
        s: list[float] = []
        while len(s) < n:
            i = rng.randrange(starts)
            s.extend(vals[i:i + BLOCK])
        means.append(statistics.fmean(s[:n]))
    means.sort()
    a = (1 - level) / 2
    return means[int(a * BOOT)], means[int((1 - a) * BOOT) - 1]


def summarize(rows: list[HistRow], ci: bool = False) -> dict:
    x = [r.x5 for r in rows if r.x5 is not None]
    if not x:
        return {"n": 0, "days": 0}
    daily = _daily(rows)
    gains, losses = sum(v for v in x if v > 0), -sum(v for v in x if v < 0)
    wins, loss = [v for v in x if v > 0], [v for v in x if v < 0]
    out = {"n": len(x), "days": len(daily), "win_rate": len(wins) / len(x), "mean": statistics.fmean(x),
           "median": statistics.median(x), "day_mean": statistics.fmean(daily.values()),
           "profit_factor": gains / losses if losses else None,
           "avg_win": statistics.fmean(wins) if wins else None, "avg_loss": statistics.fmean(loss) if loss else None}
    if ci:
        lo, hi = block_ci(list(daily.values()))
        out |= {"ci_low": lo, "ci_high": hi}
    return out


def funnel(rows: list[HistRow], raw_counts: dict[date, int]) -> dict:
    days = sorted({r.session_date for r in rows})
    counts = {"raw": sum(raw_counts.get(d, 0) for d in days), "directional": len(rows),
              "clean": sum(r.stage != "gate" for r in rows), "signals": sum(r.tier is not None for r in rows)}
    n = len(days) or 1
    return {"days": len(days), **counts, "per_day": {k: v / n for k, v in counts.items()}}


def by_key(rows: list[HistRow], key) -> dict[str, dict]:
    groups: dict[str, list[HistRow]] = defaultdict(list)
    for r in rows:
        groups[str(key(r))].append(r)
    return {k: summarize(v) for k, v in sorted(groups.items())}


def monthly(rows: list[HistRow]) -> list[dict]:
    return [{"month": k, **v} for k, v in by_key(rows, lambda r: r.session_date.isoformat()[:7]).items()]
