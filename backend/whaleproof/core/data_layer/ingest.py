from __future__ import annotations

from datetime import date, timedelta
from urllib.parse import quote

from .fetch import cached_get, rows
from .models import Bar, alert_to_row, num, parse_alert, parse_gex
from .store import Store

KIND_GEX, KIND_DP, KIND_IVR = "gex", "dp_levels", "iv_rank"
KIND_TIDE, KIND_EARN, KIND_UNUSUAL = "tide", "earnings", "unusual_opt_pct"
MARKET = "MARKET"
PAGE = 200
LIVE_TTL = {"flow": 60, "eod": 300, "series": 12 * 3600}


def _ttl(live: bool, kind: str) -> float | None:
    return LIVE_TTL[kind] if live else None


def ingest_flow_day(client, store: Store, d: date, min_premium: int = 100_000, live: bool = False) -> int:
    cursor = (d + timedelta(days=1)).isoformat()
    stored = 0
    prev_oldest_ms: int | None = None
    while True:
        params = {"limit": PAGE, "min_premium": min_premium, "newer_than": d.isoformat(), "older_than": cursor}
        batch = rows(cached_get(client, store, "/api/option-trades/flow-alerts", params, _ttl(live, "flow")))
        parsed = [(parse_alert(r), r) for r in batch]
        good = [alert_to_row(a, r) for a, r in parsed if a and a.session_date == d]
        stored += store.upsert_alerts(good)
        if len(batch) < PAGE or not any(a for a, _ in parsed):
            break
        oldest_ms = int(min(a.created_at for a, _ in parsed if a).timestamp() * 1000)
        if prev_oldest_ms is not None and oldest_ms >= prev_oldest_ms:
            break  # cursor cannot move further back — never spin (server ignored/inclusive cursor)
        prev_oldest_ms = oldest_ms
        cursor = str(oldest_ms)
    return stored


def ingest_eod(client, store: Store, ticker: str, d: date, live: bool = False) -> None:
    ttl = _ttl(live, "eod")
    g = rows(cached_get(client, store, f"/api/stock/{ticker}/gex-levels", {"date": d.isoformat(), "source": "oi"}, ttl))
    if g:
        store.put_metric(ticker, d, KIND_GEX, parse_gex(g[0]).__dict__)
    dp = rows(cached_get(client, store, f"/api/darkpool/{ticker}/price-levels", {"date": d.isoformat()}, ttl))
    levels = [[num(r.get("price")), int(num(r.get("dark_pool_volume")) or 0)] for r in dp if num(r.get("price"))]
    if levels:
        store.put_metric(ticker, d, KIND_DP, levels)


def ingest_market(client, store: Store, d: date, live: bool = False) -> None:
    rs = rows(cached_get(client, store, "/api/market/market-tide",
                         {"date": d.isoformat(), "interval_5m": True}, _ttl(live, "eod")))
    if rs:
        last = rs[-1]
        c, p = num(last.get("net_call_premium")), num(last.get("net_put_premium"))
        if c is not None and p is not None:
            store.put_metric(MARKET, d, KIND_TIDE, c - p)


def _ingest_ohlc_earnings(client, store: Store, ticker: str, ttl: float | None) -> None:
    ingest_bars(client, store, ticker, ttl)
    ingest_earnings(client, store, ticker, ttl)


def ingest_bars(client, store: Store, ticker: str, ttl: float | None) -> None:
    """Daily regular-session bars, 3y (1 call)."""
    bars = []
    for r in rows(cached_get(client, store, f"/api/stock/{ticker}/ohlc/1d",
                             {"timeframe": "3Y", "limit": 2500}, ttl)):
        if r.get("market_time") not in (None, "r"):
            continue
        o, h, l, c = (num(r.get(k)) for k in ("open", "high", "low", "close"))
        if not r.get("date") or None in (o, h, l, c):
            continue
        bars.append(Bar(date.fromisoformat(str(r["date"])[:10]), o, h, l, c,
                        float(r.get("volume") or r.get("total_volume") or 0)))
    store.put_ohlc(ticker, bars)


def ingest_earnings(client, store: Store, ticker: str, ttl: float | None) -> None:
    er = rows(cached_get(client, store, f"/api/earnings/{ticker}", {}, ttl))
    store.put_metric(ticker, "all", KIND_EARN,
                     sorted({str(r["report_date"])[:10] for r in er if r.get("report_date")}))


def ingest_prices(client, store: Store, ticker: str, today: date) -> None:
    """Daily bars + earnings dates only (2 calls) — enough for the simple-rules backtest."""
    mark = f"prices:{ticker}"
    if store.get_checkpoint(mark) == today.isoformat() or store.get_checkpoint(f"series:{ticker}") == today.isoformat():
        return
    _ingest_ohlc_earnings(client, store, ticker, _ttl(True, "series"))
    store.set_checkpoint(mark, today.isoformat())


