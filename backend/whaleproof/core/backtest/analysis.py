"""Pre-registered hypothesis tests (docs/preregistration.md, Amendment 7): day-clustered bootstrap, Holm correction,
signed-weight rescoring, tercile splits and the "tradeable" rule. Pure functions over BacktestRow lists."""
from __future__ import annotations

import statistics
from datetime import timedelta
from collections import defaultdict

import numpy as np

from whaleproof.core.verdict.verdict import GO, MIN_COVERAGE
from whaleproof.core.verdict.weights import BACKTESTABLE, Weights

BOOT_B = 10_000
BOOT_SEED = 42
ALPHA = 0.05
MIN_DAYS = 60
MIN_EFFECT = 0.002   # +0.20% per 5 days (≥ 2× round-trip cost)


def boot_test(daily: list[float], b: int = BOOT_B, seed: int = BOOT_SEED) -> dict:
    """Mean of daily values with percentile CI and a two-sided null-centred bootstrap p."""
    n = len(daily)
    if n == 0:
        return {"n_days": 0, "mean": None, "ci_low": None, "ci_high": None, "p": 1.0}
    x = np.asarray(daily, dtype=float)
    mean = float(x.mean())
    idx = np.random.default_rng(seed).integers(0, n, size=(b, n))
    boots = x[idx].mean(axis=1)
    null = boots - mean                                    # = resampled (x − mean)
    p = max(float(np.mean(np.abs(null) >= abs(mean))), 1 / (b + 1))
    return {"n_days": n, "mean": mean, "ci_low": float(np.percentile(boots, 2.5)),
            "ci_high": float(np.percentile(boots, 97.5)), "p": min(p, 1.0)}


def daily(rows: list, field) -> dict:
    """{day: mean of field} — field is an attribute name or a function of the row."""
    get = field if callable(field) else (lambda r: getattr(r, field))
    by = defaultdict(list)
    for r in rows:
        v = get(r)
        if v is not None:
            by[r.session_date].append(v)
    return {d: statistics.fmean(v) for d, v in by.items()}


def one_sample(rows: list, field) -> dict:
    m = daily(rows, field)
    return boot_test([m[d] for d in sorted(m)])


def paired(a_rows: list, b_rows: list, field) -> dict:
    a, b = daily(a_rows, field), daily(b_rows, field)
    return boot_test([a[d] - b[d] for d in sorted(a.keys() & b.keys())])


def holm(pvals: dict[str, float]) -> dict[str, float]:
    order = sorted(pvals, key=lambda k: pvals[k])
    m, out, running = len(order), {}, 0.0
    for i, k in enumerate(order):
        running = max(running, min(1.0, (m - i) * pvals[k]))
        out[k] = running
    return out


def rescore(r, weights: Weights) -> float:
    """score_parity with signed weights: divide by Σ|w| of available backtestable checks."""
    par = {n: w for n, w in weights.w.items() if n in BACKTESTABLE and r.available.get(n)}
    den = sum(abs(w) for w in par.values())
    if not den:
        return 50.0
    num = sum(w * r.scores.get(n, 0.0) * r.confidences.get(n, 1.0) for n, w in par.items())
    return 50 + 50 * num / den


def _coverage(r, weights: Weights) -> float:
    total = sum(abs(w) for w in weights.w.values())
    return sum(abs(w) for n, w in weights.w.items() if r.available.get(n)) / total if total else 0.0


def is_go(r, weights: Weights) -> bool:
    return not r.hard_fail and rescore(r, weights) >= GO and _coverage(r, weights) >= MIN_COVERAGE


def top_n(rows: list, weights: Weights, n: int = 5) -> list:
    """Live selection under `weights`: GO rows ranked by rescored parity, best n per session."""
    by = defaultdict(list)
    for r in rows:
        if is_go(r, weights):
            by[r.session_date].append(r)
    out = []
    for d in sorted(by):
        out.extend(sorted(by[d], key=lambda r: (-rescore(r, weights), r.ticker))[:n])
    return out


def tercile_cuts(values: list[float]) -> tuple[float, float]:
    return float(np.percentile(values, 100 / 3)), float(np.percentile(values, 200 / 3))


def tercile_split(rows: list, check: str, cuts: tuple[float, float]) -> tuple[list, list]:
    lo, hi = cuts
    avail = [r for r in rows if r.available.get(check)]
    if lo == hi:
        return [r for r in avail if r.scores.get(check, 0.0) > hi], [r for r in avail if r.scores.get(check, 0.0) <= lo]
    return [r for r in avail if r.scores.get(check, 0.0) >= hi], [r for r in avail if r.scores.get(check, 0.0) <= lo]


def tradeable(effect: float | None, p_holm: float, train_effect: float | None, n_days: int) -> bool:
    return (effect is not None and train_effect is not None and p_holm < ALPHA and n_days >= MIN_DAYS
            and effect >= MIN_EFFECT and train_effect > 0)


# ---------- orchestration (Amendment 7) ----------
H5_CHECKS = ("dark_pool", "dp_blocks", "ticker_flow", "sector_flow")
H9_CHECKS = ("skew", "option_sentiment", "iv_rv", "macro_event")
H6_BASE = "0.75x1.25"
H3_MIN_FLAGGED = 300
TOP = 5

