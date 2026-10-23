"""Point-in-time history rows (built by scripts/desk_build_rows.py) run through the same conviction filter as live.

Holdout files are loaded only when `include_holdout=True` — the one-time holdout command is the only caller that
passes it."""
from __future__ import annotations

import json
import pickle
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

from whaleproof.core.data_layer.store import Store

from .config import DEFAULT_FILTER, HOLDOUT, TRAIN, FilterConfig
from .signals import decide


@dataclass(frozen=True)
class HistRow:
    session_date: date
    ticker: str
    direction: int
    premium: float
    otm_pct: float
    price: float
    value: str
    dte: int
    sector: str | None
    gate_fail: str | None
    x5: float | None
    r5: float | None
    stage: str
    reason: str
    tier: str | None
    alert_id: str = ""
    contract: str | None = None      # the whale's option (tracker prices it)
    opt_r5: float | None = None      # backtest's whale-option 5-session return (tracker reconciles against it)


def earnings_map(store: Store) -> dict[str, list[tuple[date, str]]]:
    """(report_date, report_time) per ticker from cached /api/earnings/{t} payloads — no API calls."""
    out: dict[str, list[tuple[date, str]]] = {}
    for key, payload in store.conn.execute("SELECT key, payload FROM raw_cache WHERE endpoint LIKE '/api/earnings/%'"):
        t = key.split("/")[3].split("?")[0]
        data = json.loads(payload)
        rows = data.get("data", []) if isinstance(data, dict) else []
        out[t] = sorted({(date.fromisoformat(str(r["report_date"])[:10]), str(r.get("report_time") or "unknown"))
                         for r in rows if r.get("report_date")})
    return out


def _in_holdout(path: Path) -> bool:
    a, b = path.stem.split("_")[1:3]
    return date.fromisoformat(a) <= HOLDOUT[1] and date.fromisoformat(b) >= HOLDOUT[0]


def load_raw(rows_dir: Path, include_holdout: bool = False) -> list[tuple[dict, dict]]:
    out = []
    for p in sorted(rows_dir.glob("rows_*.pkl")):
        if _in_holdout(p) and not include_holdout:
            continue
        blob = pickle.loads(p.read_bytes())
        out += [(r, blob["extra"].get(r["alert_id"], {})) for r in blob["rows"]]
    return out


def classify_rows(raw: list[tuple[dict, dict]], earnings: dict[str, list[tuple[date, str]]],
                  cfg: FilterConfig = DEFAULT_FILTER) -> list[HistRow]:
    out = []
    for r, x in raw:
        price = float(x.get("underlying_price") or 0)
        if r["setup"] is None or r["label"] != "PURE":
            stage, reason, tier = "gate", r.get("gate_fail") or "not a clean buy", None
        else:
            stage, reason, tier = decide(r["direction"], price, r["premium"] or 0, r["otm_pct"] or 0,
                                         r.get("value") or "unknown", r["session_date"],
                                         earnings.get(r["ticker"], []), cfg)
        out.append(HistRow(r["session_date"], r["ticker"], r["direction"], r["premium"] or 0, r["otm_pct"] or 0,
                           price, r.get("value") or "unknown", r.get("dte") or 0, r.get("sector"), r.get("gate_fail"),
                           r.get("x5"), r.get("r5"), stage, reason, tier, r.get("alert_id") or "",
                           x.get("option_chain"), r.get("opt_r5")))
    return out


def in_window(rows: list[HistRow], start: date, end: date | None) -> list[HistRow]:
    return [r for r in rows if start <= r.session_date and (end is None or r.session_date <= end)]


def _mon(d: date) -> str:
    return f"{d:%b %Y}"


# Plain period names (same as the Methodology page and the MCP), each with its months so nobody has to guess the years.
PRE_LABEL = f"Second sealed test (Oct 2023–{_mon(TRAIN[0] - timedelta(days=1))})"
TRAIN_LABEL = f"Practice year ({_mon(TRAIN[0])}–{_mon(TRAIN[1])}, rules chosen here)"
HOLDOUT_LABEL = f"Sealed test ({_mon(HOLDOUT[0])}–{_mon(HOLDOUT[1])})"
POST_LABEL = f"Recent months (since {_mon(HOLDOUT[1] + timedelta(days=3))})"


def period_label(d: date) -> str:
    """Plain name of the test period a date falls in."""
    if d < TRAIN[0]:
        return PRE_LABEL
    if d <= TRAIN[1]:
        return TRAIN_LABEL
    if d <= HOLDOUT[1]:
        return HOLDOUT_LABEL
    return POST_LABEL
