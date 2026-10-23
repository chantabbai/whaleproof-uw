from __future__ import annotations

import argparse
import logging
import os
from pathlib import Path

import uvicorn

from whaleproof.api.app import create_app
from whaleproof.config import REPO_ROOT, load_settings
from whaleproof.desk.service import DeskService
from whaleproof.desk.userdb import UserDB


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(prog="whaleproof serve")
    p.add_argument("--port", type=int, default=8100)
    p.add_argument("--no-live", action="store_true", help="cache only: never call the UW API")
    args = p.parse_args(argv)
    s = load_settings()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    udb = UserDB(Path(os.environ.get("SIGNALDESK_USERDB", REPO_ROOT / "data" / "signaldesk.sqlite")))  # tests: temp file
    svc = DeskService(s.db_path, "" if args.no_live else s.uw_api_key, watchlist_fn=udb.watchlist,
                      journal_fn=udb.open_stock_tickers)
    svc.start()
    app = create_app(s.journal_path, s.db_path, REPO_ROOT / "data" / "backfill.log",
                     REPO_ROOT / "journal" / "backtest-summary.json", desk=(svc, udb, REPO_ROOT / "data" / "desk"))
    print(f"Signal Desk API → http://127.0.0.1:{args.port}  (local only)", flush=True)
    uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="warning")  # never 0.0.0.0
    return 0
