"""Shared FastAPI dependencies.

- ``get_redis_url``  — read REDIS_URL from env, default to local docker compose
- ``get_redis``      — async redis client (closed by lifespan in main.py)
- ``RedisDep``       — FastAPI dependency injector
"""
from __future__ import annotations

import os
from functools import lru_cache

import redis.asyncio as aioredis
from fastapi import Depends


@lru_cache(maxsize=1)
def get_redis_url() -> str:
    return os.getenv("REDIS_URL", "redis://localhost:6379/0")


async def get_redis() -> aioredis.Redis:
    """Per-request async redis client.

    In real handlers prefer reading ``request.app.state.redis`` (created once
    in the lifespan) — but this dependency is convenient for unit tests where
    no app is running.
    """
    return aioredis.from_url(get_redis_url(), decode_responses=True)


RedisDep = Depends(get_redis)
