import httpx
import pytest
import respx

from whaleproof.core.data_layer.client import (
    BASE_URL, UWAuthError, UWBudgetExceeded, UWClient)

USAGE = {"x-uw-daily-req-count": "10", "x-uw-token-req-limit": "40000",
         "x-uw-req-per-minute-remaining": "100", "x-uw-req-per-minute-reset": "30000"}


@respx.mock
def test_sends_auth_headers_and_bracket_list_params():
    route = respx.get(f"{BASE_URL}/api/option-trades").mock(
        return_value=httpx.Response(200, json={"data": []}, headers=USAGE))
    c = UWClient("KEY", sleep=lambda s: None)
    c.get("/api/option-trades", {"tags": ["ask_side", "sweep"], "is_otm": True, "limit": 5, "skip": None})
    req = route.calls.last.request
    assert req.headers["Authorization"] == "Bearer KEY"
    assert req.headers["UW-CLIENT-API-ID"] == "100001"
    q = req.url.params
    assert q.get_list("tags[]") == ["ask_side", "sweep"]
    assert q["is_otm"] == "true" and q["limit"] == "5" and "skip" not in q


@respx.mock
def test_reads_usage_headers():
    respx.get(f"{BASE_URL}/x").mock(return_value=httpx.Response(200, json={}, headers=USAGE))
    c = UWClient("KEY", sleep=lambda s: None)
    c.get("/x")
    assert c.usage.daily_count == 10 and c.usage.minute_remaining == 100


@respx.mock
def test_retries_429_after_reset_then_succeeds():
    slept = []
    respx.get(f"{BASE_URL}/x").mock(side_effect=[
        httpx.Response(429, headers={"x-uw-req-per-minute-reset": "2000"}),
        httpx.Response(200, json={"ok": 1}, headers=USAGE)])
    c = UWClient("KEY", sleep=slept.append)
    assert c.get("/x") == {"ok": 1}
    assert slept == [2.0]


@respx.mock
def test_retries_5xx_with_backoff():
    slept = []
    respx.get(f"{BASE_URL}/x").mock(side_effect=[
        httpx.Response(502), httpx.Response(503), httpx.Response(200, json={}, headers=USAGE)])
    UWClient("KEY", sleep=slept.append).get("/x")
    assert slept == [1.0, 2.0]


@respx.mock
def test_401_raises_auth_error_without_retry():
    route = respx.get(f"{BASE_URL}/x").mock(return_value=httpx.Response(401, text="bad key"))
    with pytest.raises(UWAuthError):
        UWClient("KEY", sleep=lambda s: None).get("/x")
    assert route.call_count == 1


@respx.mock
def test_daily_cap_blocks_requests():
    respx.get(f"{BASE_URL}/x").mock(return_value=httpx.Response(
        200, json={}, headers={**USAGE, "x-uw-daily-req-count": "38000"}))
    c = UWClient("KEY", sleep=lambda s: None)
    c.get("/x")
    with pytest.raises(UWBudgetExceeded):
        c.get("/x")


@respx.mock
def test_waits_when_minute_budget_nearly_empty():
    slept = []
    respx.get(f"{BASE_URL}/x").mock(return_value=httpx.Response(
        200, json={}, headers={**USAGE, "x-uw-req-per-minute-remaining": "1",
                               "x-uw-req-per-minute-reset": "1500"}))
    c = UWClient("KEY", sleep=slept.append)
    c.get("/x")
    c.get("/x")
    assert slept == [1.5]


@respx.mock
def test_daily_quota_429_raises_quota_error_without_retry():
    from whaleproof.core.data_layer.client import UWQuotaExhausted
    slept = []
    route = respx.get(f"{BASE_URL}/x").mock(return_value=httpx.Response(
        429, headers={"x-uw-daily-req-count": "40000", "x-uw-token-req-limit": "40000"}))
    with pytest.raises(UWQuotaExhausted):
        UWClient("KEY", sleep=slept.append).get("/x")
    assert route.call_count == 1 and slept == []


@respx.mock
def test_cloudflare_403_is_blocked_not_auth():
    from whaleproof.core.data_layer.client import UWBlocked
    respx.get(f"{BASE_URL}/x").mock(return_value=httpx.Response(
        403, text="<html>Attention Required! | Cloudflare error code 1010</html>"))
    with pytest.raises(UWBlocked) as e:
        UWClient("KEY", sleep=lambda s: None).get("/x")
    assert not isinstance(e.value, UWAuthError)


@respx.mock
def test_plain_403_is_still_auth_error():
    respx.get(f"{BASE_URL}/x").mock(return_value=httpx.Response(403, json={"message": "plan expired"}))
    with pytest.raises(UWAuthError):
        UWClient("KEY", sleep=lambda s: None).get("/x")


@respx.mock
def test_history_limit_403_is_plain_error_not_blocked_or_auth():
    from whaleproof.core.data_layer.client import UWBlocked, UWError
    respx.get(f"{BASE_URL}/x").mock(return_value=httpx.Response(403, json={
        "code": "historic_data_access_missing", "message": "The earliest date currently available to this token is 2023-10-31"}))
    with pytest.raises(UWError) as e:
        UWClient("KEY", sleep=lambda s: None).get("/x")
    assert not isinstance(e.value, (UWBlocked, UWAuthError)) and "2023-10-31" in str(e.value)


@respx.mock
def test_counts_own_requests_when_uw_stops_sending_daily_count():
    # UW dropped x-uw-daily-req-count around 2026-10-07; the client keeps its own tally of requests sent
    respx.get(f"{BASE_URL}/x").mock(side_effect=[
        httpx.Response(502), httpx.Response(200, json={}, headers={"x-uw-req-per-minute-remaining": "1000000"}),
        httpx.Response(200, json={})])
    c = UWClient("KEY", sleep=lambda s: None)
    c.get("/x")
    c.get("/x")
    assert c.usage.daily_count is None and c.usage.sent == 3
