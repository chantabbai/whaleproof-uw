"""EXPLORATORY: did signals whose whale contract's open interest did NOT grow the next morning do worse?
(owner 2026-10-05, after MXL 10-02: 1,496 calls bought, OI 656 → 560 overnight; filter untouched, post-holdout look.)
Groups use the dashboard's own rule (desk/oi.py, CONFIRM_RATIO = 0.5, fixed before this look):
  confirmed   = OI(next session) − OI(session) ≥ 0.5 × whale size
  weak        = grew, but by less than half the size
  fell        = OI went down overnight (someone closed more than was opened)
  unknown     = no OI on one of the two days in the cache
UW's OI for date X = contracts open after X−1's session, so OI(next session) is known ~06:45 ET before the entry open.
Outcome = tracker stock trade (buy next open, sell 5th-session close, −0.10% costs) vs SPY same days; closed rows only.
Ranges: 1,000× bootstrap resampling signal days (all signals of a day together) of the group mean vs SPY and of
(unconfirmed − confirmed). Cache only (reads tracker rows from the running desk API, OI + alert size from SQLite).
→ journal/research/oi-confirm.json   Usage: uv run python scripts/research/oi_confirm.py [tracker.json]"""
from __future__ import annotations

import json
import random
import statistics as st
import sys
import urllib.request
from collections import defaultdict

from whaleproof import market_calendar as mc
from whaleproof.config import REPO_ROOT, load_settings
from whaleproof.core.data_layer.store import Store
from whaleproof.desk.oi import CONFIRM_RATIO
from datetime import date

SEED, BOOT = 7, 1000
GROUPS = ("confirmed", "weak", "fell", "unknown")


def tracker_rows(path: str | None) -> list[dict]:
    if path:
        return json.loads(open(path).read())["rows"]
    with urllib.request.urlopen("http://127.0.0.1:8100/api/desk/tracker", timeout=120) as r:
        return json.loads(r.read())["rows"]


def group_of(store: Store, row: dict) -> tuple[str, float | None]:
    c = row.get("contract")
    if not c:
        return "unknown", None
    a = store.conn.execute("SELECT payload FROM flow_alerts WHERE id=?", (row["id"],)).fetchone()
    size = json.loads(a[0]).get("total_size") if a else None
    d = row["session_date"]
    nxt = mc.next_session(date.fromisoformat(d)).isoformat()
    oi = dict(store.conn.execute("SELECT date, payload FROM daily_metric WHERE ticker=? AND kind='oi' AND date IN (?,?)",
                                 (c, d, nxt)).fetchall())
    if d not in oi or nxt not in oi or not size:
        return "unknown", None
    ratio = (float(oi[nxt]) - float(oi[d])) / float(size)
    if ratio >= CONFIRM_RATIO:
        return "confirmed", ratio
    return ("fell" if ratio < 0 else "weak"), ratio


def boot(by_day: dict[str, list[float]], rng: random.Random) -> tuple[float, float] | None:
    days = list(by_day)
    if len(days) < 5:
        return None
    means = []
    for _ in range(BOOT):
        xs = [x for d in (rng.choice(days) for _ in days) for x in by_day[d]]
        means.append(st.mean(xs))
    means.sort()
    return means[int(0.025 * BOOT)], means[int(0.975 * BOOT) - 1]


def diff_boot(a: dict[str, list[float]], b: dict[str, list[float]], rng: random.Random) -> tuple[float, float] | None:
    days = sorted(set(a) | set(b))
    if len(a) < 5 or len(b) < 5:
        return None
    out = []
    for _ in range(BOOT):
        pick = [rng.choice(days) for _ in days]
        xa = [x for d in pick for x in a.get(d, [])]
        xb = [x for d in pick for x in b.get(d, [])]
        if xa and xb:
            out.append(st.mean(xa) - st.mean(xb))
    out.sort()
    n = len(out)
    return out[int(0.025 * n)], out[int(0.975 * n) - 1]


def summ(xs: list[float]) -> dict:
    return {"trades": len(xs), "mean_vs_spy": round(st.mean(xs), 5) if xs else None,
            "beat_spy": round(sum(x > 0 for x in xs) / len(xs), 3) if xs else None}


def main() -> None:
    store = Store(load_settings().db_path)
    rows = tracker_rows(sys.argv[1] if len(sys.argv) > 1 else None)
    rng = random.Random(SEED)
    data: dict[str, dict[str, dict[str, list[float]]]] = defaultdict(lambda: {g: defaultdict(list) for g in GROUPS})
    counts: dict[str, dict[str, int]] = defaultdict(lambda: {g: 0 for g in GROUPS})
    for r in rows:
        g, _ = group_of(store, r)
        for p in (r["period"], "All periods"):
            counts[p][g] += 1
        s = r.get("stock") or {}
        if s.get("status") != "closed" or s.get("vs_spy") is None:
            continue
        for p in (r["period"], "All periods"):
            data[p][g][r["session_date"]].append(s["vs_spy"])
    out = {"note": __doc__.split("\n")[0], "confirm_ratio": CONFIRM_RATIO, "periods": {}}
    for p, gs in data.items():
        flat = {g: [x for v in gs[g].values() for x in v] for g in GROUPS}
        unconf = defaultdict(list)
        for g in ("weak", "fell"):
            for d, v in gs[g].items():
                unconf[d] += v
        out["periods"][p] = {
            "signals": counts[p],
            "groups": {g: summ(flat[g]) | {"range": boot(gs[g], rng)} for g in GROUPS},
            "unconfirmed": summ([x for v in unconf.values() for x in v]) | {"range": boot(unconf, rng)},
            "unconfirmed_minus_confirmed": diff_boot(unconf, gs["confirmed"], rng),
            "fell_minus_confirmed": diff_boot(gs["fell"], gs["confirmed"], rng),
        }
    path = REPO_ROOT / "journal/research/oi-confirm.json"
    path.write_text(json.dumps(out, indent=1, default=lambda x: round(x, 5)) + "\n")
    for p, v in out["periods"].items():
        print(f"\n{p}  signals {v['signals']}")
        for g in (*GROUPS, "unconfirmed"):
            s = v["groups"].get(g) or v["unconfirmed"]
            rg = s["range"]
            line = f"vs SPY {s['mean_vs_spy']:+.2%} beat {s['beat_spy']:.0%}" if s["trades"] else "—"
            if rg:
                line += f"  range {rg[0]:+.2%}…{rg[1]:+.2%}"
            print(f"  {g:12} {s['trades']:5}  {line}")
        for k in ("unconfirmed_minus_confirmed", "fell_minus_confirmed"):
            rg = v[k]
            print(f"  {k}: " + (f"{rg[0]:+.2%}…{rg[1]:+.2%}" if rg else "too few days"))


if __name__ == "__main__":
    main()
