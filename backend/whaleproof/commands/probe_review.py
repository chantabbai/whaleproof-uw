"""Endpoint-review probe (owner-approved ~45 calls): does each Tier A/B endpoint have point-in-time history back to
2024-10, what shape does it return, and does paging the unusual screener reproduce the cached unusual list?
Writes metadata only (status, row counts, date range, field names) — never raw rows (UW data is not redistributed)."""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta

from whaleproof import market_calendar as mc
from whaleproof.config import REPO_ROOT, load_settings
from whaleproof.core.data_layer.client import UWClient, UWError
from whaleproof.core.data_layer.fetch import rows
from whaleproof.core.data_layer.ingest import UW_UNUSUAL_LIMIT, UW_UNUSUAL_MIN_PREMIUM, UW_UNUSUAL_PARTS
from whaleproof.core.data_layer.models import num
from whaleproof.core.data_layer.store import Store

T = "NVDA"
HIST = date(2024, 10, 25)
DATE_KEYS = ("date", "time", "created_at", "report_date", "published_at", "market_date", "timestamp")

# (name, path, params(when) — when=None means "today", and whether to also ask for HIST)
REVIEW_PROBES = [
    ("rr_skew", f"/api/stock/{T}/historical-risk-reversal-skew",
     lambda w, t: {"date": t.isoformat(), "timeframe": "3Y", "delta": "25"}, False),
    ("realized_vol", f"/api/stock/{T}/volatility/realized",
     lambda w, t: {"date": t.isoformat(), "timeframe": "3Y", "days": 21}, False),
    ("vrp", f"/api/stock/{T}/volatility/variance-risk-premium", lambda w, t: {"date": t.isoformat()}, False),
    ("vol_stats", f"/api/stock/{T}/volatility/stats", lambda w, t: {"date": (w or t).isoformat()}, True),
    ("option_sentiment", f"/api/stock/{T}/volatility/option-sentiment", lambda w, t: {"date": (w or t).isoformat()}, True),
    ("option_sentiment_top", "/api/volatility/option-sentiment/top",
     lambda w, t: {"date": (w or t).isoformat(), "limit": 5}, True),
    ("options_pulse", f"/api/stock/{T}/options-pulse", lambda w, t: {"date": (w or t).isoformat()}, True),
    ("options_pulse_top", "/api/options-pulse/top", lambda w, t: {"date": (w or t).isoformat(), "limit": 5}, True),
    ("econ_calendar", "/api/market/economic-calendar", lambda w, t: {}, False),
    ("analysts", "/api/screener/analysts", lambda w, t: {"ticker": T, "limit": 5, "older_than": "2024-11-01"}, False),
    ("short_interest", f"/api/shorts/{T}/interest-float/v2", lambda w, t: {}, False),
    ("short_volume", f"/api/shorts/{T}/volume-and-ratio", lambda w, t: {}, False),
    ("ftds", f"/api/shorts/{T}/ftds", lambda w, t: {}, False),
    ("top_net_impact", "/api/market/top-net-impact", lambda w, t: {"date": (w or t).isoformat(), "limit": 5}, True),
    ("etf_flow", "/api/etfs/XLK/in-outflow", lambda w, t: {"start_date": "2024-10-01", "end_date": t.isoformat()}, False),
    ("greek_exposure", f"/api/stock/{T}/greek-exposure", lambda w, t: {"date": t.isoformat(), "timeframe": "3Y"}, False),
]


def _rows(payload) -> list[dict]:
    if isinstance(payload, dict) and "data" not in payload:
        for k in ("si", "history", "chains", "results"):
            if isinstance(payload.get(k), list):
                return payload[k]
    return [r for r in rows(payload) if isinstance(r, dict)]


def _dates(rs: list[dict]) -> list[str]:
    out = []
    for r in rs:
        for k in DATE_KEYS:
            if r.get(k):
                out.append(str(r[k])[:10])
                break
    return sorted(out)


