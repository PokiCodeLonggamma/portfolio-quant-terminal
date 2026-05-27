"""Phase 0 — FastAPI skeleton + meta endpoints tests."""
from __future__ import annotations

from fastapi.testclient import TestClient

from api.main import app

client = TestClient(app)


def test_health_endpoint_returns_ok():
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert "version" in body
    assert "redis" in body
    assert body["redis"] in {"up", "down"}


def test_root_endpoint_returns_service_metadata():
    r = client.get("/")
    assert r.status_code == 200
    body = r.json()
    assert body["service"] == "Quant Terminal API"
    assert "docs" in body
    assert "openapi" in body


def test_openapi_schema_published():
    r = client.get("/openapi.json")
    assert r.status_code == 200
    schema = r.json()
    assert schema["info"]["title"] == "Quant Terminal API"
    assert schema["info"]["version"]


def test_cors_headers_present():
    """A request with Origin=localhost:3000 (Next.js dev) gets the right CORS header."""
    r = client.get("/api/universe", headers={"Origin": "http://localhost:3000"})
    assert r.status_code == 200
    assert r.headers.get("access-control-allow-origin") == "http://localhost:3000"
