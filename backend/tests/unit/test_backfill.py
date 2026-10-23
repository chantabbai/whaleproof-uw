from datetime import date

from whaleproof.commands import backfill as bf
from whaleproof.core.data_layer.client import UWBudgetExceeded


def test_newest_first_resumable_and_budget_stop(store, monkeypatch):
    seen = []
    monkeypatch.setattr(bf, "ingest_flow_day", lambda c, s, d, **k: seen.append(d) or 0)
    monkeypatch.setattr(bf, "ingest_market", lambda c, s, d, **k: None)
    monkeypatch.setattr(bf, "ingest_series", lambda c, s, t, today: None)
    res = bf.backfill(object(), store, date(2026, 9, 21), date(2026, 9, 25), today=date(2026, 9, 27))
    assert seen == [date(2026, 9, 25), date(2026, 9, 24), date(2026, 9, 23), date(2026, 9, 22), date(2026, 9, 21)]
    assert res["days_done"] == 5

    seen.clear()
    res = bf.backfill(object(), store, date(2026, 9, 21), date(2026, 9, 25), today=date(2026, 9, 27))
    assert seen == [] and res["days_skipped"] == 5

    def boom(*a, **k):
        raise UWBudgetExceeded("cap")
    monkeypatch.setattr(bf, "ingest_flow_day", boom)
    res = bf.backfill(object(), store, date(2026, 9, 14), date(2026, 9, 18), today=date(2026, 9, 27))
    assert res["stopped_reason"] == "budget" and store.get_checkpoint("day:2026-09-18") is None


def test_enrich_fetches_unusual_per_day_and_vol_history_once_per_ticker(store, monkeypatch):
    from tests.conftest import raw_alert
    from whaleproof.core.data_layer.models import alert_to_row, parse_alert
    for i, (t, day) in enumerate([("NVDA", "2026-09-24"), ("AMD", "2026-09-24"), ("NVDA", "2026-09-25")]):
        r = raw_alert(id=f"e{i}", ticker=t, created_at=f"{day}T15:00:00Z", expiry="2026-10-16")
        store.upsert_alerts([alert_to_row(parse_alert(r), r)])
    days, vols = [], []
    monkeypatch.setattr(bf, "ingest_uw_unusual_paged", lambda c, s, d, **k: days.append(d))
    monkeypatch.setattr(bf, "ingest_realized_vol",
                        lambda c, s, t, today: vols.append(t) or s.put_metric(t, "all", "vol_hist", [["x"]]))
    res = bf.enrich(object(), store, date(2026, 9, 24), date(2026, 9, 25), today=date(2026, 9, 27))
    assert days == [date(2026, 9, 25), date(2026, 9, 24)] and sorted(vols) == ["AMD", "NVDA"]
    assert res["days_done"] == 2
    days.clear()
    assert bf.enrich(object(), store, date(2026, 9, 24), date(2026, 9, 25), today=date(2026, 9, 27))["days_done"] == 0
    assert days == []


def test_enrich_stops_on_budget(store, monkeypatch):
    def boom(*a, **k):
        raise UWBudgetExceeded("cap")
    monkeypatch.setattr(bf, "ingest_uw_unusual_paged", boom)
    res = bf.enrich(object(), store, date(2026, 9, 24), date(2026, 9, 25), today=date(2026, 9, 27))
    assert res["stopped_reason"] == "budget" and store.get_checkpoint("enrich:2026-09-25") is None


def test_fill_contract_history_fetches_only_finalist_candidates_once(store, monkeypatch):
    """Real option prices for F2/F3 candidates (long + cheap or far OTM) whose contract history isn't cached."""
    from types import SimpleNamespace as NS
    a1 = NS(option_chain="A", direction=1, otm_pct=0.20)                     # far OTM long → needed
    a2 = NS(option_chain="B", direction=1, otm_pct=0.02)                     # cheap long → needed
    a3 = NS(option_chain="C", direction=-1, otm_pct=0.20)                    # short → not a F2/F3 trade
    a4 = NS(option_chain="D", direction=1, otm_pct=0.02)                     # fair long → not needed
    monkeypatch.setattr(bf, "day_trades", lambda s, d: [(a1, [], False), (a2, [], False), (a3, [], False),
                                                        (a4, [], False)])
    monkeypatch.setattr(bf, "option_view", lambda s, a: "cheap" if a.option_chain == "B" else "fair")
    got = []
    monkeypatch.setattr(bf, "ingest_contract_oi", lambda c, s, chain, ttl=None: got.append(chain))
    monkeypatch.setattr(bf, "has_history", lambda s, chain: chain in got)
    res = bf.fill_contract_history(object(), store, date(2026, 9, 22), date(2026, 9, 23), date(2026, 9, 27))
    assert got == ["A", "B"] and res["fetched"] == 2 and store.get_checkpoint("contracts_done") == "2026-09-23"
    assert bf.fill_contract_history(object(), store, date(2026, 9, 22), date(2026, 9, 23), date(2026, 9, 27))["stopped_reason"] == "already done"


def test_fill_f1_oi_fetches_every_f1_shaped_row_missing_oi(store, monkeypatch):
    """Amendment 15: OI for every F1-shaped gate passer (31–90 DTE, > 5% OTM, not a put sale), both directions."""
    from types import SimpleNamespace as NS
    rows = [(NS(option_chain="A", direction=1, dte=45, otm_pct=0.08), [], False),     # shaped, no OI → fetch
            (NS(option_chain="B", direction=-1, dte=60, otm_pct=0.20), [], False),    # short too → fetch
            (NS(option_chain="C", direction=1, dte=20, otm_pct=0.08), [], False),     # too short-dated
            (NS(option_chain="D", direction=1, dte=45, otm_pct=0.03), [], False),     # not far enough OTM
            (NS(option_chain="E", direction=1, dte=45, otm_pct=0.08), ["multi-leg"], False),   # gate failure
            (NS(option_chain="F", direction=1, dte=45, otm_pct=0.08), [], True),      # put sale
            (NS(option_chain="G", direction=1, dte=45, otm_pct=0.08), [], False)]     # already has OI
    monkeypatch.setattr(bf, "day_trades", lambda s, d: rows)
    monkeypatch.setattr(bf, "oi_ratio", lambda s, a: 0.9 if a.option_chain == "G" or a.option_chain in got else None)
    got = []
    monkeypatch.setattr(bf, "ingest_contract_oi", lambda c, s, chain, ttl=None: got.append(chain))
    res = bf.fill_f1_oi(object(), store, date(2026, 9, 22), date(2026, 9, 22), date(2026, 9, 27))
    assert got == ["A", "B"] and res["fetched"] == 2 and store.get_checkpoint("f1_oi_done") == "2026-09-22"
    assert bf.fill_f1_oi(object(), store, date(2026, 9, 22), date(2026, 9, 22), date(2026, 9, 27))["stopped_reason"] \
        == "already done"


def test_fill_f1_oi_stops_on_budget_without_checkpoint(store, monkeypatch):
    from types import SimpleNamespace as NS
    monkeypatch.setattr(bf, "day_trades", lambda s, d: [(NS(option_chain="A", direction=1, dte=45, otm_pct=0.08), [], False)])
    monkeypatch.setattr(bf, "oi_ratio", lambda s, a: None)
    res = bf.fill_f1_oi(object(), store, date(2026, 9, 22), date(2026, 9, 22), date(2026, 9, 27), stop_at=lambda: True)
    assert res["stopped_reason"] == "budget" and store.get_checkpoint("f1_oi_done") is None
