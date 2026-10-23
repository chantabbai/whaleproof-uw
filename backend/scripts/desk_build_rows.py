"""Build simple-backtest rows (every directional alert: clean buys + noise controls) for a date range and pickle them
under data/desk/ (gitignored, derived). Cache-only: never calls the UW API."""
from __future__ import annotations

import dataclasses
import pickle
import sys
import time
from datetime import date

from whaleproof.config import REPO_ROOT, load_settings
from whaleproof.core.backtest.simple import run_simple_backtest
from whaleproof.core.data_layer.store import Store
from whaleproof.desk.live_evidence import extras


def main(start: str, end: str) -> None:
    store = Store(load_settings().db_path)
    t0 = time.time()
    rows, skipped = run_simple_backtest(store, date.fromisoformat(start), date.fromisoformat(end))
    extra = extras(store, rows)
    out = REPO_ROOT / "data" / "desk" / f"rows_{start}_{end}.pkl"
    with out.open("wb") as f:
        pickle.dump({"rows": [dataclasses.asdict(r) for r in rows], "extra": extra, "skipped": skipped}, f)
    print(f"{start}..{end}: {len(rows)} rows, skipped {skipped}, {time.time() - t0:.0f}s → {out}", flush=True)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
