"""Option P&L estimate for a pick (Plan 2b): Black-Scholes value of the contract at entry and at the plan's target /
stop on the expected exit day, IV held flat (±5 vol points shown as sensitivity). A model estimate, not a quote."""
from __future__ import annotations

import math
import re
from datetime import date

from whaleproof import market_calendar as mc

from .contract import spread_cost

RATE = 0.04          # flat risk-free rate
IV_BUMP = 0.05
OCC = re.compile(r"^([A-Z.]+?)(\d{6})([CP])(\d{8})$")


def parse_contract(symbol: str) -> dict | None:
    m = OCC.match(symbol or "")
    if not m:
        return None
    t, ymd, kind, strike = m.groups()
    return {"ticker": t, "expiry": date(2000 + int(ymd[:2]), int(ymd[2:4]), int(ymd[4:])), "kind": kind,
            "strike": int(strike) / 1000}


def readable(symbol: str) -> str:
    """"SPY261120C00765000" → "SPY $765 Call · Nov 20 '26" (anything else comes back unchanged)."""
    c = parse_contract(symbol)
    if c is None:
        return symbol
    k = c["strike"]
    return (f"{c['ticker']} ${k:,.0f}" if k == int(k) else f"{c['ticker']} ${k:,.2f}") + \
        f" {'Call' if c['kind'] == 'C' else 'Put'} · {c['expiry']:%b} {c['expiry'].day} '{c['expiry']:%y}"


def _ncdf(x: float) -> float:
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def bs_price(kind: str, s: float, k: float, t: float, iv: float, r: float = RATE) -> float:
    if t <= 0 or iv <= 0:
        return max(s - k, 0.0) if kind == "C" else max(k - s, 0.0)
    d1 = (math.log(s / k) + (r + iv * iv / 2) * t) / (iv * math.sqrt(t))
    d2 = d1 - iv * math.sqrt(t)
    if kind == "C":
        return s * _ncdf(d1) - k * math.exp(-r * t) * _ncdf(d2)
    return k * math.exp(-r * t) * _ncdf(-d2) - s * _ncdf(-d1)


def _years(a: date, b: date) -> float:
    return max((b - a).days, 0) / 365


def estimate(contract: str, spot: float, target: float, stop: float, iv: float | None, entry: date,
             exit_sessions: int, spread_width: float | None = None) -> dict | None:
    """Value per share at entry / target / stop. spread_width → debit spread with the short leg that far OTM."""
    c = parse_contract(contract)
    if c is None or not iv or not spot:
        return None
    exit_day = entry
    for _ in range(max(exit_sessions, 1)):
        exit_day = mc.next_session(exit_day)
    kind, k, exp = c["kind"], c["strike"], c["expiry"]
    k2 = (k + spread_width if kind == "C" else k - spread_width) if spread_width else None

    def value(s: float, t: float, v: float) -> float:
        long = bs_price(kind, s, k, t, v)
        return long - bs_price(kind, s, k2, t, v) if k2 is not None else long

    t0, t1 = _years(entry, exp), _years(exit_day, exp)
    prem = value(spot, t0, iv)
    if prem <= 0:
        return None
    at_t, at_s = value(target, t1, iv), value(stop, t1, iv)
    leg = "call" if kind == "C" else "put"
    # Greeks by bumping the same model: per $1 move in the stock, per calendar day passing
    delta = (value(spot + 0.01, t0, iv) - value(spot - 0.01, t0, iv)) / 0.02
    theta_day = value(spot, max(t0 - 1 / 365, 0), iv) - prem
    # the bid/ask spread: pay half going in, give up half coming out
    cost = spread_cost(prem)
    buy, net = prem * (1 + cost / 2), lambda v: v * (1 - cost / 2)
    rt_net, rs_net = net(at_t) / buy - 1, net(at_s) / buy - 1
    return {"structure": f"{leg} debit spread" if k2 is not None else f"long {leg}", "strike": k,
            "delta": delta, "theta_day": theta_day, "theta_pct": theta_day / prem, "cost_pct": cost,
            "ret_target_net": rt_net, "ret_stop_net": rs_net,
            "option_rr": rt_net / abs(rs_net) if rs_net < 0 else None,
            "short_strike": k2, "expiry": exp.isoformat(), "exit_day": exit_day.isoformat(), "iv": iv,
            "entry_premium": prem, "value_target": at_t, "value_stop": at_s,
            "ret_target": at_t / prem - 1, "ret_stop": at_s / prem - 1,
            "ret_target_iv_up": value(target, t1, iv + IV_BUMP) / prem - 1,
            "ret_target_iv_down": value(target, t1, max(iv - IV_BUMP, 0.01)) / prem - 1,
            "breakeven": k + prem if kind == "C" else k - prem,
            "note": "Black-Scholes estimate, IV held flat; not a quote"}


def mark(contract: str, iv: float | None, entry: date, s_entry: float, s_now: float, on: date) -> float | None:
    """What the option would have done: bought at entry (spot s_entry), valued on `on` at spot s_now, IV flat,
    net of the bid/ask spread. Turns the scorecard's stock move into an estimated option result."""
    c = parse_contract(contract)
    if c is None or not iv or not s_entry or not s_now:
        return None
    k, kind, exp = c["strike"], c["kind"], c["expiry"]
    prem = bs_price(kind, s_entry, k, _years(entry, exp), iv)
    if prem <= 0:
        return None
    cost = spread_cost(prem)
    now = bs_price(kind, s_now, k, _years(on, exp), iv)
    return now * (1 - cost / 2) / (prem * (1 + cost / 2)) - 1
