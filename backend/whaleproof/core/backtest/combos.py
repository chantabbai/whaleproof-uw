"""Strategy combinations on TRAIN (pre-registration Amendment 11).

Simple building blocks, tested alone, in pairs and in cross-family triples. Each combination is measured for return
(vs the market) AND risk (biggest drop, worst day, losing streaks), pulled toward zero when thin, and must work in both
halves of the train year. Ranked risk-first; at most 3 finalists go to the one-time holdout exam (family C).
Pure functions over simple-backtest rows; never reads holdout data (the caller passes train rows only)."""
from __future__ import annotations

import itertools
import statistics
from collections import defaultdict
from datetime import date

from whaleproof.core.verdict.setups import SETUPS

from .analysis import boot_test

MIN_TRADES, MIN_DAYS, SHRINK_DAYS = 100, 60, 60
CAPITAL_SHARE = 1 / 5            # each day's trades share 1/5 of the money (5-day hold)
SIMPLER_WITHIN = 0.10            # a simpler rule wins when its score is within 10% of the best
MAX_FINALISTS = 3
SETUP_LABEL = {"pre_earnings": "before earnings", "far_otm": "far OTM", "whale_sweep": "whale sweep",
               "repeat_buyer": "repeat buyer", "sweep": "sweep", "clean_other": "other clean buy"}


def _known(v, test):
    return None if v is None else test(v)


# name → (family, predicate). Predicate returns None when the fact is unknown (row excluded, not counted as "no").
BLOCKS: dict[str, tuple[str, object]] = {
    **{f"setup: {SETUP_LABEL[s]}": ("setup", (lambda s: lambda r: r.setup == s)(s)) for s in SETUPS},
    "OI confirmed": ("confirmed", lambda r: _known(r.oi_ratio, lambda v: v >= 0.5)),
    "option cheap": ("value", lambda r: None if r.value in (None, "unknown") else r.value == "cheap"),
    "option not rich": ("value", lambda r: None if r.value in (None, "unknown") else r.value != "rich"),
    "≤ 30 days to expiry": ("dte", lambda r: _known(r.dte, lambda v: v <= 30)),
    "31–90 days to expiry": ("dte", lambda r: _known(r.dte, lambda v: 30 < v <= 90)),
    "whale ≥ $1M": ("size", lambda r: _known(r.premium, lambda v: v >= 1e6)),
    "long only": ("direction", lambda r: r.direction > 0),
    "short only": ("direction", lambda r: r.direction < 0),
    "market rising": ("trend", lambda r: _known(r.spy_trend, lambda v: v > 0)),
    "market falling": ("trend", lambda r: _known(r.spy_trend, lambda v: v < 0)),
    "0–5% OTM": ("otm", lambda r: _known(r.otm_pct, lambda v: v <= 0.05)),
    "over 5% OTM": ("otm", lambda r: _known(r.otm_pct, lambda v: v > 0.05)),
}


# Amendment 12 (owner-confirmed 2026-09-28, before the holdout run): the three finalists — also the benchmark.
FINALISTS: dict[str, list[str]] = {
    "F.1": ["OI confirmed", "31–90 days to expiry", "over 5% OTM"],
    "F.2": ["option cheap", "long only"],
    "F.3": ["setup: far OTM", "option not rich", "long only"],
}
FINALIST_NAMES = {"F.1": "Confirmed bold bet (1–3 months, >5% OTM)", "F.2": "Cheap option, long",
                  "F.3": "Far out-of-the-money buy, fair price, long"}


def combinations(max_size: int = 3) -> list[tuple[str, ...]]:
    names = list(BLOCKS)
    out = []
    for k in range(1, max_size + 1):
        for c in itertools.combinations(names, k):
            if len({BLOCKS[b][0] for b in c}) == k:          # never two blocks from one family
                out.append(c)
    return out


def matches(r, combo: tuple[str, ...]) -> bool:
    return all(BLOCKS[b][1](r) is True for b in combo)


def _daily(rows) -> dict[date, float]:
    by = defaultdict(list)
    for r in rows:
        if r.x5 is not None:
            by[r.session_date].append(r.x5)
    return {d: statistics.fmean(v) for d, v in sorted(by.items())}


def stats(rows: list, total_days: int, boot: bool = False) -> dict:
    x5 = [r.x5 for r in rows if r.x5 is not None]
    daily = _daily(rows)
    if not x5:
        return {"n": 0, "n_days": 0}
    eq = peak = mdd = 0.0
    streak = worst_streak = 0
    for v in daily.values():
        eq += v * CAPITAL_SHARE
        peak = max(peak, eq)
        mdd = min(mdd, eq - peak)
        streak = streak + 1 if v < 0 else 0
        worst_streak = max(worst_streak, streak)
    gains, losses = sum(v for v in x5 if v > 0), -sum(v for v in x5 if v < 0)
    mean_daily = statistics.fmean(daily.values())
    n_days = len(daily)
    out = {"n": len(x5), "n_days": n_days, "trades_per_day": len(x5) / total_days if total_days else 0.0,
           "win_rate": sum(v > 0 for v in x5) / len(x5), "mean_x5": mean_daily,
           "profit_factor": gains / losses if losses else None,
           "shrunk": mean_daily * n_days / (n_days + SHRINK_DAYS),
           "max_drawdown": mdd, "worst_day": min(daily.values()) * CAPITAL_SHARE, "losing_streak": worst_streak,
           "total": eq}
    # descriptive: the whale's REAL option, where UW contract history is cached (never used for ranking or pass/fail)
    opt = [r.opt_r5 for r in rows if getattr(r, "opt_r5", None) is not None and r.x5 is not None]
    out |= {"opt_n": len(opt), "opt_coverage": len(opt) / len(x5),
            "opt_mean": statistics.fmean(opt) if opt else None, "opt_median": statistics.median(opt) if opt else None,
            "opt_win_rate": sum(v > 0 for v in opt) / len(opt) if opt else None}
    if boot:
        t = boot_test(list(daily.values()), b=2000)
        out |= {"ci_low": t["ci_low"], "ci_high": t["ci_high"]}
    return out


