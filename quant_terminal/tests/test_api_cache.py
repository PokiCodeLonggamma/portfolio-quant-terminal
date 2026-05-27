"""Phase 3 — Redis @cached decorator tests (uses fakeredis)."""
from __future__ import annotations

import fakeredis.aioredis
import pytest
import pytest_asyncio
from pydantic import BaseModel

from api.cache import cached, invalidate_prefix, set_client_for_tests


class Item(BaseModel):
    name: str
    value: int


# Tests in this file are async to share a single event loop with the fakeredis
# client (avoids "bound to a different event loop" RuntimeError).
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


# ---------------------------------------------------------------------------
# Basic hit / miss
# ---------------------------------------------------------------------------
async def test_cache_miss_then_hit_returns_same_pydantic():
    counter = {"calls": 0}

    @cached(ttl_seconds=60, model_cls=Item)
    async def compute(tk: str) -> Item:
        counter["calls"] += 1
        return Item(name=tk, value=counter["calls"])

    a = await compute("ES")
    assert isinstance(a, Item)
    assert a.value == 1
    assert counter["calls"] == 1

    b = await compute("ES")
    assert b.value == 1
    assert counter["calls"] == 1
    assert a is not b
    assert a == b


async def test_cache_distinguishes_different_args():
    @cached(ttl_seconds=60, model_cls=Item)
    async def compute(tk: str, n: int = 1) -> Item:
        return Item(name=tk, value=n)

    a = await compute("ES", n=1)
    b = await compute("ES", n=2)
    c = await compute("NQ", n=1)
    assert a.value == 1 and b.value == 2 and c.name == "NQ"


# ---------------------------------------------------------------------------
# list[Pydantic] support
# ---------------------------------------------------------------------------
async def test_cache_pydantic_list():
    @cached(ttl_seconds=60, model_cls=Item)
    async def compute_list() -> list[Item]:
        return [Item(name=str(i), value=i) for i in range(3)]

    a = await compute_list()
    b = await compute_list()
    assert len(a) == 3 == len(b)
    assert all(isinstance(x, Item) for x in b)
    assert a == b


# ---------------------------------------------------------------------------
# Raw / dict support (no model_cls)
# ---------------------------------------------------------------------------
async def test_cache_dict_without_model():
    @cached(ttl_seconds=60)
    async def compute() -> dict:
        return {"status": "ok", "count": 42}

    a = await compute()
    b = await compute()
    assert a == {"status": "ok", "count": 42}
    assert b == a


# ---------------------------------------------------------------------------
# TTL expiry — simulate by flushing the key
# ---------------------------------------------------------------------------
async def test_cache_recomputes_after_flush(_fake_redis):
    counter = {"calls": 0}

    @cached(ttl_seconds=60, model_cls=Item)
    async def compute() -> Item:
        counter["calls"] += 1
        return Item(name="x", value=counter["calls"])

    a = await compute()
    assert a.value == 1
    await _fake_redis.flushall()
    b = await compute()
    assert b.value == 2  # cache miss → recomputed


# ---------------------------------------------------------------------------
# Graceful degradation when Redis is broken
# ---------------------------------------------------------------------------
async def test_cache_falls_through_when_redis_down():
    class BrokenRedis:
        async def get(self, key):
            raise ConnectionError("redis offline")

        async def setex(self, *a, **kw):
            raise ConnectionError("redis offline")

    set_client_for_tests(BrokenRedis())  # type: ignore[arg-type]
    counter = {"calls": 0}

    @cached(ttl_seconds=60, model_cls=Item)
    async def compute() -> Item:
        counter["calls"] += 1
        return Item(name="x", value=counter["calls"])

    a = await compute()
    b = await compute()
    assert a.value == 1
    assert b.value == 2
    assert counter["calls"] == 2


# ---------------------------------------------------------------------------
# invalidate_prefix
# ---------------------------------------------------------------------------
async def test_invalidate_prefix_clears_matching_keys():
    @cached(ttl_seconds=300, prefix="opts.gex", model_cls=Item)
    async def gex(tk: str) -> Item:
        return Item(name=tk, value=1)

    @cached(ttl_seconds=300, prefix="opts.chain", model_cls=Item)
    async def chain(tk: str) -> Item:
        return Item(name=tk, value=42)

    await gex("ES")
    await gex("NQ")
    await chain("ES")

    n = await invalidate_prefix("opts.gex")
    assert n == 2

    # opts.chain entries still present — a fresh call hits the cache
    counter = {"x": 0}

    @cached(ttl_seconds=300, prefix="opts.chain", model_cls=Item)
    async def chain2(tk: str) -> Item:
        counter["x"] += 1
        return Item(name=tk, value=999)

    out = await chain2("ES")
    assert counter["x"] == 0  # came from cache
    assert out.name == "ES" and out.value == 42


# ---------------------------------------------------------------------------
# Wrapped function metadata is preserved
# ---------------------------------------------------------------------------
async def test_cached_decorator_preserves_metadata():
    @cached(ttl_seconds=120, prefix="mine")
    async def my_handler():
        return {"x": 1}

    assert my_handler.__name__ == "my_handler"
    assert my_handler.__cache_prefix__ == "mine"  # type: ignore[attr-defined]
    assert my_handler.__cache_ttl__ == 120  # type: ignore[attr-defined]


# Mark the file as async-mode for pytest-asyncio (already auto-mode globally,
# but explicit is OK).
pytest.importorskip("pytest_asyncio")
