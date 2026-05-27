"""Phase 5a — /api/regime/macro endpoint tests."""
from __future__ import annotations

from unittest.mock import patch

import fakeredis.aioredis
import pytest_asyncio
from fastapi.testclient import TestClient

from api.cache import set_client_for_tests
from api.main import app
from src.services.macro_service import MacroService

client = TestClient(app)


@pytest_asyncio.fixture(autouse=True)
async def _fake_redis():
    fake = fakeredis.aioredis.FakeRedis(decode_responses=True)
    set_client_for_tests(fake)
    yield fake
    try:
        await fake.flushall()
        await fake.aclose()
    except Exception:
        pass
    set_client_for_tests(None)


def test_get_macro_returns_snapshot():
    stub = MacroService(fetch_fn=lambda: {
        "vix_level": 16.0, "vix_short": 15.0, "vix_long": 17.0,
        "dxy": 103.0, "us10y_yield": 4.1,
        "spy_close": 555.0, "spy_ma200": 530.0,
    })
    with patch("api.routes.macro._service", stub):
        r = client.get("/api/regime/macro")
    assert r.status_code == 200
    body = r.json()
    assert body["vix_level"] == 16.0
    assert body["vix_term_structure"] == "contango"
    assert body["dxy"] == 103.0
    assert body["spy_above_200d"] is True


def test_get_macro_handles_upstream_failure():
    stub = MacroService(fetch_fn=lambda: {
        "vix_level": None, "vix_short": None, "vix_long": None,
        "dxy": None, "us10y_yield": None,
        "spy_close": None, "spy_ma200": None,
    })
    with patch("api.routes.macro._service", stub):
        r = client.get("/api/regime/macro")
    # Service returns a snapshot with all None — endpoint always 200 (no upstream → empty)
    assert r.status_code == 200
    body = r.json()
    assert body["vix_level"] is None
