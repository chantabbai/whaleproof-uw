"""User-owned data (watchlist, trade journal) in its own SQLite file — gitignored, never mixed with the UW cache.
Every write makes a rolling local backup (last 20 copies)."""
from __future__ import annotations

import csv
import io
import json
import re
import sqlite3
import statistics
import threading
from datetime import UTC, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

SYMBOL = re.compile(r"^[A-Z][A-Z0-9.\-]{0,9}$")
KEEP_BACKUPS = 20
FIELDS = ("id", "ticker", "instrument", "direction", "entry_date", "entry_price", "exit_date", "exit_price", "stop",
          "size", "setup", "notes", "r_multiple", "pnl", "status")
INSTRUMENTS = {"stock": 1, "option": 100}     # dollars per point per unit of size (an option contract = 100 shares)

SCHEMA = """
CREATE TABLE IF NOT EXISTS watchlist(ticker TEXT PRIMARY KEY, added_at TEXT);
CREATE TABLE IF NOT EXISTS trades(id INTEGER PRIMARY KEY AUTOINCREMENT, ticker TEXT, direction INTEGER,
  entry_date TEXT, entry_price REAL, exit_date TEXT, exit_price REAL, stop REAL, size REAL, setup TEXT, notes TEXT,
  signal TEXT, created_at TEXT, instrument TEXT DEFAULT 'stock');
"""


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _now() -> str:
    return _utcnow().isoformat(timespec="seconds")


def _today() -> str:
    """Trading-day date in New York (after 8 PM ET the UTC date is already tomorrow)."""
    return _utcnow().astimezone(ZoneInfo("America/New_York")).date().isoformat()


def _symbol(t: str) -> str:
    s = (t or "").strip().upper()
    if not SYMBOL.match(s):
        raise ValueError(f"not a ticker: {t!r}")
    return s


def _num(v, name: str, positive: bool = True) -> float | None:
    if v in (None, ""):
        return None
    x = float(v)
    if positive and x <= 0:
        raise ValueError(f"{name} must be > 0")
    return x


