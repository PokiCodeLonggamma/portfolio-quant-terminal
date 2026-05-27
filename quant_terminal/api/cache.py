"""Redis cache decorator for FastAPI handlers (Phase 3 of portage).

Usage::

    from api.cache import cached

    @router.get("/foo/{tk}", response_model=Foo)
    @cached(ttl_seconds=60)
    async def get_foo(tk: str) -> Foo:
        return _service.compute(tk)

Behaviour
---------
- Cache HIT  → return the deserialised Pydantic model directly
- Cache MISS → call the wrapped function, serialise its return value, SETEX in Redis
- Redis down → log + fall through (the API stays available, just uncached)
- Non-Pydantic return values (dict, list[Pydantic], primitives) are also supported

Cache keys are namespaced ``qt:cache:<endpoint>:<param_hash>`` and built from
the function name + bound parameters via ``inspect.signature``. The hash is
deterministic across processes (SHA-1).
"""
from __future__ import annotations

import hashlib
import inspect
import json
import logging
from functools import wraps
from typing import Any, Callable

import redis.asyncio as aioredis
from pydantic import BaseModel

from api.deps import get_redis_url

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------
_REDIS_CLIENT: aioredis.Redis | None = None


def _client() -> aioredis.Redis:
    """Lazy-built shared Redis client. Reused across decorator invocations."""
    global _REDIS_CLIENT
    if _REDIS_CLIENT is None:
        _REDIS_CLIENT = aioredis.from_url(get_redis_url(), decode_responses=True)
    return _REDIS_CLIENT


def set_client_for_tests(client: aioredis.Redis | None) -> None:
    """Patch the cached client — used by tests to inject fakeredis."""
    global _REDIS_CLIENT
    _REDIS_CLIENT = client


def _hash_params(payload: dict) -> str:
    """SHA-1 of the JSON-serialised payload (sort keys for determinism)."""
    raw = json.dumps(payload, sort_keys=True, default=str)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]


def _build_key(prefix: str, fn: Callable, args: tuple, kwargs: dict) -> str:
    """Compose ``qt:cache:<endpoint>:<param_hash>``."""
    sig = inspect.signature(fn)
    try:
        bound = sig.bind_partial(*args, **kwargs)
        bound.apply_defaults()
        params = dict(bound.arguments)
    except TypeError:
        params = {**kwargs}
    return f"qt:cache:{prefix}:{_hash_params(params)}"


def _serialize(value: Any) -> str:
    """JSON-encode a Pydantic model, list of models, dict, or primitive."""
    if isinstance(value, BaseModel):
        return json.dumps({
            "__type": "pydantic",
            "model": value.__class__.__name__,
            "data": value.model_dump(mode="json"),
        }, default=str)
    if isinstance(value, list) and value and isinstance(value[0], BaseModel):
        return json.dumps({
            "__type": "pydantic_list",
            "model": value[0].__class__.__name__,
            "data": [v.model_dump(mode="json") for v in value],
        }, default=str)
    return json.dumps({"__type": "raw", "data": value}, default=str)


def _deserialize(raw: str, model_cls: type | None) -> Any:
    """Reverse of :func:`_serialize`. ``model_cls`` is the response_model."""
    payload = json.loads(raw)
    kind = payload.get("__type")
    data = payload.get("data")
    if kind == "pydantic" and model_cls and issubclass(model_cls, BaseModel):
        return model_cls.model_validate(data)
    if kind == "pydantic_list" and model_cls and issubclass(model_cls, BaseModel):
        return [model_cls.model_validate(d) for d in data]
    return data


# ---------------------------------------------------------------------------
# Public decorator
# ---------------------------------------------------------------------------
def cached(
    *,
    ttl_seconds: int = 60,
    prefix: str | None = None,
    model_cls: type | None = None,
) -> Callable:
    """Cache the wrapped async FastAPI handler in Redis for ``ttl_seconds``.

    Parameters
    ----------
    ttl_seconds
        Time-to-live in seconds. Use small values (30-300) for live data and
        longer ones (3600+) for compute-heavy results like HMM fits.
    prefix
        Optional override for the cache key prefix. Defaults to the wrapped
        function's qualified name.
    model_cls
        Pydantic model class to deserialise into on cache hit. If omitted,
        the cached payload is returned as plain dict/list/primitive.

    The decorator NEVER raises on Redis errors — it falls through to the
    wrapped function so the API stays available even if Redis is down.
    """
    def decorator(fn: Callable) -> Callable:
        nonlocal prefix
        key_prefix = prefix or fn.__qualname__

        @wraps(fn)
        async def wrapper(*args, **kwargs):
            key = _build_key(key_prefix, fn, args, kwargs)
            try:
                client = _client()
                hit = await client.get(key)
                if hit is not None:
                    log.debug("cache HIT %s", key)
                    try:
                        return _deserialize(hit, model_cls)
                    except Exception as exc:
                        log.warning("cache deserialize failed for %s: %s", key, exc)
            except Exception as exc:
                log.debug("cache lookup failed for %s: %s (degrading to no-cache)", key, exc)

            # Compute fresh
            result = await fn(*args, **kwargs)

            # Store back (best-effort, never raise)
            try:
                client = _client()
                await client.setex(key, ttl_seconds, _serialize(result))
                log.debug("cache MISS+SET %s ttl=%ss", key, ttl_seconds)
            except Exception as exc:
                log.debug("cache store failed for %s: %s", key, exc)

            return result

        wrapper.__cache_prefix__ = key_prefix  # type: ignore[attr-defined]
        wrapper.__cache_ttl__ = ttl_seconds  # type: ignore[attr-defined]
        return wrapper

    return decorator


# ---------------------------------------------------------------------------
# Cache management helpers (used by /api/admin/cache/* — optional)
# ---------------------------------------------------------------------------
async def invalidate_prefix(prefix: str) -> int:
    """Delete all keys matching ``qt:cache:{prefix}:*``.

    An empty ``prefix`` flushes the entire ``qt:cache:*`` namespace.
    Returns the count of deleted keys.
    """
    try:
        client = _client()
        pattern = "qt:cache:*" if not prefix else f"qt:cache:{prefix}:*"
        cursor = 0
        deleted = 0
        while True:
            cursor, keys = await client.scan(cursor=cursor, match=pattern, count=200)
            if keys:
                await client.delete(*keys)
                deleted += len(keys)
            if cursor == 0:
                break
        return deleted
    except Exception as exc:
        log.warning("invalidate_prefix(%s) failed: %s", prefix, exc)
        return 0


async def cache_stats() -> dict:
    """Return rough cache stats — count + memory."""
    try:
        client = _client()
        info = await client.info("memory")
        keys = await client.dbsize()
        return {
            "redis": "up",
            "keys": int(keys),
            "memory_human": info.get("used_memory_human", "n/a"),
        }
    except Exception:
        return {"redis": "down", "keys": 0, "memory_human": "n/a"}
