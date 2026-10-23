"""EXPLORATORY: do UW gamma call/put walls act as resistance/support? (owner 2026-10-03; filter untouched)
Walls = daily `gex-levels` (source oi, stamped ~15:59 ET on day D) → known by D's close; tested on sessions D+1..D+5.
Put wall below D's close = support candidate, call wall above = resistance. Distance in ATR(14, bars ≤ D) units,
eight buckets 0–0.25 … 2.5–3 ATR (>3 dropped, e.g. AAPL put wall at 100; wrong-side walls counted, dropped).
De-dup: one event per ticker+side until the wall level changes or 5 sessions pass (walls barely move day to day).
Control: per event up to 3 placebo levels on the same ticker-day and side, distance drawn from other events' ATR
distances, snapped to the wall's own strike grid (largest of 25/10/5/2.5/1/0.5 dividing the wall), at least 0.25 ATR
from the wall, the other wall, gamma flip and magnet. Real vs placebo compared within distance bucket, weighted by real
counts per bucket. Metrics (bounce direction = up for support, down for resistance):
  touch  = low ≤ level (support) / high ≥ level (resistance) within 5 sessions
  gap    = first touch day opens already beyond the level (no daily-bar read on hold) → excluded from hold
  held   = on first touch day the close stays on the original side
  bounce1/3 = close 1/3 sessions after the touch day vs the level, in bounce direction
  follow3 = after the first close beyond the level, close 3 sessions later vs that close, in break direction
Ranges: 5-day moving-block bootstrap over event dates of the bucket-weighted real − placebo difference.
Caveat: most tickers only have GEX on days with large flow (selection). Cache-only.
→ journal/research/walls-sr.json   Usage: uv run python scripts/research/walls_sr.py"""
from __future__ import annotations

import json
import random
import statistics as st
from bisect import bisect_right
from collections import defaultdict
from datetime import date

from whaleproof.config import REPO_ROOT, load_settings
from whaleproof.core.data_layer.store import Store
from whaleproof.desk.config import HOLDOUT, TRAIN

HOLD, ATR_N, MIN_GAP_ATR, N_PLACEBO, SEED, BOOT, BLOCK = 5, 14, 0.25, 3, 11, 1000, 5
BUCKETS = [(0, 0.25), (0.25, 0.5), (0.5, 0.75), (0.75, 1), (1, 1.5), (1.5, 2), (2, 2.5), (2.5, 3)]
GRIDS = [25, 10, 5, 2.5, 1, 0.5]
INDEX = {"SPY", "QQQ", "IWM", "DIA", "SPX", "SPXW", "NDX", "RUT", "XSP", "SMH", "XLF", "XLE", "XLK", "TLT", "GLD", "SLV",
         "HYG", "EEM", "EWZ", "FXI", "KRE", "XBI", "ARKK", "UVXY", "VXX", "TQQQ", "SQQQ", "SOXL", "USO"}
PERIODS = {"train": TRAIN, "holdout": HOLDOUT, "post": (date(2026, 6, 1), date(2026, 12, 31))}
METRICS = ("touch", "held", "bounce1", "bounce3", "follow3")


def fnum(x) -> float | None:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return v if v > 0 else None


def grid_of(wall: float, price: float) -> float:
    for g in GRIDS:
        if g <= 0.03 * price and abs(wall / g - round(wall / g)) < 1e-6:
            return g
    return 0.5


def bucket(k: float) -> int | None:
    return next((i for i, (a, b) in enumerate(BUCKETS) if a <= k < b), None)


def measure(bars: list, i: int, level: float, side: int) -> dict:
    """side +1 = support (bounce up), −1 = resistance (bounce down). bars[i] = day D."""
    out: dict = {"touch": 0.0}
    fut = bars[i + 1:i + 1 + HOLD]
    for j, b in enumerate(fut):
        hit = b.low <= level if side > 0 else b.high >= level
        if not hit:
            continue
        out["touch"] = 1.0
        if (b.open < level if side > 0 else b.open > level):
            out["gap"] = 1.0
            break
        out["gap"] = 0.0
        out["held"] = float(b.close >= level if side > 0 else b.close <= level)
        t = i + 1 + j
        for h in (1, 3):
            if t + h < len(bars):
                out[f"bounce{h}"] = side * (bars[t + h].close / level - 1)
        break
    for j, b in enumerate(fut):
        if (b.close < level if side > 0 else b.close > level):
            t = i + 1 + j
            if t + 3 < len(bars):
                out["follow3"] = -side * (bars[t + 3].close / b.close - 1)
            break
    return out


