from __future__ import annotations

import json
import sqlite3
import time
from datetime import date
from pathlib import Path
from typing import Any

from .models import Bar

SCHEMA = """
CREATE TABLE IF NOT EXISTS raw_cache(key TEXT PRIMARY KEY, endpoint TEXT, fetched_at REAL, payload TEXT);
CREATE TABLE IF NOT EXISTS flow_alerts(id TEXT PRIMARY KEY, ticker TEXT, created_at TEXT, session_date TEXT, payload TEXT);
CREATE INDEX IF NOT EXISTS ix_fa_date ON flow_alerts(session_date);
CREATE INDEX IF NOT EXISTS ix_fa_ticker_date ON flow_alerts(ticker, session_date);
CREATE TABLE IF NOT EXISTS daily_metric(ticker TEXT, date TEXT, kind TEXT, payload TEXT, PRIMARY KEY(ticker, date, kind));
CREATE TABLE IF NOT EXISTS ohlc_daily(ticker TEXT, date TEXT, open REAL, high REAL, low REAL, close REAL, volume REAL, PRIMARY KEY(ticker, date));
CREATE TABLE IF NOT EXISTS checkpoint(name TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS pick_outcome(pick_id TEXT PRIMARY KEY, updated_at TEXT, payload TEXT);
CREATE TABLE IF NOT EXISTS pick_health(pick_id TEXT PRIMARY KEY, as_of TEXT, payload TEXT);
CREATE TABLE IF NOT EXISTS pick_health_log(pick_id TEXT, as_of TEXT, state TEXT, reason TEXT,
    PRIMARY KEY(pick_id, as_of));
CREATE TABLE IF NOT EXISTS option_marks(pick_id TEXT, day TEXT, tag TEXT, at TEXT, payload TEXT,
    PRIMARY KEY(pick_id, day, tag));
CREATE TABLE IF NOT EXISTS scan_result(session_date TEXT, kind TEXT, created_at TEXT, weights_version TEXT,
    payload TEXT, PRIMARY KEY(session_date, kind, created_at));
"""


def _d(x: date | str) -> str:
    return x.isoformat() if isinstance(x, date) else x


class Store:
    def __init__(self, path: Path):
        path = Path(path)
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(path, check_same_thread=False, timeout=30)
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA synchronous=NORMAL")
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    # raw cache
    def cache_get(self, key: str, max_age_s: float | None) -> Any | None:
        row = self.conn.execute("SELECT fetched_at, payload FROM raw_cache WHERE key=?", (key,)).fetchone()
        if row is None:
            return None
        if max_age_s is not None and time.time() - row[0] > max_age_s:
            return None
        return json.loads(row[1])

    def cache_put(self, key: str, endpoint: str, payload: Any) -> None:
        self.conn.execute("INSERT OR REPLACE INTO raw_cache VALUES (?,?,?,?)",
                          (key, endpoint, time.time(), json.dumps(payload)))
        self.conn.commit()

    # flow alerts
    def upsert_alerts(self, rows: list[dict]) -> int:
        before = self.conn.total_changes
        self.conn.executemany(
            "INSERT OR IGNORE INTO flow_alerts VALUES (?,?,?,?,?)",
            [(r["id"], r["ticker"], r["created_at"], r["session_date"], json.dumps(r)) for r in rows])
        self.conn.commit()
        return self.conn.total_changes - before

    def alerts_between(self, start: date, end: date, ticker: str | None = None) -> list[dict]:
        sql = "SELECT payload FROM flow_alerts WHERE session_date BETWEEN ? AND ?"
        args: list[Any] = [_d(start), _d(end)]
        if ticker:
            sql += " AND ticker=?"
            args.append(ticker)
        sql += " ORDER BY created_at, id"
        return [json.loads(r[0]) for r in self.conn.execute(sql, args)]

    # daily metrics
    def put_metric(self, ticker: str, d: date | str, kind: str, payload: Any) -> None:
        self.conn.execute("INSERT OR REPLACE INTO daily_metric VALUES (?,?,?,?)",
                          (ticker, _d(d), kind, json.dumps(payload)))
        self.conn.commit()

    def get_metric(self, ticker: str, d: date | str, kind: str) -> Any | None:
        row = self.conn.execute("SELECT payload FROM daily_metric WHERE ticker=? AND date=? AND kind=?",
                                (ticker, _d(d), kind)).fetchone()
        return json.loads(row[0]) if row else None

    def latest_metric(self, ticker: str, on_or_before: date, kind: str) -> tuple[date, Any] | None:
        row = self.conn.execute(
            "SELECT date, payload FROM daily_metric WHERE ticker=? AND kind=? AND date<=? AND date!='all' "
            "ORDER BY date DESC LIMIT 1", (ticker, kind, _d(on_or_before))).fetchone()
        return (date.fromisoformat(row[0]), json.loads(row[1])) if row else None

    # ohlc
    def put_ohlc(self, ticker: str, bars: list[Bar]) -> None:
        self.conn.executemany("INSERT OR REPLACE INTO ohlc_daily VALUES (?,?,?,?,?,?,?)",
                              [(ticker, b.date.isoformat(), b.open, b.high, b.low, b.close, b.volume) for b in bars])
        self.conn.commit()

    def get_ohlc(self, ticker: str, start: date, end: date) -> list[Bar]:
        rows = self.conn.execute(
            "SELECT date, open, high, low, close, volume FROM ohlc_daily WHERE ticker=? AND date BETWEEN ? AND ? "
            "ORDER BY date", (ticker, _d(start), _d(end))).fetchall()
        return [Bar(date.fromisoformat(r[0]), *r[1:]) for r in rows]

    # checkpoints
    def get_checkpoint(self, name: str) -> str | None:
        row = self.conn.execute("SELECT value FROM checkpoint WHERE name=?", (name,)).fetchone()
        return row[0] if row else None

    def set_checkpoint(self, name: str, value: str) -> None:
        self.conn.execute("INSERT OR REPLACE INTO checkpoint VALUES (?,?)", (name, value))
        self.conn.commit()

    # live option marks (raw quotes stay in this gitignored DB, never redistributed)
    def put_mark(self, pick_id: str, day: str, tag: str, at: str, payload: dict) -> None:
        self.conn.execute("INSERT OR REPLACE INTO option_marks VALUES (?,?,?,?,?)",
                          (pick_id, day, tag, at, json.dumps(payload)))
        self.conn.commit()

    def marks(self, pick_id: str) -> list[dict]:
        rs = self.conn.execute("SELECT day, tag, at, payload FROM option_marks WHERE pick_id=? ORDER BY day, at",
                               (pick_id,)).fetchall()
        return [{"day": d, "tag": t, "at": a, **json.loads(p)} for d, t, a, p in rs]

    # scan snapshots (derived verdict summaries only — never raw UW payloads)
    def put_scan(self, session_date: str, kind: str, created_at: str, weights_version: str, rows: list[dict]) -> None:
        self.conn.execute("INSERT OR REPLACE INTO scan_result VALUES (?,?,?,?,?)",
                          (session_date, kind, created_at, weights_version, json.dumps(rows)))
        self.conn.commit()

    def latest_scan(self, kind: str) -> dict | None:
        row = self.conn.execute("SELECT session_date, created_at, weights_version, payload FROM scan_result "
                                "WHERE kind=? ORDER BY created_at DESC LIMIT 1", (kind,)).fetchone()
        if not row:
            return None
        return {"session_date": row[0], "kind": kind, "created_at": row[1], "weights_version": row[2],
                "rows": json.loads(row[3])}
