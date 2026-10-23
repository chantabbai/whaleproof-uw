"""Watchlist + trade journal in data/signaldesk.sqlite (separate from the UW cache)."""
import csv
import io

import pytest

from whaleproof.desk.userdb import UserDB


@pytest.fixture
def db(tmp_path):
    return UserDB(tmp_path / "sd.sqlite", backup_dir=tmp_path / "bk")


def test_watchlist_add_remove_normalizes(db):
    db.watch_add(" nvda ")
    db.watch_add("NVDA")
    db.watch_add("spy")
    assert db.watchlist() == ["NVDA", "SPY"]
    db.watch_remove("nvda")
    assert db.watchlist() == ["SPY"]


def test_watchlist_rejects_bad_symbols(db):
    with pytest.raises(ValueError):
        db.watch_add("DROP TABLE;")


def test_trade_lifecycle_stats_and_snapshot(db):
    t1 = db.trade_add({"ticker": "aapl", "direction": 1, "entry_price": 100, "stop": 95, "size": 10,
                       "setup": "whale", "signal": {"tier": "whale", "why": ["x"]}, "notes": "n"})
    db.trade_close(t1, exit_price=110)                     # +10 on 5 risk → +2R
    t2 = db.trade_add({"ticker": "MSFT", "direction": -1, "entry_price": 50, "stop": 52, "size": 5, "setup": "far_otm"})
    db.trade_close(t2, exit_price=51)                      # short, lost 1 on 2 risk → −0.5R
    db.trade_add({"ticker": "TSLA", "direction": 1, "entry_price": 10, "stop": 9, "size": 1, "setup": "whale"})
    s = db.stats()
    assert s["closed"] == 2 and s["open"] == 1 and s["win_rate"] == 0.5
    assert abs(s["avg_r"] - 0.75) < 1e-9
    assert s["by_setup"]["whale"]["n"] == 1 and s["by_setup"]["far_otm"]["avg_r"] == -0.5
    t = db.trades()[0]
    assert t["ticker"] == "TSLA" or any(x["signal"] == {"tier": "whale", "why": ["x"]} for x in db.trades())


def test_trade_validation(db):
    with pytest.raises(ValueError):
        db.trade_add({"ticker": "AAPL", "direction": 1, "entry_price": -1})


def test_csv_export_and_backup(db, tmp_path):
    db.trade_add({"ticker": "AAPL", "direction": 1, "entry_price": 100, "size": 1, "setup": "manual"})
    rows = list(csv.DictReader(io.StringIO(db.export_csv())))
    assert rows[0]["ticker"] == "AAPL"
    p = db.backup()
    assert p.exists() and p.parent == tmp_path / "bk"


def test_csv_export_neutralises_formulas(db):
    db.trade_add({"ticker": "AAPL", "direction": 1, "entry_price": 100, "notes": "=HYPERLINK(\"x\")"})
    row = next(csv.DictReader(io.StringIO(db.export_csv())))
    assert row["notes"].startswith("'=")


def test_delete_keeps_a_backup_with_the_trade_in_it(db, tmp_path):
    """An accidental delete must be recoverable: a backup taken just before the delete still holds the trade."""
    import sqlite3
    tid = db.trade_add({"ticker": "AAPL", "direction": 1, "entry_price": 100, "setup": "manual"})
    db.trade_delete(tid)
    assert db.trades() == []
    backups = sorted((tmp_path / "bk").glob("signaldesk-*.sqlite"))
    held = [p for p in backups if sqlite3.connect(p).execute("SELECT count(*) FROM trades WHERE id=?", (tid,)).fetchone()[0]]
    assert held and held[-1] == backups[-2]       # the one right before the post-delete backup


def test_option_trades_count_100_shares_per_contract(db):
    """Size is in contracts for options: 2 contracts bought at $1.50, sold at $2.00 = +$100, not +$1."""
    t = db.trade_add({"ticker": "CRWV", "direction": 1, "entry_price": 1.5, "size": 2, "instrument": "option"})
    db.trade_close(t, 2.0)
    row = next(x for x in db.trades() if x["id"] == t)
    assert row["instrument"] == "option" and row["pnl"] == pytest.approx(100.0)
    s = db.trade_add({"ticker": "CRWV", "direction": 1, "entry_price": 100, "size": 10})
    db.trade_close(s, 101)
    assert next(x for x in db.trades() if x["id"] == s)["pnl"] == pytest.approx(10.0)   # stock is the default


def test_old_journal_files_gain_the_instrument_column(tmp_path):
    import sqlite3
    p = tmp_path / "old.sqlite"
    c = sqlite3.connect(p)
    c.execute("CREATE TABLE trades(id INTEGER PRIMARY KEY AUTOINCREMENT, ticker TEXT, direction INTEGER, entry_date TEXT, "
              "entry_price REAL, exit_date TEXT, exit_price REAL, stop REAL, size REAL, setup TEXT, notes TEXT, signal TEXT, "
              "created_at TEXT)")
    c.execute("INSERT INTO trades(ticker,direction,entry_date,entry_price,size) VALUES ('AAA',1,'2026-10-01',10,5)")
    c.commit(); c.close()
    old = UserDB(p, backup_dir=tmp_path / "bk")
    assert old.trades()[0]["instrument"] == "stock"


def test_default_dates_are_new_york_dates(db, monkeypatch):
    """At 23:00 ET the UTC date is already tomorrow; a trade logged then belongs to today (ET)."""
    from datetime import datetime, timezone
    import whaleproof.desk.userdb as u
    monkeypatch.setattr(u, "_utcnow", lambda: datetime(2026, 10, 7, 3, 0, tzinfo=timezone.utc))
    t = db.trade_add({"ticker": "AAA", "direction": 1, "entry_price": 10})
    db.trade_close(t, 11)
    row = db.trades()[0]
    assert row["entry_date"] == "2026-10-06" and row["exit_date"] == "2026-10-06"


def test_open_stock_tickers_leave_out_closed_trades_and_options(db):
    a = db.trade_add({"ticker": "GWRE", "direction": 1, "entry_price": 164.35, "size": 1})
    db.trade_add({"ticker": "CRDO", "direction": 1, "entry_price": 214.14, "size": 1})
    db.trade_add({"ticker": "SPY", "direction": 1, "entry_price": 2.5, "size": 1, "instrument": "option"})
    db.trade_add({"ticker": "GWRE", "direction": 1, "entry_price": 160.0, "size": 1})
    assert db.open_stock_tickers() == ["GWRE", "CRDO"]
    db.trade_close(a, 170.0)
    assert set(db.open_stock_tickers()) == {"GWRE", "CRDO"}       # the second GWRE trade is still open
