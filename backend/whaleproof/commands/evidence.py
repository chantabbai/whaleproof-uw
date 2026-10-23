"""`whaleproof evidence [--holdout]` — Signal Desk noise funnel + performance on history (cache-only, no API calls).

Default: train + post-period (previously seen) → journal/desk-evidence.json.
--holdout: the ONE-TIME holdout test with the frozen filter → journal/desk-holdout.json; refuses if it exists."""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import UTC, date, datetime

from whaleproof.config import REPO_ROOT, load_settings
from whaleproof.core.data_layer.store import Store
from whaleproof.desk.config import DEFAULT_FILTER, HOLDOUT, POST, PRE, TRAIN
from whaleproof.desk.evidence import by_key, funnel, monthly, summarize
from whaleproof.desk.history import (
    HistRow,
    classify_rows,
    earnings_map,
    in_window,
    load_raw,
)

OUT = REPO_ROOT / "journal" / "desk-evidence.json"
HOLDOUT_OUT = REPO_ROOT / "journal" / "desk-holdout.json"
PRE_OUT = REPO_ROOT / "journal" / "desk-preperiod.json"
PRE_FAROTM_OUT = REPO_ROOT / "journal" / "desk-preperiod-farotm.json"
FAROTM_MIN_N = 30   # docs/PREPERIOD-FAROTM-TEST.md: fewer far-OTM signals → "inconclusive"

# Research-backed checks measured one at a time on clean buys (with vs without). Labels → docs/METHODOLOGY.md.
CHECKS = {
    "far_otm_15": ("Strike > 15% out of the money", "Pan & Poteshman (2006): deep-OTM opening buys most informative",
                   lambda r: r.otm_pct > 0.15),
    "whale_1m": ("Premium ≥ $1M", "Size as conviction (UW whale definition); informed traders trade size",
                 lambda r: r.premium >= 1e6),
    "not_rich": ("Option not rich (IV rank < 70)", "Cremers & Weinbaum (2010), Xing-Zhang-Zhao (2010): "
                 "option prices carry information; buying rich vol pays the premium", lambda r: r.value in ("cheap", "fair")),
    "long": ("Bullish (call buy)", "Pan & Poteshman: put:call of opening buys; put buys are hedge-heavy in UW flow",
             lambda r: r.direction > 0),
    "no_earnings": ("No earnings before exit", "Ni, Pan & Poteshman (2008): vol-informed trading peaks before "
                    "earnings — direction is not the bet; IV crush after", lambda r: r.stage != "earnings"),
    "short_dte": ("≤ 30 days to expiry", "Shorter-dated buys = more leverage on a view (descriptive)",
                  lambda r: r.dte <= 30),
}


def filter_hash() -> str:
    return hashlib.sha256(json.dumps(DEFAULT_FILTER.as_dict(), sort_keys=True).encode()).hexdigest()[:16]


def raw_counts(store: Store) -> dict[date, int]:
    return {date.fromisoformat(d): n for d, n in
            store.conn.execute("SELECT session_date, COUNT(*) FROM flow_alerts GROUP BY session_date")}


def farotm_verdict(far: dict, allr: dict, min_n: int = FAROTM_MIN_N) -> str:
    """Pre-registered rule (docs/PREPERIOD-FAROTM-TEST.md): n floor, then beats all directional AND day CI low > 0."""
    if far.get("n", 0) < min_n:
        return "inconclusive"
    return "supports the far-OTM edge" if far["mean"] > allr["mean"] and far["ci_low"] > 0 else "does not support"


def window_report(rows: list[HistRow], counts: dict[date, int]) -> dict:
    clean = [r for r in rows if r.stage != "gate"]
    sig = [r for r in rows if r.tier]
    return {
        "funnel": funnel(rows, counts),
        "all_directional": summarize(rows, ci=True), "clean": summarize(clean, ci=True),
        "signals": summarize(sig, ci=True),
        "tiers": {t: summarize([r for r in sig if r.tier == t], ci=True) for t in ("whale", "far_otm")},
        "rejected_by_stage": by_key([r for r in rows if not r.tier], lambda r: r.stage),
        "signals_monthly": monthly(sig),
        "signals_by_sector": by_key(sig, lambda r: r.sector or "unknown"),
        "checks": {k: {"label": lab, "source": src, "with": summarize([r for r in clean if f(r)]),
                       "without": summarize([r for r in clean if not f(r)])} for k, (lab, src, f) in CHECKS.items()},
        "cluster": _clusters(sig),
    }


