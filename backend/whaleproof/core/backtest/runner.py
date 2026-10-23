from __future__ import annotations

import hashlib
import re
import json
from collections import Counter, defaultdict
from dataclasses import dataclass, field, replace
from datetime import date, timedelta

from whaleproof import market_calendar as mc
from whaleproof.core.data_layer.context import PERSISTENCE_SESSIONS, build_context, oi_ratio
from whaleproof.core.data_layer.models import row_to_alert
from whaleproof.core.data_layer.store import Store
from whaleproof.core.journal.flow_health import flow_health
from whaleproof.core.journal.tracker import evaluate_pick, evaluate_pick_follow
from whaleproof.core.verdict.candidates import MAX_CANDIDATES, prefilter
from whaleproof.core.verdict.setups import PUT_SALE, SETUPS, gate_failures, is_put_sale, pure_only, repeat_buys, setup_for
from whaleproof.core.verdict.verdict import evaluate, hold_em
from whaleproof.core.verdict.weights import V0, Weights

from whaleproof.core.checks.base import human

from .breakdowns import (
    LOW_SAMPLE, bucket_dte, bucket_ivr, bucket_premium, bucket_rr, bucket_score, day_cluster, portfolio,
    top_n_per_day)
from .outcomes import forward_returns
from .stats import summarize_returns

HORIZONS = ("r1", "r5", "r20", "x5", "plan_return", "plan_follow_return")
COST = 0.001  # 5 bps per side on the underlying (entry + exit)
TOP_N = 5     # live official picks per day
OI_CONFIRMED = 0.5
# H6 (pre-registration Amendment 7): fixed-level exits, stop × EM and target × EM; (0.75, 1.25) = current fallback
GRID = [(s, t) for s in (0.75, 1.0, 1.5) for t in (1.25, 2.0)]
DISCLAIMER = "*Not investment advice. Past performance does not guarantee future results.*"


@dataclass(frozen=True)
class BacktestRow:
    session_date: date
    ticker: str
    direction: int
    alert_id: str
    score: float
    label: str
    coverage: float
    scores: dict
    available: dict
    r1: float | None
    r5: float | None
    r20: float | None
    mfe20: float | None
    mae20: float | None
    x5: float | None = None            # r5 minus SPY's 5-day return in the trade direction
    plan_status: str | None = None     # same exit rules as the live tracker
    plan_return: float | None = None
    confidences: dict = field(default_factory=dict)
    hard_fail: bool = False
    oi_ratio: float | None = None       # next-morning OI change / size (measured, never used by the decision)
    score_parity: float | None = None
    rr: float | None = None             # plan reward:risk on the underlying
    dte: int | None = None
    premium: float | None = None
    iv_rank: float | None = None
    sector: str | None = None
    issue_type: str | None = None
    catalyst: str | None = None         # none | event bet | earnings inside
    spy_trend: int | None = None        # +1 SPY above its 50-day average on D, −1 below
    plan_follow_return: float | None = None   # plan exits + exit at next open when the money leaves
    follow_status: str | None = None
    setup: str | None = None            # pure-directional setup; None = failed the gate (noise)
    gate_fail: str | None = None        # first gate failure reason
    otm_pct: float | None = None        # strike distance out of the money (Amendment 11 block)
    value: str | None = None            # cheap / fair / rich / unknown option view (Amendment 11 block)
    opt_r5: float | None = None         # REAL 5-day return of the whale's option (cached UW contract history)
    opt_spread: float | None = None     # its bid/ask spread at entry (share of mid)
    opt_r5_mid: float | None = None     # same, bought/sold at mid (Amendment 18 best case)
    opt_r5_wide: float | None = None    # same, 1.5 × the half gap each way (Amendment 18 bad day)
    em: float | None = None             # plan's holding-period expected move ($)
    grid: dict = field(default_factory=dict)   # "stop x target" (EM multiples) → net plan-exit return (H6)
    plan_days: int | None = None        # sessions held under the current plan rule (1 = sold on the entry day)
    overnight_return: float | None = None   # Amendment 13: day 1 only an emergency stop at 2x stop distance
    overnight_status: str | None = None
    overnight_days: int | None = None


