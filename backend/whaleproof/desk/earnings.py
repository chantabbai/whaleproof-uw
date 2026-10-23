"""Earnings tab (W2): is the option market's implied move cheap or rich vs this stock's own past report moves?

Pre-declared 2026-10-04 (docs/EARNINGS-MOVES.md, Method), before any outcome was computed:
  implied I  = UW `expected_move_perc` (front-month ATM straddle × 0.85; assumed captured before the report)
  actual A   = UW `post_earnings_move_1d` (verified vs our bars: PM close D+1/close D, AM close D/close D−1)
  past H     = median |A| of the ticker's prior reports (report_date < event, within 3 years, last 8, at least 4)
  label      = cheap I/H < 0.8 · fair · rich I/H > 1.25
  beat       = |A| > I   (primary outcome; move_vs_implied = |A|/I; edge = |A| − I, at-expiry straddle proxy)
Descriptive only — never feeds the frozen signal filter."""
from __future__ import annotations

import statistics as st
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from whaleproof import market_calendar as mc

CHEAP, RICH = 0.8, 1.25
MIN_PAST, MAX_PAST, LOOKBACK = 4, 8, timedelta(days=3 * 365)
JUNK_IMPLIED = 0.5          # implied moves above 50% are junk values on illiquid names (docs/EARNINGS-MOVES.md)
PATH = "/api/earnings/{t}"


@dataclass(frozen=True)
class Report:
    day: date
    time: str
    implied: float | None
    actual: float | None


def _num(x) -> float | None:
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def parse_reports(rows: list[dict]) -> list[Report]:
    out = []
    for r in rows:
        try:
            d = date.fromisoformat(str(r.get("report_date"))[:10])
        except ValueError:
            continue
        imp = _num(r.get("expected_move_perc"))
        out.append(Report(d, r.get("report_time") or "unknown", imp if imp and imp > 0 else None,
                          _num(r.get("post_earnings_move_1d"))))
    return sorted(out, key=lambda r: r.day)


def past_moves(reports: list[Report], before: date) -> list[float]:
    prior = [abs(r.actual) for r in reports if before - LOOKBACK <= r.day < before and r.actual is not None]
    return prior[-MAX_PAST:]


def past_median(reports: list[Report], before: date) -> float | None:
    p = past_moves(reports, before)
    return st.median(p) if len(p) >= MIN_PAST else None


def _past_note(n: int) -> str:
    return f"only {n} past report{'' if n == 1 else 's'} (need {MIN_PAST})"


def classify(implied: float | None, past: float | None) -> str | None:
    if not implied or not past:
        return None
    r = round(implied / past, 6)
    return "cheap" if r < CHEAP else "rich" if r > RICH else "fair"


def score_reports(ticker: str, reports: list[Report]) -> list[dict]:
    """Past reports with implied, actual and enough earlier history → one scored event each."""
    out = []
    for r in reports:
        if r.implied is None or r.actual is None:
            continue
        h = past_median(reports, r.day)
        if h is None or h <= 0:
            continue
        a = abs(r.actual)
        out.append({"ticker": ticker, "day": r.day.isoformat(), "time": r.time, "implied": r.implied, "past": h,
                    "ratio": r.implied / h, "label": classify(r.implied, h), "actual": r.actual, "beat": a > r.implied,
                    "move_vs_implied": a / r.implied, "edge": a - r.implied})
    return out


def _stats(ev: list[dict]) -> dict:
    return {"reports": len(ev), "beat": round(sum(e["beat"] for e in ev) / len(ev), 4),
            "median_move_vs_implied": round(st.median(e["move_vs_implied"] for e in ev), 4),
            "mean_edge": round(st.fmean(e["edge"] for e in ev), 4)}


def _group(ev: list[dict], key) -> dict:
    g: dict = {}
    for e in ev:
        g.setdefault(key(e), []).append(e)
    return {k: _stats(v) for k, v in sorted(g.items())}


