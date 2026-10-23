"""History lookup — "how did bets like this do?" for any directional bet UW flags, not only our signals.

Unit = one bet per (ticker, direction, kind) per day: the biggest alert of that bet (`core/backtest/simple.day_trades`),
the same unit the history rows hold. Outcome = x5: 5-session stock return in the bet's direction minus SPY's move in
that direction, net of costs. Descriptive only: it never feeds the frozen filter, and callers must not rank by it
(that would be an untested second filter). Point-in-time: a row counts only once its 5-session hold has closed
before `before`."""
from __future__ import annotations

import bisect
from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from statistics import mean, median

from .history import period_label
from .signals import exit_session

MIN_MATCHES = 30
PERIOD_MIN = 10           # a period needs this many matches to vote on "same direction in every period"

KINDS = {"PURE": "clean buy", "PUT_SALE": "put sale", "NOISE": "not a clean buy"}
# Back-off: drop the least important trait first until a bucket has MIN_MATCHES.
DROP_ORDER = ("sector", "sweep", "dte", "otm", "premium")
TRAITS = ("direction", "opt_type", "kind", "premium", "dte", "otm", "sweep", "sector")


@dataclass(frozen=True)
class Bet:
    session_date: date
    ticker: str
    direction: int
    opt_type: str            # call / put
    kind: str                # clean buy / put sale / not a clean buy
    premium: float
    dte: int
    otm_pct: float
    sweep: bool
    sector: str | None
    x5: float | None = None
    gate_fail: str | None = None


def bands(premium: float, dte: int, otm_pct: float) -> tuple[str, str, str]:
    p = "<100K" if premium < 1e5 else "100K–500K" if premium < 5e5 else "500K–1M" if premium < 1e6 else "≥1M"
    d = "≤7d" if dte <= 7 else "8–30d" if dte <= 30 else "31–90d" if dte <= 90 else ">90d"
    o = "ITM" if otm_pct < 0 else "0–5% OTM" if otm_pct < 0.05 else "5–15% OTM" if otm_pct < 0.15 else ">15% OTM"
    return p, d, o


def bet_from_raw(r: dict, extra: dict) -> Bet:
    """History pickle row (+ its alert extras) → Bet."""
    return Bet(r["session_date"], r["ticker"], r["direction"], str(extra.get("type") or "?"),
               KINDS.get(r.get("label"), "not a clean buy"), float(r.get("premium") or 0), int(r.get("dte") or 0),
               float(r.get("otm_pct") or 0), bool(extra.get("has_sweep")), r.get("sector"), r.get("x5"),
               r.get("gate_fail"))


def traits(b: Bet) -> dict[str, object]:
    p, d, o = bands(b.premium, b.dte, b.otm_pct)
    return {"direction": b.direction, "opt_type": b.opt_type, "kind": b.kind, "premium": p, "dte": d, "otm": o,
            "sweep": b.sweep, "sector": b.sector or "Unknown"}


def _levels() -> list[tuple[str, ...]]:
    out, keep = [TRAITS], list(TRAITS)
    for t in DROP_ORDER:
        keep.remove(t)
        out.append(tuple(keep))
    return out


LEVELS = _levels()


def _stats(items: list[tuple[date, str, float]]) -> dict:
    xs = [x for _, _, x in items]
    if not xs:
        return {"matches": 0, "win_share": None, "avg": None, "median": None}
    return {"matches": len(xs), "win_share": sum(x > 0 for x in xs) / len(xs), "avg": mean(xs), "median": median(xs)}


def _pct(x: float) -> str:
    s = f"{x * 100:+.1f}%"                          # true minus, as everywhere in the app; a move that rounds to zero
    return "0.0%" if s in ("+0.0%", "-0.0%") else s.replace("-", "−")   # has no sign


class _Bucket:
    def __init__(self, items: list[tuple[date, str, float]]):
        self.items = sorted(items, key=lambda it: it[0])
        self.dates = [it[0] for it in self.items]

    def known(self, before: date) -> list[tuple[date, str, float]]:
        return self.items[: bisect.bisect_left(self.dates, before)]


_EMPTY = _Bucket([])


class LookupIndex:
    """Bucket index over history bets. Each bucket list is sorted by the date its outcome became known, so a
    point-in-time cut is one bisect."""

    def __init__(self, bets: list[Bet]):
        self._by: list[dict[tuple, list[tuple[date, str, float]]]] = [defaultdict(list) for _ in LEVELS]
        self._all: list[tuple[date, str, float]] = []
        per_day: dict[date, tuple[date, str]] = {}
        for b in bets:
            if b.x5 is None:
                continue
            if b.session_date not in per_day:
                per_day[b.session_date] = (exit_session(b.session_date), period_label(b.session_date))
            item = (*per_day[b.session_date], b.x5)
            self._all.append(item)
            t = traits(b)
            for i, level in enumerate(LEVELS):
                self._by[i][tuple(t[k] for k in level)].append(item)
        self._buckets = [{k: _Bucket(v) for k, v in m.items()} for m in self._by]
        self._base = _Bucket(self._all)
        self._base_stats: dict[date, dict] = {}
        self.size = len(self._all)

    def baseline(self, before: date) -> dict:
        if before not in self._base_stats:
            self._base_stats[before] = _stats(self._base.known(before))
        return self._base_stats[before]

    def lookup(self, b: Bet, before: date) -> dict:
        t = traits(b)
        items: list = []
        # no sector given (a typed lookup without a ticker): pool every sector instead of matching the "Unknown" group
        first = 1 if b.sector is None else 0
        level = first
        for level, keys in list(enumerate(LEVELS))[first:]:
            items = self._buckets[level].get(tuple(t[k] for k in keys), _EMPTY).known(before)
            if len(items) >= MIN_MATCHES:
                break
        dropped = list(DROP_ORDER[first:level])
        by_period: dict[str, list] = defaultdict(list)
        for it in items:
            by_period[it[1]].append(it)
        periods = [{"period": p} | _stats(v) for p, v in sorted(by_period.items(), key=lambda kv: min(i[0] for i in kv[1]))]
        voting = [p["avg"] > 0 for p in periods if p["matches"] >= PERIOD_MIN]
        agree = None if len(voting) < 2 else len(set(voting)) == 1
        out = _stats(items) | {
            "traits": {k: t[k] for k in LEVELS[level]}, "traits_dropped": dropped,
            "thin": len(items) < MIN_MATCHES, "periods": periods, "periods_agree": agree,
            "baseline": self.baseline(before),
        }
        out["in_plain_words"] = plain_words(out)
        return out


def plain_words(o: dict) -> str:
    if o["matches"] == 0:
        return "No earlier bets like this in the history — too few to tell."
    s = (f"Of {o['matches']:,} earlier bets like this, {o['win_share']:.0%} beat the S&P 500 over the five-day hold; "
         f"average {_pct(o['avg'])} vs the S&P (all bets: {_pct(o['baseline']['avg'])}).")
    if o["thin"]:
        return s + " Too few to tell."
    if o["periods_agree"] is False:
        return s + " The test periods disagree, so treat it as noise."
    if o["periods_agree"]:
        return s + " Same direction in every test period — still not a tested signal."
    voting = [p["period"] for p in o.get("periods", []) if p["matches"] >= PERIOD_MIN]
    if voting:
        return s + f" Only {voting[0]} has {PERIOD_MIN} or more of them, so there's no second period to compare it with."
    return s + f" No test period has {PERIOD_MIN} or more of them on its own, so the periods can't be compared."
