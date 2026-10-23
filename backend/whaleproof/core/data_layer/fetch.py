from __future__ import annotations

import json
from typing import Any

from .store import Store


def cache_key(path: str, params: dict | None) -> str:
    return path + "?" + json.dumps(params or {}, sort_keys=True, default=str)


def cached_get(client, store: Store, path: str, params: dict | None = None,
               ttl_s: float | None = None) -> Any:
    """ttl_s=None → cache forever (use for past dates). Otherwise refetch when older than ttl_s."""
    key = cache_key(path, params)
    hit = store.cache_get(key, ttl_s)
    if hit is not None:
        return hit
    payload = client.get(path, params)
    store.cache_put(key, path, payload)
    return payload


def rows(payload: Any) -> list[dict]:
    if payload is None:
        return []
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        if "data" in payload:
            data = payload["data"]
            if data is None:
                return []
            return data if isinstance(data, list) else [data]
        return [payload]
    return []
