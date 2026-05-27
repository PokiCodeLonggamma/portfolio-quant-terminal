"""Phase 3 — FastAPI cache + admin endpoints + worker import tests."""
from __future__ import annotations

from datetime import datetime
from unittest.mock import patch

import fakeredis.aioredis
import pytest_asyncio
from fastapi.testclient import TestClient

from api.cache import set_client_for_tests
from api.main import app

client = TestClient(app)


# =============================================================================
# Shared fixture — inject fakeredis into the @cached decorator
# =============================================================================
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


# =============================================================================
# /api/admin/cache/*
# =============================================================================
async def test_admin_cache_stats():
    r = client.get("/api/admin/cache/stats")
    assert r.status_code == 200
    body = r.json()
    assert "redis" in body
    assert "keys" in body
    assert body["redis"] in ("up", "down")


async def test_admin_cache_invalidate_bad_payload():
    r = client.post("/api/admin/cache/invalidate", json={"not_prefix": 1})
    assert r.status_code == 400


async def test_admin_cache_invalidate_unknown_prefix_returns_zero(_fake_redis):
    r = client.post("/api/admin/cache/invalidate", json={"prefix": "no.such.prefix"})
    assert r.status_code == 200
    assert r.json() == {"prefix": "no.such.prefix", "deleted": 0}


async def test_admin_cache_flush_all_empty():
    r = client.post("/api/admin/cache/flush_all")
    assert r.status_code == 200
    assert r.json()["deleted"] == 0


# =============================================================================
# Cached endpoint hit/miss behaviour — /api/options/{ticker}/gex
# =============================================================================
async def test_gex_endpoint_is_cached_second_call_uses_cache(_fake_redis):
    """First call hits the service; second call (within TTL) returns cached body
    without re-calling the underlying compute (proven by patching the service).

    Uses httpx.AsyncClient + ASGITransport so the FastAPI request runs in the
    same event loop as the fakeredis fixture (TestClient spawns its own loop
    in a worker thread which breaks fakeredis.aioredis).
    """
    import httpx
    from src.services import OptionsService
    from src.services.schemas import GexSummary

    call_count = {"n": 0}

    def fake_compute(ticker: str, **_kw) -> GexSummary | None:
        call_count["n"] += 1
        return GexSummary(
            ticker=ticker,
            spot=100.0,
            gamma_flip=99.5, neg_gamma_lo=98.0, neg_gamma_hi=102.0,
            call_wall=105.0, put_wall=95.0,
            overall_pc_ratio=0.85,
            n_strikes=3,
            asof=datetime.utcnow(),
            buckets=[],
        )

    stub = OptionsService()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        with patch.object(stub, "get_gex_summary", side_effect=fake_compute), \
             patch("api.routes.options._service", stub):
            r1 = await ac.get("/api/options/SPY/gex")
            assert r1.status_code == 200
            assert call_count["n"] == 1

            r2 = await ac.get("/api/options/SPY/gex")
            assert r2.status_code == 200
            # Cache hit → no new compute
            assert call_count["n"] == 1

            # Same body
            assert r1.json() == r2.json()


# =============================================================================
# Worker module — import smoke test
# =============================================================================
def test_worker_module_imports():
    """The arq WorkerSettings should be importable without side effects."""
    from api.workers.worker import (
        WorkerSettings,
        publish_price_tick,
        refit_hmm,
        refresh_hot_chains,
        refresh_news,
    )
    assert WorkerSettings.functions
    # cron_jobs need at least one entry per job
    assert len(WorkerSettings.cron_jobs) >= 4
    # Functions are async
    for fn in (refresh_hot_chains, refresh_news, refit_hmm, publish_price_tick):
        import inspect
        assert inspect.iscoroutinefunction(fn)


# =============================================================================
# WebSocket — fallback path still works when no Redis-publishing worker runs
# =============================================================================
def test_ws_prices_still_works_with_fakeredis():
    """fakeredis has no publisher → handler should fall back to mock-pusher
    OR to redis pub/sub with no messages. Either way subscribe/ping must work."""
    import json as _json
    with client.websocket_connect("/ws/prices") as ws:
        ws.send_text(_json.dumps({"op": "subscribe", "tickers": ["ES"]}))
        msg = _json.loads(ws.receive_text())
        assert msg["type"] == "subscribed"
        assert "ES" in msg["tickers"]
