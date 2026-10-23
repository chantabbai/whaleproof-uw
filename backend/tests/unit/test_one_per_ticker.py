"""Amendment 10: at most one pick per ticker per day; the highest score_parity wins."""
from datetime import date
from types import SimpleNamespace as NS

from whaleproof.core.backtest.breakdowns import top_n_per_day
from whaleproof.core.verdict.scan import select_go

D = date(2026, 9, 28)


def v(ticker, direction, score, label="GO"):
    return NS(ticker=ticker, direction=direction, score_parity=score, label=label, session_date=D)


def test_select_go_keeps_best_per_ticker_then_top_n():
    vs = [v("SPY", 1, 78), v("SPY", -1, 77), v("QQQ", 1, 76), v("AAA", 1, 90, "WATCH"), v("BBB", -1, 71)]
    out = select_go(vs, top=5)
    assert [(x.ticker, x.direction) for x in out] == [("SPY", 1), ("QQQ", 1), ("BBB", -1)]
    assert [x.ticker for x in select_go(vs, top=2)] == ["SPY", "QQQ"]


def test_select_go_is_order_independent():
    vs = [v("SPY", -1, 77), v("SPY", 1, 78)]
    assert select_go(vs, top=5)[0].direction == 1


def test_backtest_official_like_mirrors_one_per_ticker():
    rows = [NS(session_date=D, ticker="SPY", direction=1, label="GO", score_parity=78),
            NS(session_date=D, ticker="SPY", direction=-1, label="GO", score_parity=77),
            NS(session_date=D, ticker="QQQ", direction=1, label="GO", score_parity=76)]
    assert [(r.ticker, r.direction) for r in top_n_per_day(rows, 5)] == [("SPY", 1), ("QQQ", 1)]


def test_intraday_new_picks_one_per_ticker_per_session():
    from whaleproof.commands.intraday import new_intraday
    vs = [v("SPY", -1, 80), v("SPY", 1, 75), v("QQQ", 1, 72), v("NVDA", 1, 71)]
    rows = [{"pick_id": f"{x.ticker}{x.direction}", "ticker": x.ticker, "session_date": D.isoformat()} for x in vs]
    journal = [{"kind": "intraday", "ticker": "QQQ", "session_date": D.isoformat(), "pick_id": "old"},
               {"kind": "official", "ticker": "NVDA", "session_date": "2026-09-25", "pick_id": "o"}]
    assert [r["pick_id"] for r in new_intraday(rows, vs, journal)] == ["SPY-1", "NVDA1"]