def _spy_r5(store: Store, d: date, direction: int) -> float | None:
    fr = forward_returns(store.get_ohlc("SPY", d, d + timedelta(days=45)), d, direction)
    return fr["r5"] if fr else None


def _spy_trend(store: Store, d: date) -> int | None:
    closes = [b.close for b in store.get_ohlc("SPY", d - timedelta(days=90), d)]
    if len(closes) < 50:
        return None
    return 1 if closes[-1] >= sum(closes[-50:]) / 50 else -1


def _catalyst(v) -> str:
    c = next((c for c in v.checks if c.name == "catalyst"), None)
    if c is None or not c.available:
        return "n/a"
    return "event bet" if "event_trade" in c.tags else "earnings inside" if c.score < 0 else "none"


def repeat_count(store: Store, a, as_of) -> int:
    """Gate-passing same-direction buys on a's ticker in the last 3 sessions (repeat_buyer setup)."""
    start = a.session_date
    for _ in range(PERSISTENCE_SESSIONS - 1):
        start = mc.previous_session(start)
    return repeat_buys(a, [row_to_alert(r) for r in store.alerts_between(start, a.session_date, a.ticker)], as_of)


def _net(x: float | None) -> float | None:
    return None if x is None else x - COST


def grid_returns(pick: dict, bars, ref: float, em: float) -> dict:
    """Net plan-exit return for each GRID cell: levels at ref ± k×EM, same time stop and fill rules as live."""
    d, out = pick["direction"], {}
    for ks, kt in GRID:
        plan = dict(pick["plan"], invalidation=ref - d * ks * em, target=ref + d * kt * em)
        po = evaluate_pick(dict(pick, plan=plan), bars)
        out[f"{ks}x{kt}"] = _net(po["return"]) if po["status"] != "pending" else None
    return out


def run_backtest(store: Store, start: date, end: date, weights: Weights = V0,
                 gate: bool = False) -> tuple[list[BacktestRow], int]:
    """gate=True: v0.6 official-like pool — gate passers only, before the top-40 cut (Amendment 9)."""
    out: list[BacktestRow] = []
    skipped = 0
    for d in mc.sessions(start, end):
        as_of = mc.session_close(d) + timedelta(minutes=15)
        alerts = [row_to_alert(r) for r in store.alerts_between(d, d)]
        visible = [x for x in alerts if x.created_at <= as_of]
        for a in prefilter(pure_only(visible, as_of) if gate else visible)[:MAX_CANDIDATES]:
            bars = store.get_ohlc(a.ticker, d, d + timedelta(days=45))
            fr = forward_returns(bars, d, a.direction)
            if fr is None:
                skipped += 1
                continue
            ref = bars[0].close if bars and bars[0].date == d else a.underlying_price  # D close, same as live
            ctx = replace(build_context(store, a, as_of, ref_price=ref), unusual_pct=None)  # live-only
            v = evaluate(ctx, weights)
            same_day = [x for x in alerts if x.ticker == a.ticker]
            fails = gate_failures(a, same_day, as_of)
            pick = {"pick_id": a.id, "direction": a.direction, "entry_session": mc.next_session(d).isoformat(),
                    "weights_version": weights.version, "kind": "backtest",
                    "plan": {"invalidation": v.plan.invalidation, "target": v.plan.target,
                             "time_stop_sessions": v.plan.time_stop_sessions}}
            po = evaluate_pick(pick, bars)
            po_n = evaluate_pick(dict(pick, plan=dict(pick["plan"], entry_ref=ref)), bars, day1="overnight")
            pick_h = pick | {"session_date": d.isoformat(), "ticker": a.ticker, "contract": a.option_chain}
            state_at = lambda day, _p=pick_h, _a=a: flow_health(  # noqa: E731  pre-open view of `day`
                store, _p, day, whale=_a, alerts_through=mc.previous_session(day))["state"]
            pf = evaluate_pick_follow(pick, bars, state_at)
            spy = _spy_r5(store, d, a.direction)
            r5 = _net(fr["r5"])
            risk = abs(ref - v.plan.invalidation)
            em = hold_em(ref, a.iv, v.plan.time_stop_sessions)
            out.append(BacktestRow(
                session_date=d, ticker=a.ticker, direction=a.direction, alert_id=a.id, score=v.score,
                label=v.label, coverage=v.coverage,
                scores={c.name: round(c.score, 4) for c in v.checks},
                available={c.name: c.available for c in v.checks},
                confidences={c.name: c.confidence for c in v.checks},
                hard_fail=any(c.hard_fail for c in v.checks),
                oi_ratio=oi_ratio(store, a),
                r1=_net(fr["r1"]), r5=r5, r20=_net(fr["r20"]), mfe20=fr["mfe20"], mae20=fr["mae20"],
                x5=(r5 - spy) if r5 is not None and spy is not None else None,
                plan_status=po["status"],
                plan_return=_net(po["return"]) if po["status"] != "pending" else None,
                score_parity=v.score_parity, rr=(abs(v.plan.target - ref) / risk) if risk else None,
                dte=a.dte, premium=a.total_premium, iv_rank=ctx.iv_rank,
                sector=store.get_metric(a.ticker, "all", "sector") or None, issue_type=a.issue_type,
                catalyst=_catalyst(v), spy_trend=_spy_trend(store, d),
                plan_follow_return=_net(pf["return"]) if pf["status"] != "pending" else None,
                follow_status=pf["status"],
                setup=(PUT_SALE if is_put_sale(a, same_day, as_of) else None) if fails
                else setup_for(a, ctx.earnings, repeat_count(store, a, as_of)),
                gate_fail=fails[0] if fails else None,
                em=em, grid=grid_returns(pick, bars, ref, em), plan_days=po.get("sessions_held"),
                overnight_return=_net(po_n["return"]) if po_n["status"] != "pending" else None,
                overnight_status=po_n["status"], overnight_days=po_n.get("sessions_held")))
    out.sort(key=lambda r: (r.session_date, r.ticker, r.direction))
    return out, skipped


