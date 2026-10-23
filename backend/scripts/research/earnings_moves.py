"""EXPLORATORY (W2, owner 2026-10-04; frozen filter untouched): is the earnings implied move cheap or rich vs the
ticker's own past report moves, and did 'cheap' reports beat the implied move more often than 'rich' ones?
Method + thresholds pre-declared before this ran (docs/EARNINGS-MOVES.md, Method):
  scoring in whaleproof/desk/earnings.py (I = UW expected move, H = median |past 1-day moves|, last 8 within 3 y, ≥ 4;
  cheap I/H < 0.8, rich > 1.25; beat = |A| > I). Events 2022-01-01 → 2026-10-02.
Verdict: 'supports' only if cheap beat-rate > rich beat-rate in every year 2023–2026 AND the 95% range of the overall
difference (5-day moving-block bootstrap over report dates) excludes 0; else 'not proven'.
Sensitivity (added after the first run, NOT pre-declared): drop reports whose implied move is > 50% (junk values on
illiquid names, e.g. 4,034 = 403,400%; they wreck the mean edge, barely touch beat rates).
Cross-check: UW actual move vs our daily bars (PM close D+1/close D, AM close D/close D−1).
Cache-only, 0 UW calls. Output holds aggregates only (Rule 11).
→ journal/research/earnings-moves.json   Usage: uv run python scripts/research/earnings_moves.py"""
from __future__ import annotations

import json
import random
import sqlite3
from collections import defaultdict
from datetime import date

from whaleproof.config import REPO_ROOT, load_settings
from whaleproof.desk.earnings import CHEAP, LOOKBACK, MAX_PAST, MIN_PAST, RICH, parse_reports, score_reports, summarize

START, END = date(2022, 1, 1), date(2026, 10, 2)
VERDICT_YEARS = ("2023", "2024", "2025", "2026")
SEED, BOOT, BLOCK = 11, 2000, 5
JUNK_IMPLIED = 0.5


def load(db) -> dict[str, list]:
    out = {}
    for ep, payload in db.execute("select endpoint, payload from raw_cache where key like '/api/earnings/%?{}'"):
        t = ep.rsplit("/", 1)[-1]
        if "/" in ep[len("/api/earnings/"):]:
            continue
        p = json.loads(payload)
        out[t] = parse_reports(p.get("data", []) if isinstance(p, dict) else p)
    return out


def diff(ev: list[dict]) -> float | None:
    c = [e["beat"] for e in ev if e["label"] == "cheap"]
    r = [e["beat"] for e in ev if e["label"] == "rich"]
    return sum(c) / len(c) - sum(r) / len(r) if c and r else None


def boot(ev: list[dict]) -> tuple[float, float]:
    by_day = defaultdict(list)
    for e in ev:
        by_day[e["day"]].append(e)
    days = sorted(by_day)
    blocks = [sum((by_day[d] for d in days[i:i + BLOCK]), []) for i in range(len(days) - BLOCK + 1)]
    rng, vals = random.Random(SEED), []
    for _ in range(BOOT):
        sample = sum((rng.choice(blocks) for _ in range(len(days) // BLOCK)), [])
        v = diff(sample)
        if v is not None:
            vals.append(v)
    vals.sort()
    return vals[int(0.025 * len(vals))], vals[int(0.975 * len(vals)) - 1]


def cross_check(db, reports: dict[str, list]) -> dict:
    n = agree = 0
    for t, rs in reports.items():
        bars = {d: c for d, c in db.execute("select date, close from ohlc_daily where ticker=? and date>=?",
                                            (t, START.isoformat()))}
        if not bars:
            continue
        days = sorted(bars)
        for r in rs:
            if r.actual is None or not (START <= r.day <= END) or r.time not in ("premarket", "postmarket"):
                continue
            d = r.day.isoformat()
            if d not in bars:
                continue
            i = days.index(d)
            a, b = (i - 1, i) if r.time == "premarket" else (i, i + 1)
            if a < 0 or b >= len(days):
                continue
            ours = bars[days[b]] / bars[days[a]] - 1
            n += 1
            agree += abs(ours - r.actual) <= 0.005
    return {"compared": n, "within_half_point": round(agree / n, 4) if n else None}


def main() -> None:
    db = sqlite3.connect(f"file:{load_settings().db_path}?mode=ro", uri=True)
    reports = load(db)
    ev = [e for t, rs in reports.items() for e in score_reports(t, rs) if START.isoformat() <= e["day"] <= END.isoformat()]
    s = summarize(ev)
    yearly = {y: diff([e for e in ev if e["day"][:4] == y]) for y in VERDICT_YEARS}
    lo, hi = boot(ev)
    every_year = all(v is not None and v > 0 for v in yearly.values())
    verdict = "supports" if every_year and lo > 0 else "not proven"
    candidates = sum(1 for rs in reports.values() for r in rs
                     if START <= r.day <= END and r.implied is not None and r.actual is not None)
    clean = [e for e in ev if e["implied"] <= JUNK_IMPLIED]
    clo, chi = boot(clean)
    sens = {"rule": f"implied move <= {JUNK_IMPLIED:.0%} (not pre-declared)", "dropped": len(ev) - len(clean),
            **summarize(clean),
            "cheap_minus_rich_beat": {"all": round(diff(clean), 4), "range95": [round(clo, 4), round(chi, 4)],
                                      "by_year": {y: round(diff([e for e in clean if e["day"][:4] == y]), 4)
                                                  for y in VERDICT_YEARS}}}
    out = {"run": date.today().isoformat(), "exploratory": True,
           "method": {"cheap_below": CHEAP, "rich_above": RICH, "min_past": MIN_PAST, "max_past": MAX_PAST,
                      "lookback_days": LOOKBACK.days, "start": START.isoformat(), "end": END.isoformat(),
                      "bootstrap": f"{BLOCK}-day moving blocks over report dates, {BOOT} draws, seed {SEED}"},
           "tickers": len(reports), "reports_with_implied_and_actual": candidates, "scored": len(ev),
           **s,
           "cheap_minus_rich_beat": {"all": round(diff(ev), 4), "range95": [round(lo, 4), round(hi, 4)],
                                     "by_year": {y: None if v is None else round(v, 4) for y, v in yearly.items()}},
           "verdict": verdict, "sensitivity": sens, "cross_check_bars": cross_check(db, reports)}
    path = REPO_ROOT / "journal" / "research" / "earnings-moves.json"
    path.write_text(json.dumps(out, indent=2) + "\n")
    print(json.dumps({k: out[k] for k in ("scored", "all", "by_label", "cheap_minus_rich_beat", "verdict",
                                          "cross_check_bars")}, indent=1))
    print(json.dumps({k: sens[k] for k in ("dropped", "all", "by_label", "cheap_minus_rich_beat")}, indent=1))


if __name__ == "__main__":
    main()