def load(store: Store) -> tuple[dict, dict]:
    gex: dict = defaultdict(dict)
    for t, d, p in store.conn.execute("SELECT ticker, date, payload FROM daily_metric WHERE kind='gex'"):
        gex[t][date.fromisoformat(d)] = json.loads(p)
    bars = {t: store.get_ohlc(t, date(2024, 8, 1), date(2026, 12, 31)) for t in gex}
    return gex, bars


def atr(bars: list, i: int) -> float | None:
    if i < ATR_N:
        return None
    trs = [max(b.high, a.close) - min(b.low, a.close) for a, b in zip(bars[i - ATR_N:i], bars[i - ATR_N + 1:i + 1])]
    return st.fmean(trs) or None


def build_events(gex: dict, bars: dict) -> tuple[list, dict]:
    events, counts = [], defaultdict(int)
    for t, days in gex.items():
        bs = bars.get(t) or []
        dates = [b.date for b in bs]
        last: dict = {}
        for d in sorted(days):
            g = days[d]
            i = bisect_right(dates, d) - 1
            if i < 0 or dates[i] != d or i + HOLD >= len(bs):
                counts["no_bars"] += 1
                continue
            a, close = atr(bs, i), bs[i].close
            if not a:
                counts["no_atr"] += 1
                continue
            levels = [fnum(g.get(k)) for k in ("call_wall", "put_wall", "gamma_flip", "gamma_magnet")]
            for side, key in ((1, "put_wall"), (-1, "call_wall")):
                w = fnum(g.get(key))
                if w is None:
                    counts["missing"] += 1
                    continue
                k = (close - w) / a * side
                if k <= 0:
                    counts["wrong_side"] += 1
                    continue
                b = bucket(k)
                if b is None:
                    counts["over_3atr"] += 1
                    continue
                prev = last.get(side)
                if prev and prev[0] == w and i - prev[1] < HOLD:
                    counts["dup"] += 1
                    continue
                last[side] = (w, i)
                counts["events"] += 1
                events.append({"ticker": t, "d": d, "i": i, "side": side, "wall": w, "k": k, "b": b, "atr": a,
                               "close": close, "grid": grid_of(w, close), "avoid": [x for x in levels if x]})
    return events, dict(counts)


def placebos(ev: dict, pool: dict, rng: random.Random) -> list[float]:
    out, ks = [], pool[ev["side"]]
    for _ in range(40):
        if len(out) >= N_PLACEBO:
            break
        k = rng.choice(ks)
        g = ev["grid"]
        lvl = round((ev["close"] - ev["side"] * k * ev["atr"]) / g) * g
        kk = (ev["close"] - lvl) / ev["atr"] * ev["side"]
        if lvl <= 0 or kk <= 0 or bucket(kk) is None or lvl in out:
            continue
        if any(abs(lvl - x) < MIN_GAP_ATR * ev["atr"] for x in ev["avoid"]):
            continue
        out.append(lvl)
    return out


def rows_for(events: list, bars: dict, rng: random.Random) -> list[dict]:
    pool = {s: [e["k"] for e in events if e["side"] == s] for s in (1, -1)}
    rows = []
    for e in events:
        bs = bars[e["ticker"]]
        base = {"ticker": e["ticker"], "d": e["d"], "side": e["side"]}
        rows.append({**base, "real": 1, "b": e["b"], **measure(bs, e["i"], e["wall"], e["side"])})
        for lvl in placebos(e, pool, rng):
            kk = (e["close"] - lvl) / e["atr"] * e["side"]
            rows.append({**base, "real": 0, "b": bucket(kk), **measure(bs, e["i"], lvl, e["side"])})
    return rows


def stat(rows: list[dict], metric: str) -> dict:
    """Bucket-weighted real and placebo means (weights = real rows per bucket having the metric)."""
    cell: dict = defaultdict(lambda: [[], []])
    for r in rows:
        if r.get(metric) is not None:
            cell[r["b"]][r["real"]].append(r[metric])
    w = {b: len(v[1]) for b, v in cell.items() if v[1] and v[0]}
    tot = sum(w.values())
    if not tot:
        return {"n_real": 0}
    real = sum(w[b] * st.fmean(cell[b][1]) for b in w) / tot
    plac = sum(w[b] * st.fmean(cell[b][0]) for b in w) / tot
    return {"n_real": tot, "n_placebo": sum(len(cell[b][0]) for b in w), "real": real, "placebo": plac,
            "diff": real - plac}


