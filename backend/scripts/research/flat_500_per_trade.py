"""EXPLORATORY: $500 flat per trade, stock only (owner question 2026-10-02, not shown in the UI).
Every bet = buy $500 of the stock at the next session open, sell at the close of the 5th session (r5, net 0.10% round
trip, same unit as the tracker/lookup: one bet per ticker/direction/kind/day). No compounding, no position limit — each
trade is its own $500. Groups: signals (frozen filter tiers) and all directional bets UW flags. Two ways to act:
"with direction" (bullish → buy, bearish → short) and "buy only" (bullish bets bought, bearish skipped; plus bearish
bets bought anyway, to show buying every alert blindly). SPY row = the same $500 put into SPY over the same 5 sessions.
Cache-only. → journal/research/flat-500-per-trade.json
Usage: uv run python scripts/research/flat_500_per_trade.py"""
from __future__ import annotations

import json
import statistics as st

from whaleproof.config import REPO_ROOT, load_settings
from whaleproof.core.data_layer.store import Store
from whaleproof.desk.history import classify_rows, earnings_map, load_raw, period_label

STAKE = 500.0
COST = 0.001          # round trip already netted inside r5 once


def summarise(trades: list[tuple[float, float | None]]) -> dict:
    """trades = (stock return, SPY long return over the same hold or None)."""
    if not trades:
        return {"trades": 0}
    pnl = [STAKE * r for r, _ in trades]
    spy = [STAKE * s for _, s in trades if s is not None]
    return {"trades": len(pnl), "invested": STAKE * len(pnl), "total_pnl": round(sum(pnl), 2),
            "avg_pnl": round(st.fmean(pnl), 2), "median_pnl": round(st.median(pnl), 2),
            "win_share": round(sum(p > 0 for p in pnl) / len(pnl), 3),
            "best": round(max(pnl), 2), "worst": round(min(pnl), 2),
            "spy_same_days_total": round(sum(spy), 2) if spy else None}


def main() -> None:
    store = Store(load_settings().db_path)
    rows = classify_rows(load_raw(REPO_ROOT / "data" / "desk", include_holdout=True), earnings_map(store))
    rows = [r for r in rows if r.r5 is not None]
    groups: dict[str, dict[str, list]] = {}

    def add(group: str, period: str, ret: float, spy: float | None) -> None:
        for p in (period, "All periods"):
            groups.setdefault(group, {}).setdefault(p, []).append((ret, spy))

    for r in rows:
        spy_dir = (r.r5 - r.x5) if r.x5 is not None else None          # SPY move × direction
        spy_long = spy_dir * r.direction if spy_dir is not None else None
        # bearish bet: r5 = -raw - COST, so buying the stock anyway = raw - COST = -r5 - 2*COST
        raw_long = r.r5 if r.direction > 0 else -r.r5 - 2 * COST
        per = period_label(r.session_date)
        if r.tier is not None:                       # the frozen filter only passes bullish bets → one way
            add("Signals · buy", per, r.r5, spy_long)
        add("All bets · with direction", per, r.r5, spy_long)
        if r.direction > 0:
            add("All bets · buy bullish only", per, r.r5, spy_long)
        add("All bets · buy every alert", per, raw_long, spy_long)

    out = {"label": "exploratory ($500 flat per trade, stock, 5 sessions; not in UI)", "method": __doc__,
           "stake": STAKE, "groups": {g: {p: summarise(v) for p, v in ps.items()} for g, ps in groups.items()}}
    (REPO_ROOT / "journal" / "research" / "flat-500-per-trade.json").write_text(json.dumps(out, indent=1))
    for g, ps in out["groups"].items():
        print(f"\n{g}")
        for p, s in sorted(ps.items()):
            print(f"  {p:34} {s['trades']:>7,} trades  P/L ${s['total_pnl']:>12,.0f}  avg ${s['avg_pnl']:>6.2f}"
                  f"  win {s['win_share']:.0%}  SPY same $ {s['spy_same_days_total'] or 0:>12,.0f}")


if __name__ == "__main__":
    main()
