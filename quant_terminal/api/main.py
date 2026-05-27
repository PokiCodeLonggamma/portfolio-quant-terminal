"""Quant Terminal — FastAPI entry point.

Run locally::

    uvicorn api.main:app --reload

Or via docker compose::

    docker compose -f docker-compose.dev.yml up

The Streamlit app (``app.py``) continues to work in parallel during the
Streamlit → Next.js migration. Each Streamlit tab is replaced by one (or more)
endpoints here + a Next.js page consuming them.
"""
from __future__ import annotations

from contextlib import asynccontextmanager

import redis.asyncio as aioredis
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.deps import get_redis_url
from api.routes import universe as universe_router

VERSION = "0.1.0"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: create the shared redis client. Shutdown: close it cleanly."""
    app.state.redis = aioredis.from_url(get_redis_url(), decode_responses=True)
    try:
        yield
    finally:
        try:
            await app.state.redis.aclose()
        except Exception:
            pass


app = FastAPI(
    title="Quant Terminal API",
    version=VERSION,
    description=(
        "Cross-asset cockpit — REST + WebSocket surface over the Python core. "
        "Phase 0 of the Streamlit → Next.js portage."
    ),
    lifespan=lifespan,
)

# CORS — open for localhost dev + Vercel deployments.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "https://quant-terminal.vercel.app",
    ],
    allow_origin_regex=r"https://quant-terminal-.*\.vercel\.app",  # PR previews
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------------
app.include_router(universe_router.router)


# ---------------------------------------------------------------------------
# Health & meta
# ---------------------------------------------------------------------------
@app.get("/health", tags=["meta"])
async def health() -> dict:
    """Liveness probe + redis ping.

    Returns:
        {"status": "ok", "version": "0.1.0", "redis": "up"|"down"}
    """
    redis_ok = False
    try:
        r = aioredis.from_url(get_redis_url(), decode_responses=True)
        try:
            pong = await r.ping()
            redis_ok = bool(pong)
        finally:
            await r.aclose()
    except Exception:
        redis_ok = False
    return {
        "status": "ok",
        "version": VERSION,
        "redis": "up" if redis_ok else "down",
    }


@app.get("/", tags=["meta"])
async def root() -> dict:
    """Hello world."""
    return {
        "service": "Quant Terminal API",
        "version": VERSION,
        "docs": "/docs",
        "openapi": "/openapi.json",
    }


def run() -> None:
    """Entry point for the ``quant-terminal-api`` console script."""
    import uvicorn
    uvicorn.run(
        "api.main:app",
        host="0.0.0.0",
        port=8000,
        reload=False,
    )
