"""How to express a bullish signal with options: long call (the whale's strike), ATM→+10% call debit spread,
cash-secured short put 5% OTM, 5%/15% OTM bull put credit spread. Priced with Black-Scholes using the whale contract's
REAL implied vol on entry and exit days (flat smile — an approximation: real OTM puts carry extra skew premium), real
stock prices, and a per-leg bid/ask cost on both sides. Model estimate; confirm with real leg prices when fetched."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from whaleproof.core.options.contract import spread_cost, strike_step
from whaleproof.core.options.pnl import bs_price

MIN_PRICE = 0.05       # smallest realistic option quote
STRUCTURES = ("long_call", "call_spread", "short_put", "put_spread")
LABEL = {"long_call": "Buy the whale's call", "call_spread": "Call debit spread (ATM → +10%)",
         "short_put": "Sell a 5% OTM put (cash-secured)", "put_spread": "Bull put spread (sell 5% / buy 15% OTM)"}


@dataclass(frozen=True)
class Leg:
    kind: str       # "C" | "P"
    strike: float
    qty: int        # +1 long, −1 short


def _grid(x: float, spot: float) -> float:
    step = strike_step(spot)
    return round(round(x / step) * step, 2)


def structures_for(spot: float, whale_strike: float) -> dict[str, list[Leg]]:
    atm, up = _grid(spot, spot), _grid(spot * 1.10, spot)
    p5, p15 = _grid(spot * 0.95, spot), _grid(spot * 0.85, spot)
    return {"long_call": [Leg("C", whale_strike, +1)],
            "call_spread": [Leg("C", atm, +1), Leg("C", max(up, atm + strike_step(spot)), -1)],
            "short_put": [Leg("P", p5, -1)],
            "put_spread": [Leg("P", p5, -1), Leg("P", min(p15, p5 - strike_step(spot)), +1)]}


OWN_CALLS = {"call_itm10_60d": 0.90, "call_atm_60d": 1.00}      # our own contract: strike = spot × factor, ~60 days
OWN_LABEL = {"call_itm10_60d": "Our call: 10% in the money, ~60 days", "call_atm_60d": "Our call: at the money, ~60 days"}


def own_expiry(entry: date, days: int = 60) -> date:
    """First monthly expiry (third Friday) at least `days` after entry."""
    from whaleproof.core.options.contract import third_friday
    t = entry + timedelta(days=days)
    tf = third_friday(t.year, t.month)
    if tf < t:
        y, m = (t.year + 1, 1) if t.month == 12 else (t.year, t.month + 1)
        tf = third_friday(y, m)
    return tf


def own_calls(spot: float) -> dict[str, list[Leg]]:
    return {name: [Leg("C", _grid(spot * f, spot), +1)] for name, f in OWN_CALLS.items()}


def _t(a: date, b: date) -> float:
    return max((b - a).days, 0) / 365


def evaluate(legs: list[Leg], s0: float, s1: float, entry: date, exit_: date, expiry: date,
             iv0: float, iv1: float) -> dict:
    """Return on the capital at risk: debit (long structures), max loss (credit spread), strike cash (short put)."""
    cash0 = cash1 = cost = 0.0
    for g in legs:
        p0 = max(bs_price(g.kind, s0, g.strike, _t(entry, expiry), iv0), MIN_PRICE)   # listed options never quote ~0
        p1 = max(bs_price(g.kind, s1, g.strike, _t(exit_, expiry), iv1), MIN_PRICE if _t(exit_, expiry) > 0 else 0.0)
        cash0 += -g.qty * p0                        # money received (+) or paid (−) at entry
        cash1 += g.qty * p1                         # money received (+) or paid (−) closing at exit
        cost += (p0 * spread_cost(p0) + p1 * spread_cost(p1)) / 2     # half the gap each side, per leg
    pnl = cash0 + cash1 - cost
    if cash0 < 0:                                   # net debit
        risk, basis = -cash0, "debit"
    elif len(legs) == 2:                            # credit spread: width − credit
        risk, basis = abs(legs[0].strike - legs[1].strike) - cash0, "max loss"
    else:                                           # naked short put, cash-secured
        risk, basis = legs[0].strike, "collateral"
    return {"pnl": pnl, "risk": risk, "cost": cost, "ret": pnl / risk if risk > 0 else None, "basis": basis}


def _f(v) -> float | None:
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return x if x > 0 else None


def evaluate_real(legs: list[Leg], symbols: list[str], hist_of, entry: date, exit_: date) -> dict | None:
    """Same returns from REAL daily option history. Fills (conservative, as the long-call backtest): enter at the entry
    day's opening trade ± half that day's closing bid/ask gap; exit long legs at the closing bid, short legs at the
    closing ask. Any leg without those prices → None (not measured, never guessed)."""
    cash0 = cash1 = 0.0
    for g, sym in zip(legs, symbols):
        h = hist_of(sym) or {}
        a, b = h.get(entry.isoformat()), h.get(exit_.isoformat())
        if not a or not b:
            return None
        op, bid0, ask0 = _f(a.get("open_price")), _f(a.get("nbbo_bid")), _f(a.get("nbbo_ask"))
        bid1, ask1 = _f(b.get("nbbo_bid")), _f(b.get("nbbo_ask"))
        if op is None or (g.qty > 0 and bid1 is None) or (g.qty < 0 and ask1 is None):
            return None
        half = (ask0 - bid0) / 2 if bid0 and ask0 and ask0 >= bid0 else 0.0
        cash0 += -(op + half) if g.qty > 0 else (op - half)
        cash1 += bid1 if g.qty > 0 else -ask1
    pnl = cash0 + cash1
    if cash0 < 0:
        risk, basis = -cash0, "debit"
    elif len(legs) == 2:
        risk, basis = abs(legs[0].strike - legs[1].strike) - cash0, "max loss"
    else:
        risk, basis = legs[0].strike, "collateral"
    return {"pnl": pnl, "risk": risk, "ret": pnl / risk if risk > 0 else None, "basis": basis}