DESCRIPTIONS = {
    "H1": "v0.5 top-5/day vs SPY (x5)", "H2": "v1 top-5 − v0.5 top-5 (x5)", "H3": "UW-flagged − unflagged (x5, oriented)",
    "H4": "SKIP − GO, v0.5 labels (x5)", "H6": "chosen stop/target cell − (0.75, 1.25)×EM (plan exit)",
    "H7": "follow-the-money − plan exit (per trade)", "H8": "OI-confirmed − unconfirmed (x5)",
    "H10": "pure gate passers − noise (x5, simple backtest)",
}


def _desc(name: str) -> str:
    if name.startswith("H5.") or name.startswith("H9."):
        return f"{name[3:]}: top − bottom tercile (x5, oriented)"
    if name.startswith("S."):
        return f"setup {name[2:]} vs SPY (x5, simple backtest)"
    if name.startswith("F."):
        from .combos import FINALIST_NAMES, FINALISTS
        return f"finalist {FINALIST_NAMES[name]}: {' + '.join(FINALISTS[name])} (x5)"
    return DESCRIPTIONS[name]


def _available_checks(rows: list, names) -> list[str]:
    return [c for c in names if any(r.available.get(c) for r in rows)]


def _raw_tests(check_rows: list, simple_rows: list, ch: dict) -> dict:
    """Un-oriented test results per family member (Amendment 7 populations)."""
    from whaleproof.core.verdict.setups import SETUPS
    from whaleproof.core.verdict.weights import V05 as CURRENT   # pre-reg H1/H2 baseline = v0.5 (ungated)
    v1 = Weights(ch["v1"]["version"], ch["v1"]["w"])
    out = {"H1": one_sample(top_n(check_rows, CURRENT, TOP), "x5"),
           "H2": paired(top_n(check_rows, v1, TOP), top_n(check_rows, CURRENT, TOP), "x5")}
    fl = [r for r in check_rows if r.available.get("uw_flagged")]
    flagged = [r for r in fl if r.scores.get("uw_flagged", 0) > 0]
    unflagged = [r for r in fl if r.scores.get("uw_flagged", 0) <= 0]
    out["H3"] = paired(flagged, unflagged, "x5") | {
        "n_flagged": len(flagged), "complete_days": len({r.session_date for r in unflagged}),
        "min_ok": len(flagged) >= H3_MIN_FLAGGED and len({r.session_date for r in unflagged}) >= MIN_DAYS}
    out["H4"] = paired([r for r in check_rows if r.label == "SKIP"], [r for r in check_rows if r.label == "GO"], "x5")
    for c in list(H5_CHECKS) + list(H9_CHECKS):
        name = ("H5." if c in H5_CHECKS else "H9.") + c
        if c in ch["cuts"]:
            top, bottom = tercile_split(check_rows, c, tuple(ch["cuts"][c]))
            out[name] = paired(top, bottom, "x5")
        else:                                   # never available on train → stays in the family with p = 1
            out[name] = boot_test([]) | {"not_backtestable": True}
    if ch["h6_cell"] != H6_BASE:
        cell = ch["h6_cell"]
        out["H6"] = one_sample(check_rows, lambda r: (r.grid[cell] - r.grid[H6_BASE])
                               if r.grid.get(cell) is not None and r.grid.get(H6_BASE) is not None else None)
    out["H7"] = one_sample(check_rows, lambda r: (r.plan_follow_return - r.plan_return)
                           if r.plan_follow_return is not None and r.plan_return is not None else None)
    out["H8"] = paired([r for r in check_rows if r.oi_ratio is not None and r.oi_ratio >= 0.5],
                       [r for r in check_rows if r.oi_ratio is not None and r.oi_ratio < 0.5], "x5")
    out["H10"] = paired([r for r in simple_rows if r.setup in SETUPS],   # noise excludes put_sale (Amendment 9)
                        [r for r in simple_rows if r.setup is None], "x5")
    for s in SETUPS:
        out[f"S.{s}"] = one_sample([r for r in simple_rows if r.setup == s], "x5")
    from . import combos as cb
    for name, blocks in (ch.get("finalists") or {}).items():
        sel = [r for r in simple_rows if r.setup in SETUPS and cb.matches(r, tuple(blocks))]
        opt = cb.stats(sel, len({r.session_date for r in simple_rows}) or 1) if sel else {}
        # descriptive only: real option results of the whale's contract (pass/fail stays on x5, as pre-registered)
        out[name] = one_sample(sel, "x5") | {k: opt.get(k) for k in ("opt_n", "opt_coverage", "opt_mean", "opt_median",
                                                                    "opt_win_rate")}
    return out


