from datetime import date

from tests.conftest import raw_alert
from whaleproof.core.data_layer.models import (
    alert_to_row, num, parse_alert, parse_gex, row_to_alert)


def test_num_handles_strings_nulls_blanks():
    assert num("123.5") == 123.5 and num(7) == 7.0
    assert num(None) is None and num("") is None and num("abc") is None


def test_parse_alert_fields_and_session_date():
    a = parse_alert(raw_alert(created_at="2026-09-26T01:30:00Z"))  # 21:30 ET on Sep 25
    assert a.session_date == date(2026, 9, 25)
    assert a.kind == "call" and a.strike == 200.0 and a.dte == 21
    assert a.total_premium == 500_000 and a.ask_share == 0.9


def test_direction_rules():
    assert parse_alert(raw_alert()).direction == 1                       # call bought at ask
    assert parse_alert(raw_alert(type="put")).direction == -1            # put bought at ask
    sold = dict(total_ask_side_prem="40000", total_bid_side_prem="460000")
    assert parse_alert(raw_alert(**sold)).direction == -1                # call sold at bid
    assert parse_alert(raw_alert(type="put", **sold)).direction == 1     # put sold at bid
    mixed = dict(total_ask_side_prem="260000", total_bid_side_prem="240000")
    assert parse_alert(raw_alert(**mixed)).direction == 0
    assert parse_alert(raw_alert(has_multileg=True)).direction == 0


def test_otm_pct():
    assert round(parse_alert(raw_alert()).otm_pct, 4) == round(10 / 190, 4)
    assert round(parse_alert(raw_alert(type="put", strike="180")).otm_pct, 4) == round(10 / 190, 4)


def test_parse_alert_rejects_missing_core_fields():
    assert parse_alert(raw_alert(underlying_price=None)) is None
    assert parse_alert(raw_alert(total_premium="")) is None
    assert parse_alert(raw_alert(expiry=None)) is None


def test_missing_id_gets_stable_synthetic_id():
    r = raw_alert()
    r.pop("id")
    assert parse_alert(r).id == parse_alert(dict(r)).id != ""


def test_row_roundtrip():
    r = raw_alert()
    a = parse_alert(r)
    row = alert_to_row(a, r)
    assert row["session_date"] == "2026-09-25" and row_to_alert(row) == a


def test_parse_gex_strings_to_floats():
    g = parse_gex({"call_wall": "210", "put_wall": "180.5", "gamma_flip": None, "gamma_magnet": ""})
    assert g.call_wall == 210.0 and g.put_wall == 180.5 and g.gamma_flip is None and g.gamma_magnet is None