def run_review(client, today: date) -> list[dict]:
    out = []
    for name, path, params, hist in REVIEW_PROBES:
        for w in [None] + ([HIST] if hist else []):
            res = {"name": name, "when": w.isoformat() if w else "today", "status": 200, "rows": 0, "oldest": "",
                   "newest": "", "keys": [], "stale": False, "error": ""}
            try:
                rs = _rows(client.get(path, params(w, today)))
                ds = _dates(rs)
                res.update(rows=len(rs), oldest=ds[0] if ds else "", newest=ds[-1] if ds else "",
                           keys=sorted(rs[0].keys())[:25] if rs else [])
                if w and ds:   # screeners fall back to the latest date — a hit must be dated near the asked day
                    res["stale"] = not any(d <= (w + timedelta(days=3)).isoformat() for d in ds)
            except UWError as e:
                res.update(status="error", error=str(e)[:160])
            out.append(res)
    return out


def _symbols(rs: list[dict]) -> set[str]:
    return {r["option_symbol"] for r in rs
            if r.get("option_symbol") and (num(r.get("premium")) or 0) >= UW_UNUSUAL_MIN_PREMIUM}


def coverage_check(client, d: date, cached: set[str], page_size: int = UW_UNUSUAL_LIMIT, max_pages: int = 6) -> dict:
    """Pre-registration Amendment 1: which fetch reproduces the (uncapped) cached unusual list for day d?"""
    paged, pages = set(), 0
    for page in range(max_pages):
        rs = _rows(client.get("/api/screener/option-contracts",
                              {"unusual": "true", "date": d.isoformat(), "min_premium": UW_UNUSUAL_MIN_PREMIUM,
                               "limit": page_size, "page": page}))
        pages += 1
        if not rs or not (_symbols(rs) - paged):   # empty, or server ignored `page` and repeated itself
            break
        paged |= _symbols(rs)
    sliced = set()
    for part in UW_UNUSUAL_PARTS:
        sliced |= _symbols(_rows(client.get("/api/option-activity/unusual",
                                            {"date": d.isoformat(), "min_premium": UW_UNUSUAL_MIN_PREMIUM,
                                             "limit": UW_UNUSUAL_LIMIT} | part)))
    return {"day": d.isoformat(), "cached_symbols": len(cached), "pages": pages,
            "paging_symbols": len(paged), "paging_matches_cached": paged == cached,
            "paging_missing": len(cached - paged), "paging_extra": len(paged - cached),
            "slices_symbols": len(sliced), "slices_matches_cached": sliced == cached,
            "slices_missing": len(cached - sliced), "slices_extra": len(sliced - cached)}


def render_review(res: list[dict], cov: dict | None) -> str:
    lines = ["# Endpoint-review probe (metadata only)", "",
             f"Run {datetime.now(mc.NY):%Y-%m-%d %H:%M} ET · ticker {T} · history target {HIST}. "
             "`stale` = asked for a past date but got only newer rows (screener fallback → no history).", "",
             "| endpoint | when | status | rows | oldest | newest | stale | fields / error |", "|---|---|---|---|---|---|---|---|"]
    for r in res:
        info = r["error"] or ", ".join(r["keys"])
        lines.append(f"| {r['name']} | {r['when']} | {r['status']} | {r['rows']} | {r['oldest']} | {r['newest']} | "
                     f"{'yes' if r['stale'] else ''} | {info} |")
    if cov:
        lines += ["", "## uw_unusual coverage (pre-registration Amendment 1)", "", "```", json.dumps(cov, indent=2), "```"]
    return "\n".join(lines) + "\n"


def _uncapped_cached_day(store: Store) -> tuple[date, set[str]] | None:
    best = None
    for key, payload in store.conn.execute(
            "SELECT key, payload FROM raw_cache WHERE endpoint='/api/option-activity/unusual'"):
        rs = _rows(json.loads(payload))
        params = json.loads(key.split("?", 1)[1]) if "?" in key else {}
        if 0 < len(rs) < UW_UNUSUAL_LIMIT and set(params) == {"date", "limit", "min_premium"}:
            d = date.fromisoformat(params["date"])
            if best is None or d > best[0]:
                best = (d, _symbols(rs))
    return best


def main(argv: list[str]) -> int:
    s = load_settings()
    client, store = UWClient(s.uw_api_key, s.live_request_cap), Store(s.db_path)
    today = datetime.now(mc.NY).date()
    res = run_review(client, today)
    day = _uncapped_cached_day(store)
    cov = coverage_check(client, *day) if day else None
    out = REPO_ROOT / "docs" / "endpoint-review-probe.md"
    out.write_text(render_review(res, cov))
    print(f"{len(res)} probes + coverage {'on ' + cov['day'] if cov else 'skipped'} → {out} "
          f"· requests today {client.usage.daily_count}")
    return 0