def boot(rows: list[dict], metric: str, seed: int = SEED) -> tuple[float, float]:
    """Same weighting as stat(), on per-day (bucket, real) sums so each resample is cheap."""
    nb = len(BUCKETS)
    by: dict = defaultdict(lambda: [0.0] * (4 * nb))      # [sum_p, n_p, sum_r, n_r] per bucket
    for r in rows:
        v = r.get(metric)
        if v is not None:
            c = by[r["d"]]
            o = 4 * r["b"] + 2 * r["real"]
            c[o] += v
            c[o + 1] += 1
    days = sorted(by)
    if len(days) < BLOCK * 4:
        return (float("nan"), float("nan"))
    vecs = [by[d] for d in days]
    rng, n, diffs = random.Random(seed), len(days), []
    for _ in range(BOOT):
        acc = [0.0] * (4 * nb)
        k = 0
        while k < n:
            j = rng.randrange(n - BLOCK + 1)
            for vec in vecs[j:j + min(BLOCK, n - k)]:
                for q in range(4 * nb):
                    acc[q] += vec[q]
            k += BLOCK
        tot = real = plac = 0.0
        for b in range(nb):
            sp, np_, sr, nr = acc[4 * b:4 * b + 4]
            if nr and np_:
                real += sr
                plac += nr * sp / np_
                tot += nr
        if tot:
            diffs.append((real - plac) / tot)
    diffs.sort()
    return diffs[int(0.025 * len(diffs))], diffs[int(0.975 * len(diffs)) - 1]


def table(rows: list[dict], ci: bool = True) -> dict:
    out = {}
    for m in METRICS:
        s = stat(rows, m)
        if ci and s.get("n_real"):
            s["ci_low"], s["ci_high"] = boot(rows, m)
        out[m] = s
    gaps = [r["gap"] for r in rows if r["real"] and r.get("gap") is not None]
    out["gap_share_of_touches"] = st.fmean(gaps) if gaps else None
    return out


def per_ticker(rows: list[dict], metric: str, min_n: int = 10) -> dict:
    by: dict = defaultdict(list)
    for r in rows:
        by[r["ticker"]].append(r)
    diffs = [s["diff"] for t, rs in by.items() if (s := stat(rs, metric)).get("n_real", 0) >= min_n]
    return {"tickers": len(diffs), "mean_diff": st.fmean(diffs) if diffs else None,
            "share_positive": st.fmean(d > 0 for d in diffs) if diffs else None}


def main() -> None:
    store = Store(load_settings().db_path)
    gex, bars = load(store)
    events, counts = build_events(gex, bars)
    rows = rows_for(events, bars, random.Random(SEED))
    out: dict = {"label": "exploratory (post-holdout; filter untouched)", "method": __doc__, "counts": counts,
                 "buckets_atr": BUCKETS, "by_side": {}}
    for side, name in ((1, "put_wall_support"), (-1, "call_wall_resistance")):
        rs = [r for r in rows if r["side"] == side]
        o: dict = {"all": table(rs)}
        o["by_bucket"] = {f"{a}-{b}": table([r for r in rs if r["b"] == i], ci=False) for i, (a, b) in enumerate(BUCKETS)}
        o["by_period"] = {p: table([r for r in rs if a <= r["d"] <= b]) for p, (a, b) in PERIODS.items()}
        o["index_etfs"] = table([r for r in rs if r["ticker"] in INDEX])
        o["single_stocks"] = table([r for r in rs if r["ticker"] not in INDEX])
        o["equal_weight_tickers"] = {m: per_ticker(rs, m) for m in ("touch", "held", "bounce3")}
        out["by_side"][name] = o
    path = REPO_ROOT / "journal" / "research" / "walls-sr.json"
    path.write_text(json.dumps(out, indent=1, default=str))
    print(counts)
    for name, o in out["by_side"].items():
        for grp in ("all", "index_etfs", "single_stocks", *[f"period:{p}" for p in PERIODS]):
            t = o["by_period"][grp.split(":")[1]] if grp.startswith("period:") else o[grp]
            line = []
            for m in METRICS:
                s = t[m]
                if not s.get("n_real"):
                    continue
                sc = 100
                line.append(f"{m} {s['real'] * sc:.2f}/{s['placebo'] * sc:.2f} Δ{s['diff'] * sc:+.2f}"
                            f" [{s.get('ci_low', float('nan')) * sc:+.2f},{s.get('ci_high', float('nan')) * sc:+.2f}]"
                            f" n{s['n_real']}")
            print(f"{name:22} {grp:15} " + " | ".join(line))
        for b, t in o["by_bucket"].items():
            print(f"{name:22} atr {b:7} " + " | ".join(
                f"{m} {t[m]['real'] * 100:.1f}/{t[m]['placebo'] * 100:.1f} n{t[m]['n_real']}" for m in METRICS
                if t[m].get("n_real")))
        print(name, "equal-weight", o["equal_weight_tickers"])


if __name__ == "__main__":
    main()
