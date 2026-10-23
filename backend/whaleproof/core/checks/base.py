from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CheckResult:
    name: str
    score: float
    confidence: float = 1.0
    hard_fail: bool = False
    available: bool = True
    reason: str = ""
    tags: tuple[str, ...] = ()


def clip(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def unavailable(name: str, reason: str = "no data") -> CheckResult:
    return CheckResult(name=name, score=0.0, confidence=0.0, available=False, reason=reason)


def human(n: float) -> str:
    """1_410_549 → '1.41M', 97_103 → '97.1K' (3 significant digits)."""
    a = abs(n)
    for div, suf in ((1e9, "B"), (1e6, "M"), (1e3, "K")):
        if a >= div:
            v = n / div
            txt = f"{v:.3g}" if abs(v) < 1000 else f"{v:.0f}"
            return txt + suf
    return f"{n:.0f}"


def money(n: float) -> str:
    """Signed dollars with a real minus sign: -270e6 → '−$270M'."""
    return ("−" if n < 0 else "") + "$" + human(abs(n))
