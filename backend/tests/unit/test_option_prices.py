"""Real option results from UW's per-contract daily history (already cached for the morning OI check): buy at the
entry day's open plus half the real spread, sell at the exit day's closing bid. Local cache only — no API calls."""
from datetime import date

from whaleproof.core.backtest import option_prices as op
from whaleproof.core.data_layer.fetch import cache_key

CHAIN = "NVDA261016C00200000"


def day(d, open_=None, last=None, bid=None, ask=None, vol=10):
    return {"date": d, "open_price": open_, "last_price": last, "nbbo_bid": bid, "nbbo_ask": ask, "volume": vol,
            "open_interest": 100}


def seed(store, chains):
    path = f"/api/option-contract/{CHAIN}/historic"
    store.cache_put(cache_key(path, {"limit": 500}), path, {"chains": chains})


def test_real_return_uses_open_plus_half_spread_and_exit_bid(store):
    seed(store, [day("2026-09-28", open_=2.00, last=2.1, bid=1.9, ask=2.1),     # entry: 2.00 + 0.20/2 = 2.10
                 day("2026-10-02", open_=3.0, last=3.1, bid=3.0, ask=3.2)])      # exit at the bid 3.00
    r = op.real_option_return(store, CHAIN, date(2026, 9, 28), date(2026, 10, 2))
    assert r["buy"] == 2.1 and r["sell"] == 3.0 and round(r["ret"], 4) == round(3.0 / 2.1 - 1, 4)
    assert round(r["spread_pct"], 3) == 0.1


def test_missing_history_or_no_trade_is_none(store):
    assert op.real_option_return(store, CHAIN, date(2026, 9, 28), date(2026, 10, 2)) is None      # not cached
    seed(store, [day("2026-09-28", open_=None, last=None, bid=1.9, ask=2.1, vol=0),
                 day("2026-10-02", open_=3.0, last=3.1, bid=3.0, ask=3.2)])
    assert op.real_option_return(store, CHAIN, date(2026, 9, 28), date(2026, 10, 2)) is None      # no entry trade


def test_exit_falls_back_to_last_price_less_half_spread_and_expired_worthless(store):
    seed(store, [day("2026-09-28", open_=2.0, bid=1.9, ask=2.1),
                 day("2026-10-02", last=1.0, bid=None, ask=None)])
    r = op.real_option_return(store, CHAIN, date(2026, 9, 28), date(2026, 10, 2))
    assert r["sell"] == 1.0 * (1 - 0.05)                 # no closing quote → last price less the entry half-spread
    seed(store, [day("2026-09-28", open_=2.0, bid=1.9, ask=2.1), day("2026-09-30", last=0.5, bid=0.4, ask=0.6)])
    r = op.real_option_return(store, CHAIN, date(2026, 9, 28), date(2026, 10, 2))
    assert r is None                                     # no row on the exit day → not measured (never guessed)


def test_has_history_is_cache_only(store):
    assert not op.has_history(store, CHAIN)
    seed(store, [])
    assert op.has_history(store, CHAIN)


def test_three_fill_levels_amendment_18(store):
    """Mid = open → exit mid; normal = open + ½ gap → exit bid; wide = open + ¾ gap → exit mid − ¾ exit gap."""
    seed(store, [day("2026-09-28", open_=2.00, bid=1.9, ask=2.1),                  # entry gap 0.20
                 day("2026-10-02", open_=3.0, last=3.1, bid=3.0, ask=3.2)])       # exit gap 0.20, mid 3.10
    r = op.real_option_return(store, CHAIN, date(2026, 9, 28), date(2026, 10, 2))
    assert round(r["ret_mid"], 6) == round(3.1 / 2.0 - 1, 6)
    assert round(r["ret"], 6) == round(3.0 / 2.1 - 1, 6)                           # normal unchanged
    assert round(r["ret_wide"], 6) == round((3.1 - 0.15) / 2.15 - 1, 6)


def test_fill_levels_fall_back_to_last_price(store):
    seed(store, [day("2026-09-28", open_=2.0, bid=1.9, ask=2.1),                  # spread_pct 10%
                 day("2026-10-02", last=1.0, bid=None, ask=None)])
    r = op.real_option_return(store, CHAIN, date(2026, 9, 28), date(2026, 10, 2))
    assert round(r["ret_mid"], 6) == round(1.0 / 2.0 - 1, 6)
    assert round(r["ret_wide"], 6) == round(1.0 * (1 - 0.075) / 2.15 - 1, 6)