def ingest_series(client, store: Store, ticker: str, today: date, force: bool = False) -> None:
    mark = f"series:{ticker}"
    if not force and store.get_checkpoint(mark) == today.isoformat():
        return
    ttl = 0 if force else _ttl(True, "series")
    year_ago = (today - timedelta(days=365)).isoformat()
    for params in ({"timespan": "1y"}, {"date": year_ago, "timespan": "1y"}):
        for r in rows(cached_get(client, store, f"/api/stock/{ticker}/iv-rank", params, ttl)):
            v = num(r.get("iv_rank_1y"))
            if r.get("date") and v is not None:
                store.put_metric(ticker, str(r["date"])[:10], KIND_IVR, v)  # UW scale is 0–100 (verified live)
    _ingest_ohlc_earnings(client, store, ticker, ttl)
    store.set_checkpoint(mark, today.isoformat())


def ingest_unusualness(client, store: Store, ticker: str, d: date) -> None:
    rs = rows(cached_get(client, store, f"/api/stock/{ticker}/unusualness", {}, 300))
    if rs and num(rs[0].get("opt_vol_pctile")) is not None:
        store.put_metric(ticker, str(rs[0].get("date") or d)[:10], KIND_UNUSUAL, num(rs[0]["opt_vol_pctile"]))  # 0–100


def ensure_day_bar(client, store: Store, ticker: str, d: date) -> float | None:
    """Close of session d; refetches series (bypassing cache) when a stale pull lacks d's bar."""
    ingest_series(client, store, ticker, d)
    bar = store.get_ohlc(ticker, d, d)
    if not bar:
        ingest_series(client, store, ticker, d, force=True)
        bar = store.get_ohlc(ticker, d, d)
    return bar[0].close if bar else None


# ---------- Plan 1.5: extra confluence inputs ----------
DP_BLOCK_MIN_PREMIUM = 1_000_000


def ingest_dp_blocks(client, store: Store, ticker: str, d: date, live: bool = False) -> None:
    rs = rows(cached_get(client, store, f"/api/darkpool/{ticker}",
                         {"date": d.isoformat(), "min_premium": DP_BLOCK_MIN_PREMIUM, "limit": 200},
                         _ttl(live, "eod")))
    out = {"buy": 0.0, "sell": 0.0, "neutral": 0.0, "n": 0}
    for r in rs:
        if r.get("canceled") or r.get("ext_hour_sold_codes"):
            continue  # regular-session, live prints only
        px, bid, ask, prem = (num(r.get(k)) for k in ("price", "nbbo_bid", "nbbo_ask", "premium"))
        if px is None or prem is None:
            continue
        side = "buy" if ask is not None and px >= ask else "sell" if bid is not None and px <= bid else "neutral"
        out[side] += prem
        out["n"] += 1
    store.put_metric(ticker, d, "dp_blocks", out)


def ingest_net_prem(client, store: Store, ticker: str, d: date, live: bool = False) -> None:
    rs = rows(cached_get(client, store, f"/api/stock/{ticker}/net-prem-ticks", {"date": d.isoformat()},
                         _ttl(live, "eod")))
    call = put = gross = 0.0
    for r in rs:
        c, p = num(r.get("net_call_premium")) or 0.0, num(r.get("net_put_premium")) or 0.0
        call, put, gross = call + c, put + p, gross + abs(c) + abs(p)
    if rs:
        store.put_metric(ticker, d, "net_prem", {"call": call, "put": put, "gross": gross})


def ingest_sector(client, store: Store, ticker: str) -> str | None:
    known = store.get_metric(ticker, "all", "sector")
    if known is not None:
        return known or None
    rs = rows(cached_get(client, store, f"/api/stock/{ticker}/info", {}, None))
    sector = (rs[0].get("sector") if rs else None) or ""
    store.put_metric(ticker, "all", "sector", sector)
    return sector or None


def ingest_sector_tide(client, store: Store, sector: str, d: date, live: bool = False) -> None:
    rs = rows(cached_get(client, store, f"/api/market/{quote(sector)}/sector-tide", {"date": d.isoformat()},
                         _ttl(live, "eod")))
    if rs:
        c, p = num(rs[-1].get("net_call_premium")), num(rs[-1].get("net_put_premium"))
        if c is not None and p is not None:
            store.put_metric(f"SECTOR:{sector}", d, KIND_TIDE, {"net": c - p, "gross": abs(c) + abs(p)})


def ingest_insider(client, store: Store, ticker: str, today: date) -> None:
    mark = f"insider:{ticker}"
    if store.get_checkpoint(mark) == today.isoformat():
        return
    rs = rows(cached_get(client, store, f"/api/insider/{ticker}/ticker-flow", {"limit": 500},
                         _ttl(True, "series")))
    hist = sorted([str(r["date"])[:10], num(r.get("premium")) or 0.0, num(r.get("premium_10b5")) or 0.0]
                  for r in rs if r.get("date"))
    store.put_metric(ticker, "all", "insider", hist)
    store.set_checkpoint(mark, today.isoformat())


