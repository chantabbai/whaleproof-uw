"""Stock vs options on Signal Desk signals — every study behind docs/STOCK-VS-OPTIONS.md, in one reproducible run.

Cache only (no UW API calls). Reads the point-in-time history rows (scripts/desk_build_rows.py → data/desk/*.pkl), the
cached daily bars and the cached per-contract option histories (UW /api/option-contract/{id}/historic).
Run:  cd backend && uv run python scripts/research/vehicle_study.py   →  journal/research/vehicle-study.json

All studies here were run AFTER the Signal Desk filter was frozen and its holdout was used, so every number is
exploratory (it can describe, not re-tune). Windows: train 2024-10-01..2025-09-30, holdout 2025-10-01..2026-05-29,
post 2026-06-01..2026-09-22 (last date with a full 5-session outcome)."""
from __future__ import annotations

import json
import statistics as st
from datetime import date, timedelta

from whaleproof import market_calendar as mc
from whaleproof.config import REPO_ROOT, load_settings
from whaleproof.core.backtest.option_prices import history
from whaleproof.core.data_layer.store import Store
from whaleproof.desk.config import HOLDOUT, TRAIN, FilterConfig
from whaleproof.desk.history import classify_rows, earnings_map, load_raw

WINDOWS = {"train": TRAIN, "holdout": HOLDOUT, "post": (date(2026, 6, 1), date(2026, 9, 22))}
OUT = REPO_ROOT / "journal" / "research" / "vehicle-study.json"


def _f(v) -> float | None:
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return x if x > 0 else None


def summ(v: list[float]) -> dict:
    v = [x for x in v if x is not None]
    if not v:
        return {"n": 0}
    s = sorted(v)
    trimmed = s[: max(1, int(len(s) * 0.99))]
    return {"n": len(v), "median": st.median(v), "mean": st.fmean(v), "mean_ex_top1pct": st.fmean(trimmed),
            "win_rate": sum(x > 0 for x in v) / len(v), "worst": s[0], "best": s[-1]}


def window_of(d: date) -> str | None:
    return next((k for k, (a, b) in WINDOWS.items() if a <= d <= b), None)


def sessions_after(d: date, n: int) -> tuple[date, date]:
    entry = mc.next_session(d)
    x = entry
    for _ in range(n - 1):
        x = mc.next_session(x)
    return entry, x


def buy_at_open(h: dict, d: date) -> float | None:
    """Conservative option buy: the day's opening trade + half the (closing) bid/ask gap."""
    a = h.get(d.isoformat())
    if not a or not _f(a.get("open_price")):
        return None
    b, k = _f(a.get("nbbo_bid")), _f(a.get("nbbo_ask"))
    return _f(a["open_price"]) + ((k - b) / 2 if b and k and k >= b else 0.0)


def load(store: Store, longs_only: bool = True):
    raw = load_raw(REPO_ROOT / "data" / "desk", include_holdout=True)
    return raw, classify_rows(raw, earnings_map(store), FilterConfig(longs_only=longs_only))


# ---------------- 1. stock vs the whale's own option (5-session hold) ----------------
def study_stock_vs_whale_option(raw, rows) -> dict:
    out: dict = {}
    for h, (r, _) in zip(rows, raw):
        w = window_of(h.session_date)
        if not h.tier or not w:
            continue
        d = out.setdefault(w, {"stock_vs_spy": [], "option_normal": [], "option_mid": [], "option_wide": []})
        d["stock_vs_spy"].append(h.x5)
        d["option_normal"].append(r.get("opt_r5"))
        d["option_mid"].append(r.get("opt_r5_mid"))
        d["option_wide"].append(r.get("opt_r5_wide"))
    return {w: {k: summ(v) for k, v in d.items()} for w, d in out.items()}


# ---------------- 2. take-profit rules on the whale's option ----------------
def _tp(h: dict, entry: date, n: int, tp: float | None, stop: float | None, buy: float | None = None) -> float | None:
    buy = buy or buy_at_open(h, entry)
    if not buy:
        return None
    d, last = entry, None
    for i in range(n):
        if i:
            d = mc.next_session(d)
        r = h.get(d.isoformat())
        if not r:
            continue
        hi, bid = _f(r.get("high_price")), _f(r.get("nbbo_bid"))
        if tp and i > 0 and hi and hi >= buy * (1 + tp):
            return tp                                    # resting limit sell filled at the target (optimistic-ish)
        if bid:
            last = bid / buy - 1
            if stop and last <= -stop:
                return last
    return last


def study_take_profit(store, raw, rows) -> dict:
    res: dict = {}
    for h, (_, x) in zip(rows, raw):
        w = window_of(h.session_date)
        hh = history(store, x.get("option_chain") or "")
        if not h.tier or not w or not hh:
            continue
        entry = mc.next_session(h.session_date)
        for n in (5, 10):
            for tp in (None, 0.2, 0.3, 0.5, 1.0):
                for stop in (None, 0.5):
                    k = f"hold<={n} tp={'none' if tp is None else f'+{int(tp * 100)}%'} stop={'none' if stop is None else '-50%'}"
                    res.setdefault(k, {}).setdefault(w, []).append(_tp(hh, entry, n, tp, stop))
    return {k: {w: summ(v) for w, v in d.items()} for k, d in res.items()}


