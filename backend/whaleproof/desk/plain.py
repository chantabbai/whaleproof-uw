"""Plain words for the API and MCP. The engine's short reason/why strings stay as they are, because filter logic and
stored history read them (e.g. setups.is_put_sale checks the "not a buy" prefix). This layer only rewrites them on the
way out. Anything it doesn't recognise passes through unchanged."""
from __future__ import annotations

import functools
import re
from datetime import date, datetime

from whaleproof.core.checks.quality import IV_RV_NEUTRAL
from whaleproof.core.options.pricing import BAND
from whaleproof.market_calendar import NY

IV_RV_CHEAP, IV_RV_RICH = IV_RV_NEUTRAL - BAND, IV_RV_NEUTRAL + BAND     # same cut-offs as the engine's value_view

TIER_PLAIN = {"Whale conviction bet": "Whale-size bet", "Far-OTM buy at a fair price": "Long shot, not overpriced"}
_WHEN = {"premarket": "before the open", "postmarket": "after the close", "afterhours": "after the close"}
_VALUE = {"cheap": "cheap", "fair": "fairly priced", "rich": "expensive"}


def _md(iso: str, today: date | None = None) -> str:
    """"Oct 9"; with the year when it isn't this year ("Jan 15, 2027")."""
    d, today = date.fromisoformat(iso), today or datetime.now(NY).date()
    return f"{d.strftime('%b')} {d.day}" if d.year == today.year else f"{d.strftime('%b')} {d.day}, {d.year}"


def _s(n: str, word: str) -> str:
    return f"{n} {word}" if n == "1" else f"{n} {word}s"


def _iv_vs_rv(iv: str, rv: str, ratio: str, verdict: str | None = None) -> str:
    """Contract IV against the stock's realized move, said the way a trader would (the verdict itself uses IV rank).
    When it points the other way from the IV-rank verdict ("cheap" but pricey vs realized), the sentence says "But"."""
    r = float(ratio)
    feel = "pricey" if r > IV_RV_RICH else "cheap" if r < IV_RV_CHEAP else None
    if (verdict, feel) in (("cheap", "pricey"), ("rich", "cheap")):
        return f"But implied vol {iv}% vs {rv}% realized lately ({ratio}×) is {feel} next to how much the stock moves."
    words = f"{feel} next to how much the stock moves" if feel else "about in line with how much the stock moves"
    return f"Implied vol {iv}% vs {rv}% realized lately ({ratio}×), {words}."


def _otm(sign: str, pct: str) -> str:
    if pct == "0":
        return "the money"
    return f"{pct}% in the money" if sign in ("-", "−") else f"{pct}% out of the money"


def _ask_side(pct: int, need: str) -> str:
    """Little traded at the ask = the other side (a seller) drove it; say that, not "only 0%"."""
    rule = f"We only count trades where {need}% or more was bought at the ask."
    if pct == 0:
        return f"Looks like a sale, not a buy: none of it traded at the asking price. {rule}"
    if pct < 40:
        return f"Looks like a sale, not a buy: only {pct}% traded at the asking price. {rule}"
    return f"Mixed buying and selling: {pct}% traded at the asking price. {rule}"


_REASONS: list[tuple[re.Pattern, object]] = [(re.compile(p), f) for p, f in [
    (r"not a buy \(ask-side (\d+)% < (\d+)%\)", lambda m: _ask_side(int(m[1]), m[2])),
    (r"floor/cross trade", "A floor or cross trade, not a buyer on the open market."),
    (r"not clearly opening", "Can't tell that it opened a new position."),
    (r"multi-leg", "Part of a multi-leg trade."),
    (r"moneyness ([+\-−]?)(\d+)% outside −5%…\+30%",
     lambda m: f"{m[2]}% {'in' if m[1] in ('-', '−') else 'out of'} the money. We only take 5% in to 30% out of the money."),
    (r"DTE (\d+) outside 7–90", lambda m: f"{'Expires today' if m[1] == '0' else 'Expires in ' + _s(m[1], 'day')}. We only take 7 to 90 days."),
    (r"issue type (.+)", lambda m: f"Not a stock, ADR or ETF ({m[1]})."),
    (r"ETF put \(likely hedge\)", "A put on an ETF, which is usually a hedge."),
    (r"call and put both bought \(vol play\)", "Calls and puts bought together, a bet on a big move rather than a direction."),
    (r"same-second sold leg \(spread leg\)", "One leg of a spread: another leg was sold in the same second."),
    (r"bearish buy — put buys lost money on train \(mostly hedges\)",
     "Bearish. We only take bullish bets: most big put buys are insurance on stock people already own, not bets on a drop."),
    (r"stock (\$[\d.]+) < (\$\d+) — thin, wide fills", lambda m: f"The stock is {m[1]}, under {m[2]}, where fills are thin and wide."),
    (r"earnings (\d{4}-\d\d-\d\d) \((\w+)\) before the planned exit — IV crush risk",
     lambda m: f"Earnings on {_md(m[1])} ({_WHEN.get(m[2], 'time not set')}) land before the planned sell."),
    (r"IV rank (\d+) \(0 = cheapest of the past year, 100 = richest\)"
     r"(?:; option IV (\d+)% vs stock's recent realized move (\d+)% \(×([\d.]+)\) — info only)?",
     lambda m: f"IV rank {m[1]} of 100 over the past year." + (f" {_iv_vs_rv(m[2], m[3], m[4])}" if m[2] else "")),
    (r"far OTM but the option is rich vs the stock's realized move",
     "A long shot, but the option was expensive next to how much the stock really moves."),
    (r"below the bar: (\S+), (-?)(\d+)% OTM \(needs ≥ (\S+) and > (\d+)% OTM, or > (\d+)% OTM at a fair price\)",
     lambda m: f"Not big enough: {m[1]} at {_otm(m[2], m[3])}. A signal needs {m[4]} or more on a strike over "
               f"{m[5]}% out, or a strike over {m[6]}% out at a fair price."),
]]

