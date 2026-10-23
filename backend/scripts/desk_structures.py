"""Option structures on every historical signal (cache only, no API calls) → journal/desk-structures.json.
Calibration: the modelled long call on the whale's contract is compared with its REAL result (cached UW history)."""
from __future__ import annotations

import json
import statistics as st
from datetime import date, timedelta

from whaleproof import market_calendar as mc
from whaleproof.config import REPO_ROOT, load_settings
from whaleproof.core.backtest.option_prices import history
from whaleproof.core.data_layer.models import num
from whaleproof.core.data_layer.store import Store
from whaleproof.desk.config import HOLD_SESSIONS, HOLDOUT, POST, TRAIN
from whaleproof.desk.history import classify_rows, earnings_map, load_raw
from whaleproof.desk.structures import (LABEL, OWN_CALLS, OWN_LABEL, STRUCTURES, evaluate, evaluate_real, own_calls,
                                        own_expiry, structures_for)

REAL = ("call_spread", "short_put", "put_spread", *OWN_CALLS)     # measured on real leg prices where every leg has history

WINDOWS = {"train": TRAIN, "holdout": HOLDOUT, "post": (POST[0], date.today())}


def occ(ticker: str, expiry: date, kind: str, strike: float) -> str:
    return f"{ticker}{expiry:%y%m%d}{kind}{round(strike * 1000):08d}"


def _iv(h: dict | None, d: date, fallback: float | None) -> float | None:
    r = (h or {}).get(d.isoformat()) or {}
    return num(r.get("implied_volatility")) or fallback


def main() -> None:
    store = Store(load_settings().db_path)
    raw = load_raw(REPO_ROOT / "data" / "desk", include_holdout=True)
    rows = classify_rows(raw, earnings_map(store))
    out: dict[str, dict] = {w: {s: [] for s in (*STRUCTURES, *OWN_CALLS, *(f"real_{x}" for x in REAL), "stock",
                                                 "real_long_call")}
                            for w in WINDOWS}
    skipped = 0
    for h, (r, x) in zip(rows, raw):
        if not h.tier:
            continue
        w = next((k for k, (a, b) in WINDOWS.items() if a <= h.session_date <= b), None)
        entry = mc.next_session(h.session_date)
        exit_ = entry
        for _ in range(HOLD_SESSIONS - 1):
            exit_ = mc.next_session(exit_)
        bars = {b.date: b for b in store.get_ohlc(h.ticker, entry, exit_ + timedelta(days=1))}
        if w is None or entry not in bars or exit_ not in bars or not x.get("expiry") or not x.get("strike"):
            skipped += 1
            continue
        s0, s1 = bars[entry].open, bars[exit_].close
        hist = history(store, x.get("option_chain") or "")
        iv0 = _iv(hist, entry, num(x.get("iv")))
        iv1 = _iv(hist, exit_, iv0)
        if not iv0:
            skipped += 1
            continue
        expiry = date.fromisoformat(str(x["expiry"])[:10])
        plans = [(n, lg, expiry) for n, lg in structures_for(s0, float(x["strike"])).items()]
        plans += [(n, lg, own_expiry(entry)) for n, lg in own_calls(s0).items()]
        for name, legs, expiry in plans:
            res = evaluate(legs, s0, s1, entry, exit_, expiry, iv0, iv1)
            if res["ret"] is not None:
                out[w][name].append(res["ret"])
            if name in REAL:
                real = evaluate_real(legs, [occ(h.ticker, expiry, g.kind, g.strike) for g in legs],
                                     lambda sym: history(store, sym), entry, exit_)
                if real and real["ret"] is not None:
                    out[w][f"real_{name}"].append(real["ret"])
        out[w]["stock"].append(s1 / s0 - 1 - 0.001)
        if r.get("opt_r5") is not None:
            out[w]["real_long_call"].append(r["opt_r5"])

    def summ(v: list[float]) -> dict:
        return {"n": len(v), "mean": st.fmean(v), "median": st.median(v), "win_rate": sum(x > 0 for x in v) / len(v),
                "worst": min(v), "best": max(v)} if v else {"n": 0}
    rep = {"meta": {"note": "Model estimate: Black-Scholes with the whale contract's real IV (entry/exit), real stock "
                    "prices, per-leg bid/ask cost both sides; flat smile (real OTM puts carry more premium AND more "
                    "crash risk). Returns on capital at risk: debit / max loss / cash-secured strike. Stock = raw "
                    "return (not vs SPY), 0.10% cost. Cache only.", "skipped": skipped, "labels": LABEL | OWN_LABEL,
                    "generated": date.today().isoformat()},
           "windows": {w: {k: summ(v) for k, v in d.items()} for w, d in out.items()}}
    (REPO_ROOT / "journal" / "desk-structures.json").write_text(json.dumps(rep, indent=1))
    for w, d in rep["windows"].items():
        print(w)
        for k, s in d.items():
            if s["n"]:
                print(f"  {k:15s} n={s['n']:4d} mean {s['mean']*100:+6.1f}% median {s['median']*100:+6.1f}% "
                      f"win {s['win_rate']*100:3.0f}% worst {s['worst']*100:+6.0f}%")
    print("skipped", skipped)


if __name__ == "__main__":
    main()
