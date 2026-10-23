"""Local-only request guard for the 127.0.0.1 API.

Binding to 127.0.0.1 keeps other machines out, but a web page open in the owner's browser can still reach it:
- DNS rebinding: a foreign name resolved to 127.0.0.1 → foreign Host (or X-Forwarded-Host via the Next proxy).
- Cross-site writes: a foreign page POSTing a "simple" request → foreign Origin.
Any port is allowed (UI :3100, API :8100, e2e :3199/:8199). Requests without Origin (curl, MCP, scripts) pass.
"""
from __future__ import annotations

from urllib.parse import urlsplit

from fastapi import FastAPI, Request
from fastapi.responses import PlainTextResponse

LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1", "testserver"}   # testserver = FastAPI TestClient
WRITES = {"POST", "PUT", "PATCH", "DELETE"}


def _hostname(host: str) -> str:
    return (urlsplit(f"//{host.strip()}").hostname or "").lower()


def _local_origin(origin: str) -> bool:
    u = urlsplit(origin)
    return u.scheme in ("http", "https") and (u.hostname or "").lower() in LOCAL_HOSTS


def add_local_guard(app: FastAPI) -> None:
    @app.middleware("http")
    async def local_only(request: Request, call_next):
        hosts = [request.headers.get("host", ""), *request.headers.get("x-forwarded-host", "").split(",")]
        if any(h.strip() and _hostname(h) not in LOCAL_HOSTS for h in hosts):
            return PlainTextResponse("forbidden host", status_code=403)
        origin = request.headers.get("origin")
        if request.method in WRITES and origin is not None and not _local_origin(origin):
            return PlainTextResponse("forbidden origin", status_code=403)
        return await call_next(request)
