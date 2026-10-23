from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Callable

import httpx

BASE_URL = "https://api.unusualwhales.com"


class UWError(Exception):
    pass


class UWAuthError(UWError):
    pass


class UWBudgetExceeded(UWError):
    pass


class UWQuotaExhausted(UWBudgetExceeded):
    """UW's own daily quota is used up (429 with daily count ≥ limit) — stop until the 20:00 ET reset."""


class UWBlocked(UWError):
    """403 from Cloudflare / an egress proxy before UW auth — a network problem, not a bad key."""


_BLOCK_MARKERS = ("cloudflare", "1010", "access denied", "attention required", "bot", "host_not_allowed", "egress")


@dataclass
class Usage:
    daily_count: int | None = None
    daily_limit: int | None = None
    minute_remaining: int | None = None
    minute_reset_ms: int | None = None
    sent: int = 0          # requests this client sent (UW stopped sending x-uw-daily-req-count ~2026-10-07)


def _int(v: str | None) -> int | None:
    try:
        return int(v) if v is not None else None
    except ValueError:
        return None


def _scalar(v: Any) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    return str(v)


def _encode(params: dict[str, Any] | None) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    for k, v in (params or {}).items():
        if v is None:
            continue
        if isinstance(v, (list, tuple)):
            key = k if k.endswith("[]") else f"{k}[]"
            out.extend((key, _scalar(x)) for x in v)
        else:
            out.append((k, _scalar(v)))
    return out


class UWClient:
    def __init__(self, api_key: str, daily_cap: int = 38_000,
                 sleep: Callable[[float], None] = time.sleep, max_retries: int = 5,
                 http: httpx.Client | None = None):
        self._http = http or httpx.Client(base_url=BASE_URL, timeout=30.0)
        self._headers = {"Authorization": f"Bearer {api_key}",
                         "UW-CLIENT-API-ID": "100001", "Accept": "application/json"}
        self._daily_cap = daily_cap
        self._sleep = sleep
        self._max_retries = max_retries
        self.usage = Usage()

    def get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        if self.usage.daily_count is not None and self.usage.daily_count >= self._daily_cap:
            raise UWBudgetExceeded(f"daily cap {self._daily_cap} reached")
        if self.usage.minute_remaining is not None and self.usage.minute_remaining <= 2:
            self._sleep((self.usage.minute_reset_ms or 1000) / 1000)
            self.usage.minute_remaining = None
        query = _encode(params)
        delay = 1.0
        for _ in range(self._max_retries):
            try:
                r = self._http.get(path, params=query, headers=self._headers)
            except httpx.TransportError:
                self._sleep(delay)
                delay *= 2
                continue
            self.usage.sent += 1
            self._read_usage(r.headers)
            if r.status_code == 200:
                return r.json()
            if r.status_code == 429:
                if self._quota_gone():
                    raise UWQuotaExhausted(f"UW daily quota used ({self.usage.daily_count}/{self.usage.daily_limit})")
                self._sleep(max(self.usage.minute_reset_ms or 5000, 1000) / 1000)
                continue
            if r.status_code >= 500:
                self._sleep(delay)
                delay *= 2
                continue
            if r.status_code == 403 and "historic_data_access_missing" in r.text:
                raise UWError(f"403 {path}: outside this token's history window: {r.text[:200]}")
            if r.status_code == 403 and self._blocked(r):
                raise UWBlocked(f"403 {path}: blocked before UW auth (network/Cloudflare), not the key: {r.text[:200]}")
            if r.status_code in (401, 403):
                raise UWAuthError(f"{r.status_code} {path}: {r.text[:200]}")
            raise UWError(f"{r.status_code} {path}: {r.text[:200]}")
        raise UWError(f"retries exhausted for {path}")

    def _quota_gone(self) -> bool:
        u = self.usage
        return u.daily_count is not None and u.daily_limit is not None and u.daily_count >= u.daily_limit

    @staticmethod
    def _blocked(r: httpx.Response) -> bool:
        """Cloudflare / proxy pages are HTML or carry a deny header; UW's own JSON errors are never 'blocked'."""
        if r.headers.get("content-type", "").startswith("application/json"):
            return False
        text = (r.text[:2000] + " " + r.headers.get("x-deny-reason", "") + " " + r.headers.get("server", "")).lower()
        return any(m in text for m in _BLOCK_MARKERS)

    def _read_usage(self, h: httpx.Headers) -> None:
        for attr, name in (("daily_count", "x-uw-daily-req-count"),
                           ("daily_limit", "x-uw-token-req-limit"),
                           ("minute_remaining", "x-uw-req-per-minute-remaining"),
                           ("minute_reset_ms", "x-uw-req-per-minute-reset")):
            v = _int(h.get(name))
            if v is not None:
                setattr(self.usage, attr, v)
