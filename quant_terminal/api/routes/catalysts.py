"""Catalysts endpoints (Phase 2)."""
from __future__ import annotations

from fastapi import APIRouter, Query

from src.services import CatalystsService
from src.services.schemas import CatalystFeed

router = APIRouter(prefix="/api/catalysts", tags=["catalysts"])

_service = CatalystsService()


@router.get("/upcoming", response_model=CatalystFeed)
async def get_upcoming(
    tickers: str | None = Query(
        None,
        description="Comma-separated tickers. Defaults to a curated watchlist.",
    ),
    horizon_days: int = Query(30, ge=1, le=180),
) -> CatalystFeed:
    parsed_tickers = (
        [t.strip().upper() for t in tickers.split(",") if t.strip()]
        if tickers else None
    )
    return _service.get_upcoming(
        tickers=parsed_tickers,
        horizon_days=horizon_days,
    )
