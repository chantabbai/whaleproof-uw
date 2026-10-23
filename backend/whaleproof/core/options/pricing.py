"""Cheap or rich? Black-Scholes turns a volatility into a price; whether that price is cheap depends on the volatility
it assumes. Primary yardstick: the contract's IV vs the stock's trailing 21-day realized vol (same neutral ratio as the
iv_rv check). Fallback: the stock's IV rank (same cut-offs as the vol_price check). Descriptive only — not proven."""
from __future__ import annotations

from whaleproof.core.checks.quality import IV_RV_NEUTRAL

BAND = 0.2            # IV/RV within 1.15 ± 0.2 → fair
RANK_CHEAP, RANK_RICH = 30, 70


def value_view(iv: float | None, rv: float | None, iv_rank: float | None) -> dict:
    if iv and rv:
        ratio = iv / rv
        verdict = "cheap" if ratio < IV_RV_NEUTRAL - BAND else "rich" if ratio > IV_RV_NEUTRAL + BAND else "fair"
        return {"verdict": verdict, "basis": "iv_rv", "iv": iv, "rv": rv, "iv_rv": ratio, "iv_rank": iv_rank,
                "reason": f"option IV {iv * 100:.0f}% vs stock's recent realized move {rv * 100:.0f}% (×{ratio:.2f})"}
    if iv_rank is not None:
        verdict = "cheap" if iv_rank <= RANK_CHEAP else "rich" if iv_rank >= RANK_RICH else "fair"
        return {"verdict": verdict, "basis": "iv_rank", "iv": iv, "rv": None, "iv_rv": None, "iv_rank": iv_rank,
                "reason": f"IV rank {iv_rank:.0f} (0 = cheapest of the past year, 100 = richest)"}
    return {"verdict": "unknown", "basis": None, "iv": iv, "rv": None, "iv_rv": None, "iv_rank": None,
            "reason": "no volatility history cached"}
