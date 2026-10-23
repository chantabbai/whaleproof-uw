"""Local-only guard: blocks DNS-rebinding (foreign Host / X-Forwarded-Host) and cross-site writes (foreign Origin)."""
from fastapi import FastAPI
from fastapi.testclient import TestClient

from whaleproof.api.guard import add_local_guard


def _client() -> TestClient:
    app = FastAPI()
    add_local_guard(app)

    @app.get("/api/x")
    def read() -> dict:
        return {"ok": True}

    @app.post("/api/x")
    def write() -> dict:
        return {"ok": True}

    return TestClient(app)


def test_local_hosts_any_port_allowed():
    c = _client()
    for host in ("testserver", "127.0.0.1", "127.0.0.1:8100", "localhost:3199", "[::1]:8100"):
        assert c.get("/api/x", headers={"Host": host}).status_code == 200, host


def test_foreign_host_rejected():
    c = _client()
    assert c.get("/api/x", headers={"Host": "evil.test:8100"}).status_code == 403
    assert c.get("/api/x", headers={"Host": "127.0.0.1.evil.test"}).status_code == 403


def test_foreign_forwarded_host_rejected():
    """The Next proxy rewrites Host to the API; the browser's real Host arrives as X-Forwarded-Host."""
    c = _client()
    assert c.get("/api/x", headers={"X-Forwarded-Host": "evil.test:3100"}).status_code == 403
    assert c.get("/api/x", headers={"X-Forwarded-Host": "127.0.0.1:3100"}).status_code == 200


def test_cross_site_write_rejected_same_site_allowed():
    c = _client()
    assert c.post("/api/x", headers={"Origin": "http://evil.test"}).status_code == 403
    assert c.post("/api/x", headers={"Origin": "http://127.0.0.1:3100"}).status_code == 200
    assert c.post("/api/x", headers={"Origin": "http://localhost:3199"}).status_code == 200
    assert c.post("/api/x").status_code == 200                     # curl / MCP / scripts send no Origin
    assert c.post("/api/x", headers={"Origin": "null"}).status_code == 403


def test_create_app_is_guarded(tmp_path):
    from whaleproof.api.app import create_app
    app = create_app(tmp_path / "picks.jsonl", tmp_path / "db.sqlite", tmp_path / "x.log")
    c = TestClient(app)
    assert c.get("/api/picks", headers={"Host": "evil.test"}).status_code == 403
