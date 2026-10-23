"""The contract WE would buy, and what trading it costs.

The whale's contract fits the whale's plan (maybe a hedge, maybe a 2-day lottery). Ours must fit ours: a standard
monthly expiry with room to spare after the holding period (time decay is slowest there) and a strike near the money
(delta ≈ 0.5). Without a listed-chain feed this is a suggestion on a typical strike grid — check it is listed.
Cost: an option's real cost is its bid/ask spread, far bigger than stock slippage, and biggest on cheap options."""
from __future__ import annotations

import math
from datetime import date, timedelta

MIN_DAYS = 21          # never shorter than three weeks to expiry
HOLD_MULT = 2.5        # expiry ≥ 2.5 × the holding period (calendar days)


def third_friday(year: int, month: int) -> date:
    d = date(year, month, 1)
    return d + timedelta(days=(4 - d.weekday()) % 7 + 14)


def pick_expiry(entry: date, hold_sessions: int) -> date:
    need = entry + timedelta(days=max(MIN_DAYS, math.ceil(HOLD_MULT * hold_sessions * 7 / 5)))
    y, m = need.year, need.month
    while third_friday(y, m) < need:
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return third_friday(y, m)


def strike_step(spot: float) -> float:
    return 0.5 if spot < 25 else 1.0 if spot < 100 else 2.5 if spot < 250 else 5.0


def round_strike(spot: float, direction: int) -> float:
    """Nearest grid strike, ties toward slightly in the money (calls down, puts up)."""
    step = strike_step(spot)
    lo = math.floor(spot / step) * step
    hi = lo + step
    if abs(spot - lo) == abs(hi - spot):
        return lo if direction > 0 else hi
    return lo if spot - lo < hi - spot else hi


def choose_contract(ticker: str, direction: int, spot: float, entry: date, hold_sessions: int) -> str:
    exp, k = pick_expiry(entry, hold_sessions), round_strike(spot, direction)
    return f"{ticker}{exp:%y%m%d}{'C' if direction > 0 else 'P'}{round(k * 1000):08d}"


def spread_cost(premium: float) -> float:
    """Estimated round-trip cost (full bid/ask spread) as a share of the option price."""
    return 0.15 if premium < 0.5 else 0.10 if premium < 1 else 0.06 if premium < 3 else 0.04 if premium < 10 else 0.03
