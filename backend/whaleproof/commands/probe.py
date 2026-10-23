from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Callable

from whaleproof import market_calendar as mc
from whaleproof.config import REPO_ROOT, load_settings
from whaleproof.core.data_layer.client import UWClient, UWError
from whaleproof.core.data_layer.fetch import rows

T = "NVDA"


@dataclass(frozen=True)
class Probe:
    name: str
    path: str
    params: Callable[[date | None], dict]   # None → "today" form


def _date(d):
    return {"date": d.isoformat()} if d else {}


PROBES = [
    Probe("flow_alerts", "/api/option-trades/flow-alerts",
          lambda d: {"limit": 5, "min_premium": 250000,
                     **({"newer_than": d.isoformat(), "older_than": (d + timedelta(days=1)).isoformat()} if d else {})}),
    Probe("stock_flow_alerts", f"/api/stock/{T}/flow-alerts", lambda d: {"limit": 5}),
    Probe("option_activity_unusual", "/api/option-activity/unusual", lambda d: {"limit": 5, **_date(d)}),
    Probe("gex_levels", f"/api/stock/{T}/gex-levels", lambda d: {"source": "oi", **_date(d)}),
    Probe("spot_exposures_strike", f"/api/stock/{T}/spot-exposures/strike", _date),
    Probe("dp_price_levels", f"/api/darkpool/{T}/price-levels", _date),
    Probe("darkpool_ticker", f"/api/darkpool/{T}", _date),
    Probe("iv_rank", f"/api/stock/{T}/iv-rank", lambda d: {"timespan": "2y"} if d else {}),
    Probe("vol_anomaly", f"/api/stock/{T}/volatility/anomaly", _date),
    Probe("vrp", f"/api/stock/{T}/volatility/variance-risk-premium", lambda d: {}),
    Probe("unusualness", f"/api/stock/{T}/unusualness", lambda d: {}),
    Probe("option_stance", f"/api/stock/{T}/option-stance", lambda d: {}),
    Probe("ohlc_1d", f"/api/stock/{T}/ohlc/1d", lambda d: {"timeframe": "2Y", "limit": 600}),
    Probe("market_tide", "/api/market/market-tide", lambda d: {"interval_5m": True, **_date(d)}),
    Probe("earnings_hist", f"/api/earnings/{T}", lambda d: {}),
    Probe("stock_info", f"/api/stock/{T}/info", lambda d: {}),
    Probe("net_prem_ticks", f"/api/stock/{T}/net-prem-ticks", _date),
    Probe("multi_leg", "/api/option-trades/multi-leg", lambda d: {"limit": 5}),
    Probe("daily_report", "/api/market/daily-report", _date),
    Probe("option_contracts", f"/api/stock/{T}/option-contracts", lambda d: {"limit": 5}),
    Probe("insider_ticker", f"/api/insider/{T}", lambda d: {}),
    Probe("congress_unusual", "/api/congress/unusual-trades", lambda d: {"limit": 5}),
    Probe("full_tape", "/api/option-trades/full-tape/2025-09-25", lambda d: {}),
]
HIST_PROBES = {"flow_alerts", "option_activity_unusual", "gex_levels", "spot_exposures_strike",
               "dp_price_levels", "darkpool_ticker", "iv_rank", "vol_anomaly", "market_tide",
               "net_prem_ticks", "daily_report"}
DATE_KEYS = ("date", "created_at", "executed_at", "start_time", "timestamp", "report_date")


def _dates(rs: list[dict]) -> list[str]:
    out = []
    for r in rs:
        if not isinstance(r, dict):
            continue
        for k in DATE_KEYS:
            if r.get(k):
                out.append(str(r[k])[:10])
                break
    return sorted(out)


def run_probe(client, today: date) -> list[dict]:
    targets = [mc.previous_session(today - timedelta(days=n)) for n in (182, 365, 700)]
    results = []
    for p in PROBES:
        whens: list[date | None] = [None] + (targets if p.name in HIST_PROBES else [])
        for w in whens:
            res = {"name": p.name, "when": w.isoformat() if w else "today", "status": 200,
                   "rows": 0, "keys": [], "first_date": "", "last_date": "", "error": ""}
            if p.name == "full_tape":
                res.update(status="skipped", error="large download — test manually")
                results.append(res)
                continue
            try:
                rs = rows(client.get(p.path, p.params(w)))
                ds = _dates(rs)
                keys = sorted(rs[0].keys())[:25] if rs and isinstance(rs[0], dict) else []
                res.update(rows=len(rs), keys=keys,
                           first_date=ds[0] if ds else "", last_date=ds[-1] if ds else "")
            except UWError as e:
                code = str(e).split(" ", 1)[0]
                res.update(status=int(code) if code.isdigit() else "error", error=str(e)[:120])
            results.append(res)
    return results


def render_matrix(results: list[dict]) -> str:
    lines = ["# UW Endpoint Matrix (Basic plan)", "",
             "Derived metadata only — no market data values.", "",
             "| endpoint | when | status | rows | first_date | last_date | keys | error |",
             "|---|---|---|---|---|---|---|---|"]
    for r in results:
        lines.append(f"| {r['name']} | {r['when']} | {r['status']} | {r['rows']} | {r['first_date']} | "
                     f"{r['last_date']} | {', '.join(r['keys'])} | {r['error']} |")
    return "\n".join(lines) + "\n"


def main(argv: list[str]) -> int:
    if "--review" in argv:          # endpoint-review probe (~40 calls) → docs/endpoint-review-probe.md
        from whaleproof.commands.probe_review import main as review
        return review([a for a in argv if a != "--review"])
    s = load_settings()
    if not s.uw_api_key:
        print("UW_API_KEY missing in .env")
        return 1
    client = UWClient(s.uw_api_key, s.live_request_cap)
    results = run_probe(client, datetime.now().date())
    out = REPO_ROOT / "docs" / "endpoint-matrix.md"
    out.write_text(render_matrix(results))
    print(f"wrote {out} — requests used today: {client.usage.daily_count}, "
          f"per-minute remaining: {client.usage.minute_remaining}, daily limit: {client.usage.daily_limit}")
    return 0