class UserDB:
    def __init__(self, path: Path, backup_dir: Path | None = None):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.backup_dir = Path(backup_dir) if backup_dir else self.path.parent / "backups"
        self._lock = threading.Lock()
        self.conn = sqlite3.connect(self.path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)
        if "instrument" not in {r[1] for r in self.conn.execute("PRAGMA table_info(trades)")}:
            self.conn.execute("ALTER TABLE trades ADD COLUMN instrument TEXT DEFAULT 'stock'")   # journals from before 10-07
        self.conn.commit()

    # ----- watchlist -----
    def watchlist(self) -> list[str]:
        return [r[0] for r in self.conn.execute("SELECT ticker FROM watchlist ORDER BY ticker")]

    def watch_add(self, ticker: str) -> None:
        with self._lock:
            self.conn.execute("INSERT OR IGNORE INTO watchlist VALUES (?,?)", (_symbol(ticker), _now()))
            self.conn.commit()
        self.backup()

    def watch_remove(self, ticker: str) -> None:
        with self._lock:
            self.conn.execute("DELETE FROM watchlist WHERE ticker=?", (_symbol(ticker),))
            self.conn.commit()
        self.backup()

    # ----- journal -----
    def trade_add(self, t: dict) -> int:
        direction = int(t.get("direction") or 1)
        if direction not in (1, -1):
            raise ValueError("direction must be 1 (long) or -1 (short)")
        instrument = str(t.get("instrument") or "stock")
        if instrument not in INSTRUMENTS:
            raise ValueError("instrument must be 'stock' or 'option'")
        row = (_symbol(t.get("ticker", "")), direction, t.get("entry_date") or _today(),
               _num(t.get("entry_price"), "entry_price"), None, None, _num(t.get("stop"), "stop"),
               _num(t.get("size"), "size"), str(t.get("setup") or "manual")[:40], str(t.get("notes") or "")[:2000],
               json.dumps(t.get("signal")) if t.get("signal") else None, _now(), instrument)
        if row[3] is None:
            raise ValueError("entry_price is required")
        with self._lock:
            cur = self.conn.execute("INSERT INTO trades(ticker,direction,entry_date,entry_price,exit_date,exit_price,"
                                    "stop,size,setup,notes,signal,created_at,instrument) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)", row)
            self.conn.commit()
        self.backup()
        return int(cur.lastrowid)

    def trade_close(self, trade_id: int, exit_price: float, exit_date: str | None = None) -> None:
        with self._lock:
            self.conn.execute("UPDATE trades SET exit_price=?, exit_date=? WHERE id=?",
                              (_num(exit_price, "exit_price"), exit_date or _today(), int(trade_id)))
            self.conn.commit()
        self.backup()

    def trade_delete(self, trade_id: int) -> None:
        with self._lock:
            self.conn.execute("DELETE FROM trades WHERE id=?", (int(trade_id),))
            self.conn.commit()
        self.backup()

    def open_stock_tickers(self) -> list[str]:
        """Tickers of open stock trades (the desk prices them live like the watchlist)."""
        return list(dict.fromkeys(r[0] for r in self.conn.execute(
            "SELECT ticker FROM trades WHERE exit_price IS NULL AND COALESCE(instrument, 'stock') = 'stock'")))

    def trades(self) -> list[dict]:
        out = []
        for r in self.conn.execute("SELECT * FROM trades ORDER BY entry_date DESC, id DESC"):
            d = dict(r)
            d["signal"] = json.loads(d["signal"]) if d["signal"] else None
            d |= _result(d)
            out.append(d)
        return out

    def stats(self) -> dict:
        ts = self.trades()
        closed = [t for t in ts if t["status"] == "closed"]
        rs = [t["r_multiple"] for t in closed if t["r_multiple"] is not None]
        by: dict[str, list[dict]] = {}
        for t in closed:
            by.setdefault(t["setup"] or "manual", []).append(t)
        return {"open": len(ts) - len(closed), "closed": len(closed),
                "win_rate": sum(t["pnl_pct"] > 0 for t in closed) / len(closed) if closed else None,
                "avg_r": statistics.fmean(rs) if rs else None,
                "avg_pct": statistics.fmean(t["pnl_pct"] for t in closed) if closed else None,
                "by_setup": {k: {"n": len(v), "win_rate": sum(t["pnl_pct"] > 0 for t in v) / len(v),
                                 "avg_r": statistics.fmean(rr) if (rr := [t["r_multiple"] for t in v
                                                                          if t["r_multiple"] is not None]) else None}
                             for k, v in sorted(by.items())}}

    def export_csv(self) -> str:
        buf = io.StringIO()
        w = csv.DictWriter(buf, fieldnames=[*FIELDS, "pnl_pct", "signal"], extrasaction="ignore")
        w.writeheader()
        for t in self.trades():
            w.writerow({k: _cell(v) for k, v in (t | {"signal": json.dumps(t["signal"]) if t["signal"] else ""}).items()})
        return buf.getvalue()

    def backup(self) -> Path:
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        p = self.backup_dir / f"signaldesk-{datetime.now().strftime('%Y%m%d-%H%M%S-%f')}.sqlite"
        dst = sqlite3.connect(p)
        with self._lock:
            self.conn.backup(dst)
        dst.close()
        for old in sorted(self.backup_dir.glob("signaldesk-*.sqlite"))[:-KEEP_BACKUPS]:
            old.unlink()
        return p


def _cell(v):
    """Spreadsheet formula-injection guard: text starting with = + - @ is prefixed with a quote."""
    return "'" + v if isinstance(v, str) and v[:1] in ("=", "+", "-", "@") else v


def _result(t: dict) -> dict:
    if t.get("exit_price") is None:
        return {"status": "open", "pnl_pct": None, "pnl": None, "r_multiple": None}
    move = (t["exit_price"] - t["entry_price"]) * t["direction"]
    risk = abs(t["entry_price"] - t["stop"]) if t.get("stop") else None
    return {"status": "closed", "pnl_pct": move / t["entry_price"],
            "pnl": move * t["size"] * INSTRUMENTS.get(t.get("instrument") or "stock", 1) if t.get("size") else None,
            "r_multiple": move / risk if risk else None}
