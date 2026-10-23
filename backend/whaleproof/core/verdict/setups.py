"""Pure-directional gate + setup tags (docs/preregistration.md Amendment 3). Simple rules first: the gate removes
alerts that are probably not directional bets; the setup names the kind of bet so each gets its own measured stats."""
from __future__ import annotations

from bisect import bisect_left, bisect_right
from datetime import date, datetime, timedelta

from whaleproof.core.data_layer.models import FlowAlert

BUY_SHARE = 0.70
MONEYNESS = (-0.05, 0.30)       # slightly ITM … 30% OTM (Amendment 5)
FAR_OTM = 0.15                  # beyond this = far_otm setup (Pan-Poteshman: deep OTM most informative)
DTE_RANGE = (7, 90)
GATE_TYPES = {"Common Stock", "ADR", "ETF"}
VOL_PLAY_RATIO = 0.5            # opposite-type buying ≥ 50% of our premium …
VOL_PLAY_SECONDS = 15 * 60      # … same expiry, within 15 min → straddle/strangle (Amendment 4)
SPREAD_LEG_SECONDS = 1.0
EARNINGS_DAYS = 7
WHALE_PREMIUM = 1_000_000
REPEAT_MIN = 2

SETUPS = ("pre_earnings", "far_otm", "whale_sweep", "repeat_buyer", "sweep", "clean_other")
PUT_SALE = "put_sale"           # research only (Amendment 9): not in SETUPS, not in pure_all, not traded live
PUT_SALE_OTM = (0.0, 0.15)


def _opening(a: FlowAlert) -> bool:
    return a.all_opening or (a.volume_oi_ratio or 0) > 1 or (
        a.total_size is not None and a.open_interest is not None and a.total_size > a.open_interest)


_BY_TIME: dict[int, tuple[list, int, list, list]] = {}    # id(same_day) → (that list, its length, times, alerts by time)


def _near(a: FlowAlert, same_day: list[FlowAlert], seconds: float) -> list[FlowAlert]:
    """`same_day` alerts within `seconds` of a (inclusive) — the only ones the time-limited checks below can match.
    Speed-up 10-16: the full scan per alert made a busy ticker-day quadratic (SPY ~1,200 prints → cold Sightings 93 s).
    The time-sorted copy is kept per list (callers build a list, then judge every alert against it); the entry holds
    the list itself, so its id can't be reused, and a list that grew gets a new index."""
    e = _BY_TIME.get(id(same_day))
    if e is None or e[0] is not same_day or e[1] != len(same_day):
        by_time = sorted(same_day, key=lambda o: o.created_at)
        e = (same_day, len(same_day), [o.created_at for o in by_time], by_time)
        if len(_BY_TIME) >= 512:
            _BY_TIME.clear()
        _BY_TIME[id(same_day)] = e
    w = timedelta(seconds=seconds)
    return e[3][bisect_left(e[2], a.created_at - w):bisect_right(e[2], a.created_at + w)]


def gate_failures(a: FlowAlert, same_day: list[FlowAlert], as_of: datetime) -> list[str]:
    """Reasons `a` is not a pure directional buy ([] = passes). `same_day`: the ticker's alerts on a's session."""
    out = []
    if a.ask_share < BUY_SHARE:
        out.append(f"not a buy (ask-side {a.ask_share * 100:.0f}% < {BUY_SHARE * 100:.0f}%)")
    if a.has_multileg:
        out.append("multi-leg")
    if a.has_floor:
        out.append("floor/cross trade")
    if not _opening(a):
        out.append("not clearly opening")
    if not MONEYNESS[0] <= a.otm_pct <= MONEYNESS[1]:
        out.append(f"moneyness {a.otm_pct * 100:+.0f}% outside −5%…+30%")
    if not DTE_RANGE[0] <= a.dte <= DTE_RANGE[1]:
        out.append(f"DTE {a.dte} outside 7–90")
    if a.issue_type not in GATE_TYPES:
        out.append(f"issue type {a.issue_type or 'unknown'}")
    elif a.issue_type == "ETF" and a.kind == "put":
        out.append("ETF put (likely hedge)")
    for o in _near(a, same_day, VOL_PLAY_SECONDS):
        if o.id == a.id or o.ticker != a.ticker or o.created_at > as_of or o.has_multileg:
            continue
        if (o.kind != a.kind and o.expiry == a.expiry and o.ask_share >= BUY_SHARE
                and o.total_premium >= VOL_PLAY_RATIO * a.total_premium
                and abs((o.created_at - a.created_at).total_seconds()) <= VOL_PLAY_SECONDS):
            out.append("call and put both bought (vol play)")
            break
    for o in _near(a, same_day, SPREAD_LEG_SECONDS):
        if (o.id != a.id and o.ticker == a.ticker and o.kind == a.kind and o.bid_share >= BUY_SHARE
                and abs((o.created_at - a.created_at).total_seconds()) <= SPREAD_LEG_SECONDS):
            out.append("same-second sold leg (spread leg)")
            break
    return out


def repeat_buys(a: FlowAlert, recent: list[FlowAlert], as_of: datetime) -> int:
    """Other gate-passing buys in a's direction among `recent` (the ticker's alerts, last 3 sessions) known by as_of.
    Sold premium and closing prints don't count as repeat buying (Amendment 4)."""
    by_day: dict = {}
    for o in recent:
        by_day.setdefault(o.session_date, []).append(o)
    return sum(1 for o in recent
               if o.id != a.id and o.ticker == a.ticker and o.created_at <= as_of and o.direction == a.direction
               and not gate_failures(o, by_day[o.session_date], as_of))


def setup_for(a: FlowAlert, earnings: list[date], repeat: int) -> str:
    """First matching setup for a gate-passing alert."""
    d = a.session_date
    if any(d < e <= d + timedelta(days=EARNINGS_DAYS) for e in earnings):
        return "pre_earnings"
    if a.otm_pct > FAR_OTM:
        return "far_otm"
    if a.has_sweep and a.total_premium >= WHALE_PREMIUM:
        return "whale_sweep"
    if repeat >= REPEAT_MIN:
        return "repeat_buyer"
    if a.has_sweep:
        return "sweep"
    return "clean_other"


def pure_only(alerts: list[FlowAlert], as_of: datetime) -> list[FlowAlert]:
    """Alerts that pass the gate, judged against their ticker's same-session alerts (Amendment 9: official candidates)."""
    by_day: dict = {}
    for a in alerts:
        by_day.setdefault((a.ticker, a.session_date), []).append(a)
    return [a for a in alerts if not gate_failures(a, by_day[(a.ticker, a.session_date)], as_of)]


def is_put_sale(a: FlowAlert, same_day: list[FlowAlert], as_of: datetime) -> bool:
    """Bid-side opening put, 7–90 DTE, 0…+15% OTM, failing the gate only for not being a buy → bullish (Amendment 9)."""
    if a.kind != "put" or a.bid_share < BUY_SHARE or not PUT_SALE_OTM[0] <= a.otm_pct <= PUT_SALE_OTM[1]:
        return False
    fails = gate_failures(a, same_day, as_of)
    return len(fails) == 1 and fails[0].startswith("not a buy")
