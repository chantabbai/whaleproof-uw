from __future__ import annotations

import math
import statistics


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return (0.0, 0.0)
    p = k / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return (centre - half, centre + half)


def summarize_returns(values: list[float]) -> dict:
    n = len(values)
    if n == 0:
        return {"n": 0, "hit_rate": None, "ci_low": None, "ci_high": None, "mean": None,
                "median": None, "expectancy": None, "profit_factor": None}
    wins = [v for v in values if v > 0]
    losses = [v for v in values if v <= 0]
    lo, hi = wilson(len(wins), n)
    gross_loss = -sum(losses)
    return {"n": n, "hit_rate": len(wins) / n, "ci_low": lo, "ci_high": hi,
            "mean": statistics.fmean(values), "median": statistics.median(values),
            "expectancy": statistics.fmean(values),
            "profit_factor": (sum(wins) / gross_loss) if gross_loss > 0 else None}
