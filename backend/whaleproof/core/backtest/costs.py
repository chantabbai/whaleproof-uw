"""Cost comparison (pre-registration Amendment 18) — report only, never a test or a ranking input.

Real option results of the whale's contract (5-session hold) at three fill levels from the same cached daily rows:
mid (best case), normal (the pre-registered fills) and wide (1.5 × the half gap each way). Per finalist and for the
Take list (Amendment 16 caps replayed on the backtest rows; no 9:45 check existed, so nothing is skipped there).
Live rule: a finalist passing the holdout joins the live Take list only if its normal-level average > 0 on ≥ 30
measured trades."""
from __future__ import annotations

import statistics
from datetime import date

from whaleproof import market_calendar as mc
from whaleproof.core.journal.take import take_plan
from whaleproof.core.verdict.setups import SETUPS

from . import combos as cb

LEVELS = (("mid", "opt_r5_mid", "Mid (best case)"), ("normal", "opt_r5", "Normal (pre-registered)"),
          ("wide", "opt_r5_wide", "Wide (bad day)"))
MIN_MEASURED = 30
HOLD = 5


def _stats(vals: list[float]) -> dict:
    if not vals:
        return {"n": 0, "win_rate": None, "mean": None, "median": None, "worst": None}
    return {"n": len(vals), "win_rate": sum(v > 0 for v in vals) / len(vals), "mean": statistics.fmean(vals),
            "median": statistics.median(vals), "worst": min(vals)}


def _levels(rows: list) -> dict:
    measured = [r for r in rows if r.opt_r5 is not None]          # same rows at every level
    out = {k: _stats([getattr(r, f) for r in measured if getattr(r, f) is not None]) for k, f, _ in LEVELS}
    n, mean = out["normal"]["n"], out["normal"]["mean"]
    out["live_ok"] = "cost check unknown" if n < MIN_MEASURED else "yes" if mean > 0 else "no"
    return out


def _matched(rows: list, finalists: dict) -> dict[str, list]:
    return {name: [r for r in rows if r.setup in SETUPS and cb.matches(r, tuple(blocks))]
            for name, blocks in finalists.items()}


def _exit_by(entry: date) -> date:
    d = entry
    for _ in range(HOLD - 1):
        d = mc.next_session(d)
    return d


def take_rows(rows: list, finalists: dict) -> list:
    """Backtest rows the Take list (≤ 3 new per finalist per day, ≤ 10 open) would have held."""
    names = list(finalists)
    matched = _matched(rows, finalists)
    by_id: dict[str, object] = {}
    tags: dict[str, list[str]] = {}
    for name in names:
        for r in matched[name]:
            by_id[r.alert_id] = r
            tags.setdefault(r.alert_id, []).append(name)
    cands = []
    for aid, r in by_id.items():
        entry = mc.next_session(r.session_date)
        cands.append({"pick_id": aid, "ticker": r.ticker, "entry_session": entry.isoformat(),
                      "exit_by": _exit_by(entry).isoformat(), "premium": r.premium,
                      "finalists": [n for n in names if n in tags[aid]]})
    plan = take_plan(cands, {})
    return [by_id[aid] for aid, v in plan.items() if v == "take"]


def cost_table(rows: list, finalists: dict) -> dict:
    out = {name: _levels(sel) for name, sel in _matched(rows, finalists).items()}
    out["Take list"] = _levels(take_rows(rows, finalists))
    return out


def render(table: dict, meta: dict) -> str:
    pct = lambda v, d=1: "–" if v is None else f"{v * 100:+.{d}f}%"   # noqa: E731
    lines = [f"# Cost comparison — {meta['phase']} ({meta['start']} → {meta['end']})", "",
             "Pre-registration Amendment 18 — **report only** (tests and pass/fail stay as registered). Real option "
             "results of the whale's contract, 5-session hold, at three fill levels on the same trades:",
             "- **Mid**: buy at the entry day's open, sell at the exit day's mid.",
             "- **Normal**: open + ½ the bid/ask gap, sell at the exit day's bid (the pre-registered fills).",
             "- **Wide**: open + ¾ gap, sell at mid − ¾ gap (a bad-fill day).",
             "Gaps come from UW's **closing** quotes; gaps at the open are usually wider, so even Normal may flatter. "
             "Trades without an entry-day trade are not measured at any level.",
             "**Live Take list rule:** a finalist that passes the holdout joins only if Normal average > 0 on "
             f"≥ {MIN_MEASURED} measured trades.", "",
             "| group | level | trades | win rate | average | median | worst | live rule |",
             "|---|---|---|---|---|---|---|---|"]
    for name, t in table.items():
        for k, _, label in LEVELS:
            s = t[k]
            lines.append(f"| {name} | {label} | {s['n']} | {pct(s['win_rate'], 0) if s['win_rate'] is not None else '–'}"
                         .replace("+", "") + f" | {pct(s['mean'])} | {pct(s['median'])} | {pct(s['worst'])} | "
                         + (t["live_ok"] if k == "normal" else "") + " |")
    if meta["phase"] == "train":
        lines += ["", "*Train = in-sample: the live rule is applied to the holdout only.*"]
    lines += ["", "*Not investment advice. Past performance does not guarantee future results.*", ""]
    return "\n".join(lines)
