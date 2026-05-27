"""Cross-asset quotes endpoints (Phase 1 — wires CrossAssetService).

- POST /api/cross-asset/quotes  { "logicals": ["ES", "NQ", "CL"] }
- GET  /api/cross-asset/heatmap → 1d/5d % matrix across the universe
"""
from __future__ import annotations

from fastapi import APIRouter, Body, HTTPException

from api.cache import cached
from src.services import CrossAssetService
from src.services.schemas import HeatmapRow, QuoteBatch

router = APIRouter(prefix="/api/cross-asset", tags=["cross-asset"])

# Singleton — yfinance fetcher, cached by yfinance itself
_service = CrossAssetService()


@router.post("/quotes", response_model=QuoteBatch)
async def post_quotes_batch(
    payload: dict = Body(..., examples=[{"logicals": ["ES", "NQ", "CL"]}]),
) -> QuoteBatch:
    logicals = payload.get("logicals")
    if not isinstance(logicals, list):
        raise HTTPException(
            status_code=400,
            detail="Body must be {'logicals': ['ES', 'NQ', ...]}",
        )
    if len(logicals) > 100:
        raise HTTPException(
            status_code=400,
            detail="Max 100 logicals per request",
        )
    return _service.get_quotes_batch([str(lg) for lg in logicals])


@router.get("/heatmap", response_model=list[HeatmapRow])
@cached(ttl_seconds=300, prefix="xa.heatmap", model_cls=HeatmapRow)
async def get_heatmap() -> list[HeatmapRow]:
    return _service.get_heatmap_rows()