def summarize(ev: list[dict]) -> dict:
    if not ev:
        return {"all": None, "by_label": {}, "by_year": {}, "by_label_year": {}, "by_time": {}}
    labels = {lab: [e for e in ev if e["label"] == lab] for lab in ("cheap", "fair", "rich")}
    return {"all": _stats(ev),
            "by_label": {k: _stats(v) for k, v in labels.items() if v},
            "by_year": _group(ev, lambda e: e["day"][:4]),
            "by_label_year": {k: _group(v, lambda e: e["day"][:4]) for k, v in labels.items() if v},
            "by_time": _group(ev, lambda e: e["time"])}


def history_rows(reports: list[Report], before: date | None = None) -> list[dict]:
    """Past reports newest first (last MAX_PAST with an actual move): day, time, implied, actual, beat."""
    past = [r for r in reports if r.actual is not None and (before is None or r.day < before)]
    past = list({r.day: r for r in past}.values())[-MAX_PAST:]     # UW can list a report twice (HLN 10-23)
    return [{"day": r.day.isoformat(), "time": r.time, "implied": r.implied, "actual": r.actual,
             "beat": None if r.implied is None else abs(r.actual) > r.implied} for r in reversed(past)]


def upcoming(calendar: list[dict], reports: dict[str, list[Report]]) -> list[dict]:
    """Calendar rows (live.earnings_session) + cached past reports → cheap/fair/rich label with the reason it is
    missing when it can't be given."""
    out = []
    for c in calendar:
        t, day, imp = c["ticker"], date.fromisoformat(c["report_date"]), c.get("expected_move_perc")
        rs = reports.get(t)
        prior = past_moves(rs, day) if rs else []
        past = st.median(prior) if len(prior) >= MIN_PAST else None
        note = None
        if imp is None:
            note = "No implied move yet"
        elif imp > JUNK_IMPLIED:
            note = f"implied move looks wrong ({imp:.0%})"
        elif not rs:
            note = "no past reports cached"
        elif past is None:
            note = _past_note(len(prior))
        ok = note is None and past
        out.append({"ticker": t, "date": c["report_date"], "time": c.get("report_time") or "unknown",
                    "implied": imp, "past": past, "ratio": round(imp / past, 4) if ok else None,
                    "label": classify(imp, past) if ok else None, "note": note,
                    "sector": c.get("sector"), "marketcap": c.get("marketcap"),
                    "history_reports": len(prior), "history": history_rows(rs, day) if rs else []})
    return out


def reported(row: dict, now: datetime) -> bool:
    """Today's before-the-open report is out from 9:30 ET. After-the-close ones land at varying times after 4 PM, so
    they aren't marked (the 6 PM reporting_day rule drops them); unknown times aren't guessed."""
    local = now.astimezone(mc.NY)
    if row["date"] != local.date().isoformat():
        return False
    return row["time"] == "premarket" and (local.hour, local.minute) >= (9, 30)


def load_reports(store, ticker: str) -> list[Report] | None:
    """Cached /api/earnings/{t} (any age, no network) → reports, or None when the ticker was never fetched."""
    from whaleproof.core.data_layer.fetch import cache_key, rows
    p = store.cache_get(cache_key(PATH.format(t=ticker), {}), None)
    return None if p is None else parse_reports(rows(p))


def ticker_view(ticker: str, reports: list[Report] | None, calendar: list[dict], today: date) -> dict:
    """Ticker page card: the next report (calendar first, else the cached history's own next row) labeled, and the
    past reports with how the implied move did."""
    rs = reports or []
    cal = [c for c in calendar if c["ticker"] == ticker]
    if not cal:
        nxt = next((r for r in rs if r.day >= today), None)
        cal = [] if nxt is None else [{"ticker": ticker, "report_date": nxt.day.isoformat(), "report_time": nxt.time,
                                       "expected_move_perc": nxt.implied, "from_history": True}]
    up = upcoming(cal[:1], {ticker: rs} if rs else {})
    nx = up[0] | {"from_history": bool(cal[0].get("from_history"))} if up else None
    if nx and nx["from_history"]:      # old front-month implied may expire before the report: no label yet
        nx |= {"label": None, "ratio": None, "note": "labeled once the report is within 5 sessions"}
    return {"ticker": ticker, "next": nx, "history": history_rows(rs, today),
            "scored": [{k: e[k] for k in ("day", "label", "beat", "ratio")} for e in score_reports(ticker, rs)][-8:][::-1]}