# UW's daily unusual list has no pagination and truncates at `limit` (sorted by volume) — split each day into
# sector slices + ETFs so every slice stays under the limit; a slice that hits it marks the day incomplete.
UW_UNUSUAL_MIN_PREMIUM = 250_000
UW_UNUSUAL_LIMIT = 500
UW_SECTORS = ("Basic Materials", "Communication Services", "Consumer Cyclical", "Consumer Defensive", "Energy",
              "Financial Services", "Healthcare", "Industrials", "Real Estate", "Technology", "Utilities")
UW_UNUSUAL_PARTS = tuple({"sectors[]": s} for s in UW_SECTORS) + ({"issue_types[]": "ETF"},)


def ingest_uw_unusual(client, store: Store, d: date, live: bool = False) -> None:
    symbols, complete = set(), True
    for part in UW_UNUSUAL_PARTS:
        params = {"date": d.isoformat(), "min_premium": UW_UNUSUAL_MIN_PREMIUM, "limit": UW_UNUSUAL_LIMIT} | part
        rs = rows(cached_get(client, store, "/api/option-activity/unusual", params, _ttl(live, "eod")))
        complete &= len(rs) < UW_UNUSUAL_LIMIT
        symbols |= {r["option_symbol"] for r in rs
                    if r.get("option_symbol") and (num(r.get("premium")) or 0) >= UW_UNUSUAL_MIN_PREMIUM}
    store.put_metric("UW_UNUSUAL", d, "contracts", {"symbols": sorted(symbols), "complete": complete})


def ingest_uw_unusual_paged(client, store: Store, d: date, live: bool = False, max_pages: int = 10) -> None:
    """Same list via the unusual screener with `page` (probe 2026-09-28: reproduces the cached list, ~2 calls/day).
    Complete only if paging ended on a short page; a repeated page (server ignored `page`) or the cap → incomplete."""
    symbols, complete = set(), False
    for page in range(max_pages):
        params = {"unusual": "true", "date": d.isoformat(), "min_premium": UW_UNUSUAL_MIN_PREMIUM,
                  "limit": UW_UNUSUAL_LIMIT, "page": page}
        rs = rows(cached_get(client, store, "/api/screener/option-contracts", params, _ttl(live, "eod")))
        new = {r["option_symbol"] for r in rs
               if r.get("option_symbol") and (num(r.get("premium")) or 0) >= UW_UNUSUAL_MIN_PREMIUM}
        if rs and not (new - symbols):
            break
        symbols |= new
        if len(rs) < UW_UNUSUAL_LIMIT:
            complete = True
            break
    store.put_metric("UW_UNUSUAL", d, "contracts", {"symbols": sorted(symbols), "complete": complete})


# ---------- endpoint-review checks (skew, iv_rv, macro_event); option_sentiment parser waits for the probe ----------
def ingest_skew(client, store: Store, ticker: str, today: date) -> None:
    """25Δ risk-reversal history (3y, one call). Stored whole; checks use only dates ≤ D."""
    rs = rows(cached_get(client, store, f"/api/stock/{ticker}/historical-risk-reversal-skew",
                         {"date": today.isoformat(), "timeframe": "3Y", "delta": "25"}, _ttl(True, "series")))
    pts = sorted([str(r["date"])[:10], num(r.get("risk_reversal"))] for r in rs if r.get("date"))
    store.put_metric(ticker, "all", "rr25", [p for p in pts if p[1] is not None])


def ingest_realized_vol(client, store: Store, ticker: str, today: date) -> None:
    """IV30 by observation date + RV21 with its window-end date (RV on row `date` is forward-looking)."""
    rs = rows(cached_get(client, store, f"/api/stock/{ticker}/volatility/realized",
                         {"date": today.isoformat(), "timeframe": "3Y", "days": 21}, _ttl(True, "series")))
    out = sorted([str(r["date"])[:10], num(r.get("implied_volatility")), num(r.get("realized_volatility")),
                  str(r["unshifted_rv_date"])[:10] if r.get("unshifted_rv_date") else None]
                 for r in rs if r.get("date"))
    store.put_metric(ticker, "all", "vol_hist", out)


def ingest_econ_calendar(client, store: Store, live: bool = True) -> None:
    """Merge the economic calendar into one market-wide list (the endpoint has no date param)."""
    rs = rows(cached_get(client, store, "/api/market/economic-calendar", {}, _ttl(live, "series")))
    known = {(t, e) for t, e in (store.get_metric(MARKET, "all", "econ") or [])}
    known |= {(str(r["time"]), str(r["event"])) for r in rs if r.get("time") and r.get("event")}
    store.put_metric(MARKET, "all", "econ", [list(x) for x in sorted(known)])


def ingest_contract_oi(client, store: Store, chain: str, ttl: float | None = None) -> None:
    raw = cached_get(client, store, f"/api/option-contract/{chain}/historic", {"limit": 500}, ttl)
    rs = raw.get("chains", []) if isinstance(raw, dict) else []
    for r in rs:
        oi = num(r.get("open_interest"))
        if r.get("date") and oi is not None:
            store.put_metric(chain, str(r["date"])[:10], "oi", int(oi))
