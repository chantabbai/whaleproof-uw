"""IV-rank backfill for docs/PREPERIOD-FAROTM-TEST.md: one `/api/stock/{t}/iv-rank?date=2024-09-27&timespan=1y` call per
ticker with a clean long buy > 15% OTM in the pre-period rows (before price/earnings stages). Cached forever (past
date), so reruns cost nothing for tickers already fetched. Nothing else is fetched.
Usage: uv run python scripts/research/preperiod_ivrank_backfill.py [stop_at_daily_count]"""
from __future__ import annotations

import pickle
import sys

from whaleproof.config import REPO_ROOT, load_settings
from whaleproof.core.data_layer.client import UWBudgetExceeded, UWClient, UWError
from whaleproof.core.data_layer.fetch import cached_get, rows
from whaleproof.core.data_layer.ingest import KIND_IVR
from whaleproof.core.data_layer.models import num
from whaleproof.core.data_layer.store import Store
from whaleproof.desk.config import DEFAULT_FILTER

PRE_PICKLES = ("rows_2023-10-31_2024-01-31", "rows_2024-02-01_2024-05-31", "rows_2024-06-01_2024-09-27")
PARAMS = {"date": "2024-09-27", "timespan": "1y"}


def candidate_tickers() -> list[str]:
    out = set()
    for stem in PRE_PICKLES:
        blob = pickle.loads((REPO_ROOT / "data" / "desk" / f"{stem}.pkl").read_bytes())
        out |= {r["ticker"] for r in blob["rows"] if r["label"] == "PURE" and r["setup"] and r["direction"] > 0
                and (r["otm_pct"] or 0) > DEFAULT_FILTER.far_otm}
    return sorted(out)


def main(stop_at: int) -> None:
    s = load_settings()
    store = Store(s.db_path)
    client = UWClient(s.uw_api_key, daily_cap=stop_at)
    tickers = candidate_tickers()
    print(f"{len(tickers)} tickers", flush=True)
    stored = 0
    try:
        for t in tickers:
            try:
                for r in rows(cached_get(client, store, f"/api/stock/{t}/iv-rank", PARAMS, None)):
                    v = num(r.get("iv_rank_1y"))
                    if r.get("date") and v is not None:
                        store.put_metric(t, str(r["date"])[:10], KIND_IVR, v)
                        stored += 1
            except UWBudgetExceeded:
                raise
            except UWError as e:
                print("skip", t, str(e)[:100], flush=True)
        print(f"DONE: {stored} iv-rank rows stored (count {client.usage.daily_count})", flush=True)
    except UWBudgetExceeded as e:
        print(f"STOPPED on budget: {e} — rerun after the 20:00 ET reset (cached tickers cost nothing)", flush=True)


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 37_500)
