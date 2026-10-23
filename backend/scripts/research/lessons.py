"""EXPLORATORY: lessons from the record — would a fixed rule have done better than the signal rule? (owner 2026-10-07)

Candidates live in whaleproof/desk/lessons.py (CANDIDATES) and were locked with `--freeze` BEFORE this backtest ran
(journal/lessons-frozen.json: hash, UTC time, git SHA). All of them are tracked forward; none dropped after the look.
Per finished signal: the signal rule (buy next open, sell 5th-session close, −0.10%) vs the same signal under each rule,
from cached daily bars. Skipped trades count as $0. Levels fill at the level (optimistic) or at a gapped open.
History periods are hindsight (rules picked after seeing these trades); the fair test is forward, on signals decided
after the lock. Verdict = how many of the 4 history periods the rule helped (total $ on $1,000 per trade); no CI.
Aggregates only in the output (per-trade prices are UW-derived, Rule 11). Cache only.
→ journal/research/lessons.json
Usage: uv run python scripts/research/lessons.py --freeze          (once; refuses to overwrite)
       uv run python scripts/research/lessons.py [tracker.json]    (backtest; rows from the running desk API by default)"""
from __future__ import annotations

import json
import subprocess
import sys
import urllib.request
from collections import defaultdict
from datetime import UTC, date, datetime, timedelta

from whaleproof.config import REPO_ROOT, load_settings
from whaleproof.core.data_layer.store import Store
from whaleproof.desk import lessons as L
from whaleproof.desk.tracker import LIVE_PERIOD

FROZEN = REPO_ROOT / "journal" / "lessons-frozen.json"
OUT = REPO_ROOT / "journal" / "research" / "lessons.json"
MIN_VOTE = 30                     # a period needs this many compared trades to vote


def tracker_rows(path: str | None) -> list[dict]:
    if path:
        return json.loads(open(path).read())["rows"]
    with urllib.request.urlopen("http://127.0.0.1:8100/api/desk/tracker", timeout=180) as r:
        return json.loads(r.read())["rows"]


def main() -> None:
    if "--freeze" in sys.argv:
        sha = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, cwd=REPO_ROOT).stdout.strip()
        f = L.freeze(FROZEN, datetime.now(UTC), sha)
        print(f"frozen {f['hash']} at {f['frozen_at']} (git {sha[:8]}) → {FROZEN}")
        return
    frozen = json.loads(FROZEN.read_text())
    if frozen["hash"] != L.candidates_hash():
        sys.exit("candidates changed after the freeze — add a new versioned freeze file instead")
    rows = [r for r in tracker_rows(next((a for a in sys.argv[1:] if a.endswith(".json")), None))
            if r["stock"]["status"] == "closed" and r["stock"]["ret"] is not None]
    store = Store(load_settings().db_path)
    by: dict = defaultdict(lambda: defaultdict(list))                # rule → period → pairs
    for r in rows:
        d = date.fromisoformat(r["session_date"])
        bars = store.get_ohlc(r["ticker"], d - timedelta(days=7), d + timedelta(days=20))
        base = L.apply(None, bars, d, r["direction"])
        if base is None:
            continue
        period = "Forward (after the lock)" if L.is_forward(d, frozen) else r["period"]
        for k in L.CANDIDATES:
            x = L.apply(k, bars, d, r["direction"])
            if x is not None:
                by[k][period].append((base["net"], x["net"], x["taken"]))
    out = {"frozen": {k: frozen[k] for k in ("hash", "frozen_at", "git_sha")}, "label": "exploratory",
           "built_at": datetime.now(UTC).isoformat(), "rules": {}}
    for k, c in L.CANDIDATES.items():
        periods = {p: L.summarize(v) for p, v in by[k].items()}
        votes = [s["diff_1k"] > 0 for p, s in periods.items()
                 if p not in (LIVE_PERIOD, "Forward (after the lock)") and s["trades"] >= MIN_VOTE]
        allp = L.summarize([x for p, v in by[k].items() if p != "Forward (after the lock)" for x in v])
        out["rules"][k] = {"text": c["text"], "params": c, "history": allp, "periods": periods,
                           "helped_periods": sum(votes), "voting_periods": len(votes)}
        print(f"{k:18} helped {sum(votes)}/{len(votes)} periods · all history {allp['trades']} trades: "
              f"${allp['base_1k']:+,.0f} → ${allp['rule_1k']:+,.0f} ({allp['diff_1k']:+,.0f})")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, indent=1) + "\n")
    print("→", OUT)


if __name__ == "__main__":
    main()
