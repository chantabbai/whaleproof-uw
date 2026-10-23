"""uw_flagged check: is our candidate's exact contract on UW's daily unusual list (≥$250K)? Weight 0 — fit decides."""
from datetime import date, datetime, timezone

from tests.conftest import raw_alert
from whaleproof.core.checks import ALL_CHECKS
from whaleproof.core.checks.confluence import uw_flagged
from whaleproof.core.data_layer import ingest
from whaleproof.core.data_layer.context import build_context
from whaleproof.core.data_layer.models import alert_to_row, parse_alert
from whaleproof.core.verdict.verdict import evaluate
from whaleproof.core.verdict.weights import BACKTESTABLE, CURRENT, V0, Weights

D = date(2026, 9, 22)
AS_OF = datetime(2026, 9, 22, 20, 15, tzinfo=timezone.utc)
CHAIN = "NVDA261016C00200000"


def uw_row(sym, tkr="NVDA", prem="500000"):
    return {"option_symbol": sym, "ticker_symbol": tkr, "premium": prem, "option_type": "call"}


class Fake:
    """Returns `per_call[i]` rows for the i-th request (default: none)."""
    def __init__(self, per_call):
        self.per_call, self.calls = per_call, []

    def get(self, path, params=None):
        self.calls.append((path, dict(params or {})))
        i = len(self.calls) - 1
        return {"data": self.per_call[i] if i < len(self.per_call) else []}


def test_ingest_partitions_by_sector_plus_etf_and_stores_symbols(store):
    f = Fake([[uw_row(CHAIN)], [uw_row("X"), uw_row("LOW", prem="100")]])
    ingest.ingest_uw_unusual(f, store, D)
    assert len(f.calls) == len(ingest.UW_UNUSUAL_PARTS) == 12
    p = f.calls[0][1]
    assert f.calls[0][0] == "/api/option-activity/unusual"
    assert p["date"] == "2026-09-22" and p["min_premium"] == 250_000 and p["limit"] == ingest.UW_UNUSUAL_LIMIT
    assert {"sectors[]": "Basic Materials"}.items() <= p.items()
    assert f.calls[-1][1]["issue_types[]"] == "ETF"
    m = store.get_metric("UW_UNUSUAL", D, "contracts")
    assert sorted(m["symbols"]) == [CHAIN, "X"]      # sub-$250K dropped even if server returns it
    assert m["complete"] is True


def test_ingest_marks_incomplete_when_any_partition_hits_limit(store, monkeypatch):
    monkeypatch.setattr(ingest, "UW_UNUSUAL_LIMIT", 2)
    ingest.ingest_uw_unusual(Fake([[uw_row("A"), uw_row("B")]]), store, D)
    assert store.get_metric("UW_UNUSUAL", D, "contracts")["complete"] is False


def test_paged_ingest_until_short_page(store, monkeypatch):
    """Probe 09-28: paging the unusual screener reproduced the cached list exactly (Amendment 1) → ~2 calls/day."""
    monkeypatch.setattr(ingest, "UW_UNUSUAL_LIMIT", 2)
    f = Fake([[uw_row("A"), uw_row("B")], [uw_row("C")]])
    ingest.ingest_uw_unusual_paged(f, store, D)
    assert [c[1]["page"] for c in f.calls] == [0, 1] and f.calls[0][0] == "/api/screener/option-contracts"
    assert f.calls[0][1]["unusual"] == "true" and f.calls[0][1]["min_premium"] == 250_000
    m = store.get_metric("UW_UNUSUAL", D, "contracts")
    assert m["symbols"] == ["A", "B", "C"] and m["complete"] is True


def test_paged_ingest_incomplete_when_page_cap_hit_or_page_repeats(store, monkeypatch):
    monkeypatch.setattr(ingest, "UW_UNUSUAL_LIMIT", 1)
    ingest.ingest_uw_unusual_paged(Fake([[uw_row("A")], [uw_row("A")]]), store, D)   # server ignored `page`
    assert store.get_metric("UW_UNUSUAL", D, "contracts")["complete"] is False
    ingest.ingest_uw_unusual_paged(Fake([[uw_row(str(i))] for i in range(20)]), store, date(2026, 9, 23), max_pages=3)
    assert store.get_metric("UW_UNUSUAL", date(2026, 9, 23), "contracts")["complete"] is False


def _ctx(store):
    r = raw_alert(created_at="2026-09-22T15:00:00Z", option_chain=CHAIN)
    a = parse_alert(r)
    store.upsert_alerts([alert_to_row(a, r)])
    return lambda: build_context(store, a, AS_OF)


def test_uw_flagged_scores(store):
    ctx = _ctx(store)
    assert not uw_flagged(ctx()).available                                    # list not fetched
    store.put_metric("UW_UNUSUAL", D, "contracts", {"symbols": [CHAIN], "complete": False})
    c = uw_flagged(ctx())
    assert c.available and c.score == 1.0 and "uw_unusual" in c.tags          # present → flagged even if truncated
    store.put_metric("UW_UNUSUAL", D, "contracts", {"symbols": ["OTHER"], "complete": True})
    c = uw_flagged(ctx())
    assert c.available and c.score == 0.0
    store.put_metric("UW_UNUSUAL", D, "contracts", {"symbols": ["OTHER"], "complete": False})
    assert not uw_flagged(ctx()).available        # truncated list: absence is unknown, not a negative


def test_registered_backtestable_weight_zero():
    assert uw_flagged in ALL_CHECKS and "uw_flagged" in BACKTESTABLE
    assert CURRENT.version == "v0.6" and CURRENT.w["uw_flagged"] == 0.0
    assert abs(sum(CURRENT.w.values()) - 1) < 1e-9


def test_zero_weight_leaves_v05_scores_unchanged(store):
    ctx = _ctx(store)
    store.put_metric("UW_UNUSUAL", D, "contracts", {"symbols": [CHAIN], "complete": True})
    without = Weights("v0.5", {k: v for k, v in CURRENT.w.items() if k != "uw_flagged"})
    for w_with, w_without in ((CURRENT, without), (V0, V0)):
        a, b = evaluate(ctx(), w_with), evaluate(ctx(), w_without)
        assert (a.score, a.score_parity, a.label, a.coverage) == (b.score, b.score_parity, b.label, b.coverage)
