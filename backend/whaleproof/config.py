from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class Settings:
    uw_api_key: str
    db_path: Path
    journal_path: Path
    live_request_cap: int = 39_500
    backfill_request_cap: int = 28_000  # = daily limit − reserve; tunable in .env
    backfill_stop: str = "07:00"        # night mode only: backfill never runs 07:00–20:00 ET
    backfill_mode: str = "adaptive"     # adaptive = use whatever live jobs won't need; night = fixed cap + quiet hours
    daily_limit: int = 40_000
    backfill_max: int | None = None     # optional hard ceiling for adaptive backfill (WHALEPROOF_BACKFILL_MAX)


def load_settings() -> Settings:
    load_dotenv(REPO_ROOT / ".env")  # each run is a new process → .env edits apply next run; real env wins
    limit = int(os.environ.get("WHALEPROOF_DAILY_LIMIT", "40000"))
    return Settings(
        uw_api_key=os.environ.get("UW_API_KEY", "").strip(),
        db_path=Path(os.environ.get("WHALEPROOF_DB", REPO_ROOT / "data" / "whaleproof.sqlite")),
        journal_path=Path(os.environ.get("WHALEPROOF_JOURNAL", REPO_ROOT / "journal" / "picks.jsonl")),
        live_request_cap=limit - 500,
        backfill_request_cap=limit - int(os.environ.get("WHALEPROOF_BACKFILL_RESERVE", "12000")),
        backfill_stop=os.environ.get("WHALEPROOF_BACKFILL_STOP", "07:00").strip(),
        backfill_mode=os.environ.get("WHALEPROOF_BACKFILL_MODE", "adaptive").strip(),
        daily_limit=limit,
        backfill_max=int(os.environ["WHALEPROOF_BACKFILL_MAX"]) if os.environ.get("WHALEPROOF_BACKFILL_MAX") else None,
    )