def choose(check_rows: list, simple_rows: list) -> dict:
    """Train-only choices frozen before the holdout: signed v1, H3/H5/H9 signs, tercile cuts, H6 cell."""
    from whaleproof.core.verdict.weights import V05 as CURRENT   # pre-reg H1/H2 baseline = v0.5 (ungated)

    from .fit import fit_weights
    far = max(r.session_date for r in check_rows) + timedelta(days=1)      # every row is train; nothing scored OOS
    v1 = fit_weights(check_rows, far, "v1", base=CURRENT, signed=True, label="x5")
    avail = _available_checks(check_rows, list(H5_CHECKS) + list(H9_CHECKS))
    cuts = {c: tercile_cuts([r.scores.get(c, 0.0) for r in check_rows if r.available.get(c)]) for c in avail}
    cells = {f"{s}x{t}" for r in check_rows for s, t in [k.split("x") for k in r.grid]}
    cell_mean = {c: statistics.fmean(daily(check_rows, lambda r, c=c: r.grid.get(c)).values())
                 for c in sorted(cells) if daily(check_rows, lambda r, c=c: r.grid.get(c))}
    from . import combos as cb
    ch = {"v1": {"version": v1.version, "w": v1.w, "meta": v1.meta}, "cuts": cuts, "finalists": cb.FINALISTS,
          "h6_cell": max(cell_mean, key=lambda c: (cell_mean[c], c == H6_BASE)) if cell_mean else H6_BASE,
          "h6_cell_means": cell_mean,
          "dropped": sorted(set(H5_CHECKS + H9_CHECKS) - set(avail))}
    raw = _raw_tests(check_rows, simple_rows, ch | {"signs": {}})
    ch["signs"] = {k: (1 if (raw[k]["mean"] or 0) >= 0 else -1) for k in raw
                   if k == "H3" or k.startswith("H5.") or k.startswith("H9.")}
    return ch


def run_tests(check_rows: list, simple_rows: list, ch: dict) -> dict:
    out = {}
    for k, t in _raw_tests(check_rows, simple_rows, ch).items():
        sign = ch["signs"].get(k, 1)
        t = dict(t)
        if t["mean"] is not None and sign < 0:
            t["mean"], t["ci_low"], t["ci_high"] = -t["mean"], -t["ci_high"], -t["ci_low"]
        t["sign"] = sign
        t["desc"] = _desc(k)
        short = t["n_days"] < MIN_DAYS or (k == "H3" and not t["min_ok"])
        t["status"] = ("not backtestable" if t.get("not_backtestable") else
                       "insufficient data" if short else "tested")
        if short:
            t["p"] = 1.0
        out[k] = t
    return out


def family(name: str) -> str:
    """Amendment 8: A = what we trade (setups + H10, simple engine); B = weighted-score hypotheses.
    Amendment 12: C = the three strategy finalists."""
    if name.startswith("F."):
        return "C"
    return "A" if name.startswith("S.") or name == "H10" else "B"


def finalize(results: dict, train_effects: dict, phase: str = "holdout") -> dict:
    """Holm within each family; "tradeable" only on the holdout (on train it would compare train with itself)."""
    adj = {}
    for fam in ("A", "B", "C"):
        adj |= holm({k: v["p"] for k, v in results.items() if family(k) == fam})
    out = {}
    for k, v in results.items():
        te = train_effects.get(k)
        out[k] = v | {"p_holm": adj[k], "train_mean": te,
                      "tradeable": phase == "holdout" and v["status"] == "tested"
                      and tradeable(v["mean"], adj[k], te, v["n_days"])}
    return out


def render(results: dict, meta: dict) -> str:
    pct = lambda v: "–" if v is None else f"{v * 100:+.2f}%"  # noqa: E731
    lines = [f"# WhaleProof analysis — {meta['phase']} ({meta['start']} → {meta['end']})", "",
             "Pre-registered tests (docs/preregistration.md, Amendments 7–8). Unit = day; day-clustered bootstrap "
             f"({BOOT_B:,} resamples), two-sided p, Holm within family A (setups + H10) and family B (the rest). "
             "Effects are oriented by the train sign (H3/H5/H9). **Tradeable** = Holm p < 0.05, same sign on train, effect ≥ +0.20%/5d, ≥ 60 days.", "",
             "| test | question | days | effect | 95% CI | p | Holm p | train effect | Tradeable |",
             "|---|---|---|---|---|---|---|---|---|"]
    train = meta["phase"] == "train"
    if train:
        lines[2] += (" **Train = in-sample: choices were made on these rows, so no verdict here — only the holdout "
                     "decides.**")
        lines[4] = lines[4].replace("| Tradeable |", "| in-sample, not a verdict |")
    for k in sorted(results, key=lambda k: (k[0], len(k.split(".")[0]), k)):
        v = results[k]
        verdict = ("in-sample" if train else "**yes**" if v.get("tradeable") else "not proven") \
            if v["status"] == "tested" else v["status"]
        ci = f"{pct(v['ci_low'])} … {pct(v['ci_high'])}" if v["ci_low"] is not None else "–"
        lines.append(f"| {k} | {v['desc']} | {v['n_days']} | {pct(v['mean'])} | {ci} | {v['p']:.4f} | "
                     f"{v.get('p_holm', v['p']):.4f} | {pct(v.get('train_mean'))} | {verdict} |")
    lines += ["", "*Not investment advice. Past performance does not guarantee future results.*", ""]
    return "\n".join(lines)
