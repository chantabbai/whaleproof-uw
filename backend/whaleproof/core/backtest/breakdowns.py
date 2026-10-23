"""Bucketing and robustness statistics for the backtest report."""
from __future__ import annotations

import random
import statistics
from collections import defaultdict

LOW_SAMPLE = 30
BOOT_SAMPLES = 1000
BOOT_SEED = 42


def bucket_rr(rr: float | None) -> str:
    if rr is None:
        return "n/a"
    return "<1" if rr < 1 else "1–1.5" if rr < 1.5 else "1.5–2" if rr < 2 else ">2"


def bucket_score(s: float) -> str:
    if s >= 90:
        return "90+"
    lo = int(s // 5 * 5)
    return f"{lo}–{lo + 5}"


def bucket_dte(dte: int | None) -> str:
    if dte is None:
        return "n/a"
    return "≤14" if dte <= 14 else "15–45" if dte <= 45 else "46–90" if dte <= 90 else ">90"


def bucket_premium(p: float | None) -> str:
    if p is None:
        return "n/a"
    return ("$100K–250K" if p < 250e3 else "$250K–1M" if p < 1e6 else "$1M–5M" if p < 5e6 else ">$5M")


def bucket_ivr(v: float | None) -> str:
    if v is None:
        return "n/a"
    return "<30" if v < 30 else "30–50" if v < 50 else "50–70" if v < 70 else "≥70"


def top_n_per_day(rows: list, n: int = 5) -> list:
    """Mirror of live selection: GO rows ranked by score_parity, one per ticker (Amendment 10), best n per session."""
    by_day = defaultdict(list)
    for r in rows:
        if r.label == "GO":
            by_day[r.session_date].append(r)
    out = []
    for d in sorted(by_day):
        seen, day = set(), []
        for r in sorted(by_day[d], key=lambda r: (-(r.score_parity or 0), r.ticker, r.direction)):
            if r.ticker not in seen:
                seen.add(r.ticker)
                day.append(r)
        out.extend(day[:n])
    return out


def _daily_means(rows: list, field: str) -> list[float]:
    by_day = defaultdict(list)
    for r in rows:
        v = getattr(r, field)
        if v is not None:
            by_day[r.session_date].append(v)
    return [statistics.fmean(v) for _, v in sorted(by_day.items())]


def day_cluster(rows: list, field: str) -> dict:
    """Same-day picks are correlated; treat each day as one observation."""
    m = _daily_means(rows, field)
    if not m:
        return {"n_days": 0, "mean_daily": None, "sd": None, "t_stat": None, "hit_days": None,
                "boot_ci_low": None, "boot_ci_high": None}
    mean = statistics.fmean(m)
    sd = statistics.stdev(m) if len(m) > 1 else 0.0
    rng = random.Random(BOOT_SEED)
    boots = sorted(statistics.fmean(rng.choices(m, k=len(m))) for _ in range(BOOT_SAMPLES))
    return {"n_days": len(m), "mean_daily": mean, "sd": sd,
            "t_stat": (mean / (sd / len(m) ** 0.5)) if sd > 0 else None,
            "hit_days": sum(x > 0 for x in m) / len(m),
            "boot_ci_low": boots[int(0.025 * BOOT_SAMPLES)], "boot_ci_high": boots[int(0.975 * BOOT_SAMPLES) - 1]}


def portfolio(rows: list, field: str, hold: int = 5) -> dict:
    """Approximate equity: each day's cohort gets 1/hold of capital; cumulative sum of cohort means."""
    m = _daily_means(rows, field)
    eq, peak, mdd = 0.0, 0.0, 0.0
    for x in m:
        eq += x / hold
        peak = max(peak, eq)
        mdd = min(mdd, eq - peak)
    return {"n_cohorts": len(m), "total_return": eq, "max_drawdown": mdd}