_WHY: list[tuple[re.Pattern, object]] = [(re.compile(p), f) for p, f in [
    (r"(\S+) (calls|puts) bought at the ask \((\d+)% ask-side\), single leg, opening position",
     lambda m: f"{m[1]} in {m[2]}, {m[3]}% of it paid at the ask, one leg, a new position."),
    (r"Whale size: (\S+) on a strike (\d+)% out of the money — a bold directional bet, not a hedge",
     lambda m: f"Whale-size: {m[1]} on a strike {m[2]}% out of the money. That's a bet on direction, not a hedge."),
    (r"Far out of the money \((\d+)%\) — deep OTM buying carries the most information \(Pan & Poteshman 2006\)",
     lambda m: f"A long shot: the strike is {m[1]}% out of the money."),
    (r"Sweep: filled across exchanges — urgency", "Swept across exchanges, so the buyer was in a hurry."),
    (r"(\d+) days to expiry", lambda m: f"{_s(m[1], 'day')} until it expires."),
    (r"Repeat buying: (\d+) other clean buy\(s\) same direction in the last (\d+) sessions",
     lambda m: f"Someone kept buying: {m[1]} other clean {'buy' if m[1] == '1' else 'buys'} the same way in the last {m[2]} sessions."),
    (r"No earnings before the planned exit \((\d{4}-\d\d-\d\d)\)", lambda m: f"No earnings before the planned sell on {_md(m[1])}."),
    (r"Earnings date not available — check before trading", "No earnings date on file, so check before trading."),
    (r"Option (cheap|fair|rich): IV rank (\d+) \(0 = cheapest of the past year, 100 = richest\)"
     r"(?:; option IV (\d+)% vs stock's recent realized move (\d+)% \(×([\d.]+)\) — info only)?",
     lambda m: f"The option was {_VALUE[m[1]]}: IV rank {m[2]} of 100 over the past year."
               + (f" {_iv_vs_rv(m[3], m[4], m[5], m[1])}" if m[3] else "")),
    (r"Option (cheap|fair|rich)", lambda m: f"The option was {_VALUE[m[1]]}."),
]]


def _apply(rules: list, text: str) -> str:
    for pat, out in rules:
        if m := pat.fullmatch(text):
            return out(m) if callable(out) else out
    return text


def reason(text: str) -> str:
    if not isinstance(text, str) or not text:
        return text
    return TIER_PLAIN.get(text) or _apply(_REASONS, text)


def why(text: str) -> str:
    return _apply(_WHY, text) if isinstance(text, str) else text


def _why_list(lines: list) -> list:
    """Plain why-lines. A whale-size bet never checks the option's price, so an expensive one says so."""
    out = [why(x) for x in lines]
    if any(isinstance(x, str) and x.startswith("Whale-size:") for x in out):
        out = [x + " Whale-size bets pass whatever the option costs."
               if isinstance(x, str) and x.startswith("The option was expensive") else x for x in out]
    return out


def plainly(fn):
    """Route decorator: run the endpoint, return its payload in plain words (signature kept for FastAPI)."""
    @functools.wraps(fn)
    def run(*args, **kwargs):
        return humanize(fn(*args, **kwargs))
    return run


def humanize(obj):
    """Copy of an API payload with `reason`, `why` and tier `label` values in plain words. Shape and every other value
    are unchanged; the input is not modified."""
    if isinstance(obj, list):
        return [humanize(x) for x in obj]
    if not isinstance(obj, dict):
        return obj
    out = {}
    for k, v in obj.items():
        if k == "reason" and isinstance(v, str):
            out[k] = reason(v)
        elif k == "why" and isinstance(v, list):
            out[k] = _why_list(v)
        elif k == "label" and isinstance(v, str):
            out[k] = TIER_PLAIN.get(v, v)
        else:
            out[k] = humanize(v)
    return out