def _score(s: dict) -> float:
    return s["shrunk"] / max(abs(s["max_drawdown"]), 0.001)     # return per unit of the worst fall


def explore(rows: list, split: date) -> dict:
    """rows = TRAIN simple-backtest rows. Only gate passers (setup in SETUPS) are candidates."""
    rows = [r for r in rows if r.setup in SETUPS and r.x5 is not None]
    total_days = len({r.session_date for r in rows})
    ranked = []
    for combo in combinations():
        sel = [r for r in rows if matches(r, combo)]
        s = stats(sel, total_days)
        if s["n"] < MIN_TRADES or s["n_days"] < MIN_DAYS:
            continue
        first = _daily([r for r in sel if r.session_date < split])
        second = _daily([r for r in sel if r.session_date >= split])
        h1 = statistics.fmean(first.values()) if first else None
        h2 = statistics.fmean(second.values()) if second else None
        stable = h1 is not None and h2 is not None and h1 > 0 and h2 > 0
        if not stable:
            continue
        ranked.append({"blocks": combo, **s, "half1": h1, "half2": h2, "stable": True, "score": _score(s)})
    ranked.sort(key=lambda r: (-r["score"], -r["trades_per_day"], len(r["blocks"])))
    for r in ranked[:20]:                                    # ranges only for what we show
        sel = [x for x in rows if matches(x, r["blocks"])]
        r |= {k: v for k, v in stats(sel, total_days, boot=True).items() if k.startswith("ci_")}
    base = stats(rows, total_days, boot=True)
    return {"ranked": ranked, "finalists": pick_finalists(ranked), "baseline": base,
            "tested": len(combinations()), "total_days": total_days, "split": split.isoformat()}


def pick_finalists(ranked: list[dict]) -> list[dict]:
    """Up to 3: from the combos within 10% of the best remaining score, take the one with fewest blocks; skip combos
    that only add blocks to (or drop blocks from) one already chosen."""
    pool, chosen = list(ranked), []
    while pool and len(chosen) < MAX_FINALISTS:
        best = pool[0]["score"]
        near = [r for r in pool if r["score"] >= best * (1 - SIMPLER_WITHIN)]
        pick = min(near, key=lambda r: (len(r["blocks"]), -r["score"]))
        chosen.append(pick)
        pb = set(pick["blocks"])
        pool = [r for r in pool if not (set(r["blocks"]) <= pb or set(r["blocks"]) >= pb)]
    return chosen


def render(res: dict, meta: dict) -> str:
    pct = lambda v, d=2: "–" if v is None else f"{v * 100:+.{d}f}%"  # noqa: E731
    b = res["baseline"]
    lines = [f"# Strategy lab — train only ({meta['start']} → {meta['end']})", "",
             f"{res['tested']:,} combinations of simple building blocks tested on the learning year. A combination is shown only "
             f"if it had at least {MIN_TRADES} trades on {MIN_DAYS}+ days **and** made money vs the market in both halves "
             f"of the year (split {res['split']}). Ranked by return per unit of the biggest drop, so lower-risk rules "
             "rank higher. **Nothing here is proven**: finalists still face the one-time final exam.", "",
             f"All clean buys together: {b['n']:,} trades, {b['trades_per_day']:.1f}/day, beat the market "
             f"{b['win_rate'] * 100:.0f}% of the time, average {pct(b['mean_x5'])} per trade, biggest drop "
             f"{pct(b['max_drawdown'], 1)}.", "",
             "## Suggested finalists", ""]
    if not res["finalists"]:
        lines.append("None: no combination was both big enough and profitable in both halves of the year.")
    for i, f in enumerate(res["finalists"], 1):
        lines.append(f"{i}. **{' + '.join(f['blocks'])}**: {f['trades_per_day']:.1f} trades/day, beat the market "
                     f"{f['win_rate'] * 100:.0f}%, average {pct(f['mean_x5'])}, biggest drop {pct(f['max_drawdown'], 1)}.")
    lines += ["", "## Top 20", "",
              "| Strategy | Trades/day | Beat the market | Average vs market (95% range) | Biggest drop | Worst day | "
              "Longest losing run | Both halves | Real option (whale's contract): n, win, median |",
              "|---|---|---|---|---|---|---|---|---|"]
    for r in res["ranked"][:20]:
        rng = f" ({pct(r.get('ci_low'))} … {pct(r.get('ci_high'))})" if r.get("ci_low") is not None else ""
        lines.append(f"| {' + '.join(r['blocks'])} | {r['trades_per_day']:.1f} | {r['win_rate'] * 100:.0f}% | "
                     f"{pct(r['mean_x5'])}{rng} | {pct(r['max_drawdown'], 1)} | {pct(r['worst_day'], 1)} | "
                     f"{r['losing_streak']} days | {pct(r['half1'])} / {pct(r['half2'])} | "
                     + (f"{r['opt_n']}, {r['opt_win_rate'] * 100:.0f}%, {pct(r['opt_median'], 0)} |" if r.get("opt_n") else "– |"))
    lines += ["", "*Not investment advice. Past performance does not guarantee future results.*", ""]
    return "\n".join(lines)