# ---------------- 3. the whale's own trade held to expiry ----------------
def study_whale_to_expiry(store, raw, rows) -> dict:
    res: dict = {"signals": [], "other_clean_call_buys": [], "clean_put_buys": []}
    for h, (_, x) in zip(rows, raw):
        if h.stage == "gate" or not x.get("expiry") or not x.get("strike") or not x.get("total_size"):
            continue
        exp = date.fromisoformat(str(x["expiry"])[:10])
        if exp > date(2026, 9, 29):
            continue
        paid = h.premium / float(x["total_size"]) / 100
        bars = store.get_ohlc(h.ticker, exp - timedelta(days=6), exp)
        if paid <= 0 or not bars:
            continue
        s, k = bars[-1].close, float(x["strike"])
        val = max(s - k, 0) if x.get("type") == "call" else max(k - s, 0)
        key = "signals" if h.tier else "other_clean_call_buys" if x.get("type") == "call" else "clean_put_buys"
        res[key].append(val / paid - 1)
    return {k: summ(v) | {"expired_worthless": sum(x <= -0.999 for x in v) / len(v)} for k, v in res.items() if v}


# ---------------- 4. entry timing: next open vs at the alert vs same-day close ----------------
def study_entry_timing(store, raw, rows) -> dict:
    res: dict = {}

    def add(k, w, v):
        if v is not None:
            res.setdefault(k, {}).setdefault(w, []).append(v)
    for h, (_, x) in zip(rows, raw):
        w = window_of(h.session_date)
        if not h.tier or not w:
            continue
        d = h.session_date
        e, xd = sessions_after(d, 5)
        bars = {b.date: b for b in store.get_ohlc(h.ticker, d, xd)}
        if d not in bars or e not in bars or xd not in bars:
            continue
        s1, sa = bars[xd].close, _f(x.get("underlying_price"))
        add("stock A next open", w, s1 / bars[e].open - 1 - 0.001)
        add("stock B at alert price", w, s1 / sa - 1 - 0.001 if sa else None)
        add("stock C same-day close", w, s1 / bars[d].close - 1 - 0.001)
        hh = history(store, x.get("option_chain") or "") or {}
        dD, dX = hh.get(d.isoformat()), hh.get(xd.isoformat())
        if not dD or not dX or not _f(dX.get("nbbo_bid")):
            continue
        bid, ask = _f(dD.get("nbbo_bid")), _f(dD.get("nbbo_ask"))
        half = ((ask - bid) / ((ask + bid) / 2)) / 2 if bid and ask and ask >= bid else 0.05
        whale = h.premium / float(x["total_size"]) / 100 if x.get("total_size") else None
        entries = {"A next open": buy_at_open(hh, e), "B at alert (whale fill + half spread)": whale * (1 + half) if whale else None,
                   "C same-day close (ask)": ask}
        for name, buy in entries.items():
            if buy:
                add(f"option {name} | hold 5", w, _f(dX["nbbo_bid"]) / buy - 1)
                add(f"option {name} | TP +20%", w, _tp(hh, e, 5, 0.2, None, buy))
    return {k: {w: summ(v) for w, v in d.items()} for k, d in res.items()}


# ---------------- 5. put buys by subgroup (why the filter is bullish-only) ----------------
def study_puts(raw_all, rows_all) -> dict:
    groups = {
        "all clean put buys": lambda h: h.stage != "gate",
        "whale-size put (≥$1M, >5% OTM)": lambda h: h.tier == "whale",
        "far-OTM put, fair price": lambda h: h.tier == "far_otm",
        "put ≥ $1M any strike": lambda h: h.stage != "gate" and h.premium >= 1e6,
        "put 0–5% OTM": lambda h: h.stage != "gate" and h.otm_pct <= 0.05,
    }
    out: dict = {}
    for h in rows_all:
        w = window_of(h.session_date)
        if h.direction >= 0 or not w:
            continue
        for g, f in groups.items():
            if f(h):
                out.setdefault(g, {}).setdefault(w, []).append(h.x5)
    return {g: {w: summ(v) for w, v in d.items()} for g, d in out.items()}


# ---------------- 6. next-morning OI confirmation and repeat buying (train) ----------------
def study_oi_and_repeat(raw, rows) -> dict:
    oi, rep = {}, {}
    for h, (r, _) in zip(rows, raw):
        if not (TRAIN[0] <= h.session_date <= TRAIN[1]) or h.x5 is None:
            continue
        if h.tier:
            ratio = r.get("oi_ratio")
            k = "no OI data" if ratio is None else "confirmed (ratio ≥ 0.5)" if ratio >= 0.5 else "not confirmed"
            oi.setdefault(k, []).append(h.x5)
        if r["label"] == "PURE" and h.direction > 0:
            rep.setdefault(r["setup"], []).append(h.x5)
    return {"oi_confirmation_signals_train": {k: summ(v) for k, v in oi.items()},
            "setups_clean_longs_train": {k: summ(v) for k, v in rep.items()}}


def main() -> None:
    store = Store(load_settings().db_path)
    raw, rows = load(store)
    raw_all, rows_all = load(store, longs_only=False)
    rep = {"meta": {"generated": date.today().isoformat(), "windows": {k: [str(a), str(b)] for k, (a, b) in WINDOWS.items()},
                    "note": "Exploratory (after the frozen filter's one-time holdout). Stock x5 = 5-session return in the "
                            "signal direction minus SPY, entry next open, 0.10% cost. Option fills conservative unless "
                            "stated: buy = opening trade + half the closing gap, sell = closing bid."},
           "stock_vs_whale_option": study_stock_vs_whale_option(raw, rows),
           "take_profit_on_whale_option": study_take_profit(store, raw, rows),
           "whale_trade_to_expiry": study_whale_to_expiry(store, raw, rows),
           "entry_timing": study_entry_timing(store, raw, rows),
           "put_buys": study_puts(raw_all, rows_all),
           **study_oi_and_repeat(raw, rows)}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(rep, indent=1, default=str))
    print(f"written → {OUT}")


if __name__ == "__main__":
    main()