def day1_compare(rows: list[BacktestRow]) -> dict:
    """Amendment 13: official-like picks under the current plan rule vs 'hold overnight' (same rows)."""
    top = top_n_per_day(rows, TOP_N)
    out = {}
    for name, ret, days in (("plan", "plan_return", "plan_days"), ("overnight", "overnight_return", "overnight_days")):
        rs = [r for r in top if getattr(r, ret) is not None]
        xs = sorted(getattr(r, ret) for r in rs)
        n = len(xs)
        out[name] = {"n": n, "mean": sum(xs) / n if n else None,
                     "median": (xs[n // 2] if n % 2 else (xs[n // 2 - 1] + xs[n // 2]) / 2) if n else None,
                     "worst": xs[0] if n else None,
                     "day1_share": sum(1 for r in rs if getattr(r, days) == 1) / n if n else None,
                     **portfolio(rs, ret)}
    return out


def _block(rows: list[BacktestRow]) -> dict:
    return {h: summarize_returns([getattr(r, h) for r in rows if getattr(r, h) is not None]) for h in HORIZONS}


BREAKDOWNS = {
    "rr": lambda r: bucket_rr(r.rr),
    "score": lambda r: bucket_score(r.score_parity if r.score_parity is not None else r.score),
    "dte": lambda r: bucket_dte(r.dte),
    "premium": lambda r: bucket_premium(r.premium),
    "ivr": lambda r: bucket_ivr(r.iv_rank),
    "sector": lambda r: r.sector or "n/a",
    "issue": lambda r: r.issue_type or "n/a",
    "catalyst": lambda r: r.catalyst or "n/a",
    "spy_trend": lambda r: {1: "SPY above 50d", -1: "SPY below 50d"}.get(r.spy_trend, "n/a"),
    "weekday": lambda r: r.session_date.strftime("%a"),
    "year": lambda r: str(r.session_date.year),
}
BREAKDOWN_TITLES = {
    "rr": "Reward : risk", "score": "Score (backtestable checks)", "dte": "Days to expiry", "premium": "Alert premium",
    "ivr": "IV rank", "sector": "Sector", "issue": "Stock vs ETF", "catalyst": "Earnings", "spy_trend": "Market trend",
    "weekday": "Weekday", "year": "Year",
}


def _group(rows: list[BacktestRow], key) -> dict:
    g = defaultdict(list)
    for r in rows:
        g[key(r)].append(r)
    return {k: _block(v) for k, v in sorted(g.items())}


def _setup_block(rows: list[BacktestRow], n_days: int) -> dict:
    """Expectancy view: how many trades, how often they win, how much winners outweigh losers."""
    r5 = [r.r5 for r in rows if r.r5 is not None]
    x5 = [r.x5 for r in rows if r.x5 is not None]
    gains, losses = sum(v for v in r5 if v > 0), -sum(v for v in r5 if v < 0)
    return {"n": len(rows), "trades_per_day": len(rows) / n_days if n_days else 0.0,
            "win_rate": sum(v > 0 for v in r5) / len(r5) if r5 else None,
            "mean_r5": sum(r5) / len(r5) if r5 else None, "mean_x5": sum(x5) / len(x5) if x5 else None,
            "profit_factor": gains / losses if losses else None,
            "plan": _block(rows)["plan_return"], "daily_x5": day_cluster(rows, "x5")}


def _gate_reason(reason: str) -> str:
    """'DTE 101 outside 7–90' → 'DTE'; 'not a buy (ask-side 40% < 70%)' → 'not a buy'."""
    return re.sub(r"\s*(\(|[−+\-]?\d).*$", "", reason)


def summarize(rows: list[BacktestRow], skipped: int) -> dict:
    rows = sorted(rows, key=lambda r: (r.session_date, r.ticker, r.direction))
    by_label = defaultdict(list)
    by_month = defaultdict(list)
    by_direction = defaultdict(list)
    by_check: dict[str, dict[str, list]] = defaultdict(lambda: {"supports": [], "opposes": []})
    for r in rows:
        by_label[r.label].append(r)
        by_direction["bullish" if r.direction > 0 else "bearish"].append(r)
        by_month[r.session_date.strftime("%Y-%m")].append(r)
        for name, s in r.scores.items():
            if not r.available.get(name):
                continue
            if s >= 0.33:
                by_check[name]["supports"].append(r)
            elif s <= -0.33:
                by_check[name]["opposes"].append(r)
    return {
        "all": _block(rows),
        "by_label": {k: _block(v) for k, v in sorted(by_label.items())},
        "by_direction": {k: _block(v) for k, v in sorted(by_direction.items())},
        "by_check": {k: {side: _block(v) for side, v in sides.items()} for k, sides in sorted(by_check.items())},
        "by_month": {k: _block(v) for k, v in sorted(by_month.items())},
        "oi_confirmed": {
            "GO_confirmed": _block([r for r in rows if r.label == "GO" and (r.oi_ratio or -1) >= OI_CONFIRMED]),
            "GO_unconfirmed": _block([r for r in rows if r.label == "GO" and r.oi_ratio is not None
                                      and r.oi_ratio < OI_CONFIRMED]),
            "all_confirmed": _block([r for r in rows if (r.oi_ratio or -1) >= OI_CONFIRMED]),
            "all_unconfirmed": _block([r for r in rows if r.oi_ratio is not None and r.oi_ratio < OI_CONFIRMED]),
        },
        **{f"by_{name}": _group(rows, fn) for name, fn in BREAKDOWNS.items()},
        "official_like": _block(top_n_per_day(rows, TOP_N)),
        "official_like_daily": {h: day_cluster(top_n_per_day(rows, TOP_N), h) for h in ("x5", "plan_return")},
        "official_like_portfolio": portfolio(top_n_per_day(rows, TOP_N), "plan_return"),
        "day1_rule": day1_compare(rows),
        "by_setup": _by_setup(rows),
        "gate_fail_counts": dict(sorted(Counter(_gate_reason(r.gate_fail) for r in rows if r.gate_fail).items())),
        "skipped": skipped,
        "n_sessions": len({r.session_date for r in rows}),
    }


def _by_setup(rows: list[BacktestRow]) -> dict:
    n_days = len({r.session_date for r in rows})
    out = {name: _setup_block([r for r in rows if r.setup == name], n_days) for name in SETUPS}
    out["pure_all"] = _setup_block([r for r in rows if r.setup in SETUPS], n_days)
    out["noise"] = _setup_block([r for r in rows if r.setup is None], n_days)
    out[PUT_SALE] = _setup_block([r for r in rows if r.setup == PUT_SALE], n_days)   # research, reported apart
    return out


def summary_hash(summary: dict) -> str:
    return hashlib.sha256(json.dumps(summary, sort_keys=True, default=str).encode()).hexdigest()


def _fmt(b: dict) -> str:
    if not b["n"]:
        return "0 | – | – | – |"
    return (f"{human(b['n'])} | {b['hit_rate']*100:.1f}% ({b['ci_low']*100:.0f}–{b['ci_high']*100:.0f}) | "
            f"{b['mean']*100:+.2f}% | {b['median']*100:+.2f}% |")


def render_report(summary: dict, meta: dict) -> str:
    lines = [f"# WhaleProof Backtest — {meta['start']} → {meta['end']} (weights {meta['weights']})", "",
             "Entry = next session open after the alert day. Returns are in the trade's direction, underlying only, "
             "net of 5 bps slippage per side. Groups under 30 trades are flagged ⚠ low sample.",
             f"Sessions: {summary['n_sessions']} · skipped (no price data): {human(summary['skipped'])} · "
             f"hash `{summary_hash(summary)[:12]}`", "",
             "## Headline: 5-day return in excess of SPY (removes market beta)", "",
             "| group | n | beat-SPY rate (95% CI) | mean excess | median excess |", "|---|---|---|---|---|",
             f"| all | {_fmt(summary['all']['x5'])}"]
    for k, v in list(summary["by_label"].items()) + list(summary["by_direction"].items()):
        lines.append(f"| {k} | {_fmt(v['x5'])}")
    lines += ["", "## Setups (pure-directional gate; no 5/day cap) — expectancy first", "",
              "Win rate alone misleads: profit factor = total gains ÷ total losses (> 1 makes money).", "",
              "| setup | n | trades/day | 5d win | mean 5d | mean vs SPY | profit factor | day-clustered vs SPY (95% CI) |",
              "|---|---|---|---|---|---|---|---|"]
    pct = lambda v: "–" if v is None else f"{v * 100:+.2f}%"  # noqa: E731
    for k, b in summary["by_setup"].items():
        c = b["daily_x5"]
        ci = (f"{c['boot_ci_low'] * 100:+.2f}% … {c['boot_ci_high'] * 100:+.2f}%" if c["n_days"] > 1 else "–")
        flag = " ⚠ low sample" if b["n"] < LOW_SAMPLE else ""
        win = "–" if b["win_rate"] is None else f"{b['win_rate'] * 100:.0f}%"
        pf = "–" if b["profit_factor"] is None else f"{b['profit_factor']:.2f}"
        lines.append(f"| {k}{flag} | {human(b['n'])} | {b['trades_per_day']:.1f} | {win} | "
                     f"{pct(b['mean_r5'])} | {pct(b['mean_x5'])} | {pf} | {ci} |")
    if summary["gate_fail_counts"]:
        lines += ["", "Noise — first gate failure: " + ", ".join(f"{k} {human(v)}" for k, v in
                                                              summary["gate_fail_counts"].items())]
    lines += ["", "## Raw 5-day return and plan exits (target / invalidation / time stop — same rules as live)", "",
              "| group | 5d n | 5d hit (95% CI) | 5d mean | 5d median | plan n | plan hit (95% CI) | plan mean | plan median |",
              "|---|---|---|---|---|---|---|---|---|",
              f"| all | {_fmt(summary['all']['r5'])} {_fmt(summary['all']['plan_return'])}"]
    for k, v in list(summary["by_label"].items()) + list(summary["by_direction"].items()):
        lines.append(f"| {k} | {_fmt(v['r5'])} {_fmt(v['plan_return'])}")
    lines += ["", "## Next-morning OI confirmation (measured pre-open; not used by the 16:30 decision)", "",
              "| group | n | beat-SPY rate (95% CI) | mean excess | median excess |", "|---|---|---|---|---|"]
    for k, v in summary["oi_confirmed"].items():
        lines.append(f"| {k} | {_fmt(v['x5'])}")
    lines += ["", "## Exit rule comparison: fixed plan vs plan + follow the money", "",
              "| group | plan n | plan hit (95% CI) | plan mean | plan median | follow n | follow hit (95% CI) | follow mean | follow median |",
              "|---|---|---|---|---|---|---|---|---|",
              f"| all | {_fmt(summary['all']['plan_return'])} {_fmt(summary['all']['plan_follow_return'])}",
              f"| official-like | {_fmt(summary['official_like']['plan_return'])} {_fmt(summary['official_like']['plan_follow_return'])}"]
    for k, v in summary["by_label"].items():
        lines.append(f"| {k} | {_fmt(v['plan_return'])} {_fmt(v['plan_follow_return'])}")
    lines += ["", "## Official-like: top 5 GO per day (what is traded live)", "",
              "| measure | n | hit rate (95% CI) | mean | median |", "|---|---|---|---|---|",
              f"| vs SPY, 5 days | {_fmt(summary['official_like']['x5'])}",
              f"| plan exits | {_fmt(summary['official_like']['plan_return'])}"]
    for h, c in summary["official_like_daily"].items():
        if c["n_days"]:
            lines.append(f"\nDay-clustered ({h}): {c['n_days']} days, mean {c['mean_daily']*100:+.2f}%/day "
                         f"(bootstrap 95% CI {c['boot_ci_low']*100:+.2f}% to {c['boot_ci_high']*100:+.2f}%), "
                         f"winning days {c['hit_days']*100:.0f}%")
    pf = summary["official_like_portfolio"]
    if pf["n_cohorts"]:
        lines.append(f"\nApprox. portfolio (1/5 capital per daily cohort, plan exits): total {pf['total_return']*100:+.1f}%, "
                     f"max drawdown {pf['max_drawdown']*100:.1f}% over {pf['n_cohorts']} cohorts")
    d1 = summary.get("day1_rule") or {}
    if d1.get("plan", {}).get("n"):
        lines += ["", "## Day-1 rule (Amendment 13): current plan vs hold overnight — official-like top 5", "",
                  "| rule | n | mean | median | worst trade | sold on day 1 | portfolio total | max drawdown |",
                  "|---|---|---|---|---|---|---|---|"]
        for k, label in (("plan", "current (stop/target from day 1)"), ("overnight", "hold overnight (2x emergency stop)")):
            c = d1[k]
            if not c["n"]:
                continue
            lines.append(f"| {label} | {c['n']} | {c['mean']*100:+.2f}% | {c['median']*100:+.2f}% | "
                         f"{c['worst']*100:+.1f}% | {c['day1_share']*100:.0f}% | {c['total_return']*100:+.1f}% | "
                         f"{c['max_drawdown']*100:.1f}% |")
    for name, title in BREAKDOWN_TITLES.items():
        lines += ["", f"## {title}", "", "| bucket | n | beat-SPY (95% CI) | mean excess | median excess | plan n | plan hit | plan mean | plan median |",
                  "|---|---|---|---|---|---|---|---|---|"]
        for k, v in summary[f"by_{name}"].items():
            flag = " ⚠ low sample" if v["x5"]["n"] < LOW_SAMPLE else ""
            lines.append(f"| {k}{flag} | {_fmt(v['x5'])} {_fmt(v['plan_return'])}")
    lines += ["", "## By check (5-day)", "", "| check | side | n | hit rate (95% CI) | mean | median |",
              "|---|---|---|---|---|---|"]
    for k, sides in summary["by_check"].items():
        for side, v in sides.items():
            lines.append(f"| {k} | {side} | {_fmt(v['r5'])}")
    lines += ["", "## By month (5-day)", "", "| month | n | hit rate (95% CI) | mean | median |",
              "|---|---|---|---|---|"]
    for k, v in summary["by_month"].items():
        lines.append(f"| {k} | {_fmt(v['r5'])}")
    lines += ["", DISCLAIMER, ""]
    return "\n".join(lines)