def _clusters(sig: list[HistRow]) -> dict:
    """How often same-day signals share a sector (N signals ≠ N independent bets)."""
    by_day: dict = {}
    for r in sig:
        by_day.setdefault(r.session_date, []).append(r.sector or "unknown")
    multi = [v for v in by_day.values() if len(v) > 1]
    clustered = sum(1 for v in multi if max(v.count(s) for s in set(v)) > 1)
    return {"days_with_2plus": len(multi), "days_with_sector_cluster": clustered}


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(prog="whaleproof evidence")
    p.add_argument("--holdout", action="store_true", help="run the ONE-TIME holdout test")
    p.add_argument("--preperiod", action="store_true", help="run the ONE-TIME pre-period test (docs/PREPERIOD-TEST.md)")
    p.add_argument("--preperiod-farotm", action="store_true",
                   help="run the ONE-TIME pre-period far-OTM test (docs/PREPERIOD-FAROTM-TEST.md)")
    args = p.parse_args(argv)
    store = Store(load_settings().db_path)
    counts, earn = raw_counts(store), earnings_map(store)
    meta = {"generated_at": datetime.now(UTC).isoformat(), "filter": DEFAULT_FILTER.as_dict(),
            "filter_hash": filter_hash(), "metric": "x5 = 5-session stock return in signal direction minus SPY, "
            "net 10 bps round trip; entry next open after the flow day",
            "raw_definition": "UW flow alerts with premium ≥ $100K (cache + live pull use the same floor)"}
    if args.preperiod_farotm:
        if PRE_FAROTM_OUT.exists():
            print(f"refusing: pre-period far-OTM test already run → {PRE_FAROTM_OUT}")
            return 1
        rows = in_window(classify_rows(load_raw(REPO_ROOT / "data" / "desk"), earn), *PRE)
        rep = {"meta": meta | {"window": [PRE[0].isoformat(), PRE[1].isoformat()],
                               "label": "pre-period far-OTM tier (out-of-sample, IV rank backfilled, run once)",
                               "prereg": "docs/PREPERIOD-FAROTM-TEST.md", "min_n": FAROTM_MIN_N},
               **window_report(rows, counts)}
        rep["verdict"] = farotm_verdict(rep["tiers"]["far_otm"], rep["all_directional"])
        PRE_FAROTM_OUT.write_text(json.dumps(rep, indent=1, default=str))
        print(f"pre-period far-OTM written → {PRE_FAROTM_OUT}: {rep['verdict']}")
        return 0
    if args.preperiod:
        if PRE_OUT.exists():
            print(f"refusing: pre-period test already run → {PRE_OUT}")
            return 1
        rows = in_window(classify_rows(load_raw(REPO_ROOT / "data" / "desk"), earn), *PRE)
        rep = {"meta": meta | {"window": [PRE[0].isoformat(), PRE[1].isoformat()],
                               "label": "pre-period (out-of-sample, never seen, run once)"}, **window_report(rows, counts)}
        sig, allr = rep["signals"], rep["all_directional"]
        rep["verdict"] = ("supports the edge" if sig.get("n") and sig["mean"] > allr["mean"] and sig["ci_low"] > 0
                          else "does not support the edge")
        PRE_OUT.write_text(json.dumps(rep, indent=1, default=str))
        print(f"pre-period written → {PRE_OUT}: {rep['verdict']}")
        return 0
    if args.holdout:
        if HOLDOUT_OUT.exists():
            print(f"refusing: holdout already run → {HOLDOUT_OUT}")
            return 1
        rows = in_window(classify_rows(load_raw(REPO_ROOT / "data" / "desk", include_holdout=True), earn), *HOLDOUT)
        rep = {"meta": meta | {"window": [HOLDOUT[0].isoformat(), HOLDOUT[1].isoformat()], "label": "holdout (out-of-sample, run once)"},
               **window_report(rows, counts)}
        HOLDOUT_OUT.write_text(json.dumps(rep, indent=1, default=str))
        print(f"holdout written → {HOLDOUT_OUT}")
        return 0
    rows = classify_rows(load_raw(REPO_ROOT / "data" / "desk"), earn)
    rep = {"meta": meta, "train": {"window": [TRAIN[0].isoformat(), TRAIN[1].isoformat()], "label": "in-sample (train)",
                                   **window_report(in_window(rows, *TRAIN), counts)},
           "post": {"window": [POST[0].isoformat(), None], "label": "post-period (previously seen, descriptive)",
                    **window_report(in_window(rows, POST[0], None), counts)}}
    OUT.write_text(json.dumps(rep, indent=1, default=str))
    print(f"evidence written → {OUT}")
    return 0
