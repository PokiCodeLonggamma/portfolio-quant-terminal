"""Admin / cache management endpoints (Phase 3).

- GET  /api/admin/cache/stats        → Redis size + key count
- POST /api/admin/cache/invalidate   { "prefix": "opts.gex" } → flush by prefix
- POST /api/admin/cache/flush_all    → nuke the entire cache namespace

These endpoints are intentionally unauthenticated for now (single-user dev).
Phase 2 of P3 will gate them behind a JWT admin role.
"""
from __future__ import annotations

from fastapi import APIRouter, Body, HTTPException

from api.cache import cache_stats, invalidate_prefix

router = APIRouter(prefix="/api/admin/cache", tags=["admin"])


@router.get("/stats")
async def get_stats() -> dict:
    return await cache_stats()


@router.post("/invalidate")
async def post_invalidate(
    payload: dict = Body(..., examples=[{"prefix": "opts.gex"}]),
) -> dict:
    prefix = payload.get("prefix")
    if not prefix or not isinstance(prefix, str):
        raise HTTPException(status_code=400, detail="Body must be {'prefix': '...'}")
    n = await invalidate_prefix(prefix)
    return {"prefix": prefix, "deleted": n}


@router.post("/flush_all")
async def post_flush_all() -> dict:
    """Wipe every qt:cache:* key. Use with care."""
    n = await invalidate_prefix("")  # empty prefix → matches qt:cache:*
    return {"deleted": n}
