"""Portfolio endpoints (Phase 2)."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from src.services import PortfolioService
from src.services.schemas import PortfolioSummary

router = APIRouter(prefix="/api/portfolio", tags=["portfolio"])

_service = PortfolioService()


@router.get("/summary", response_model=PortfolioSummary)
async def get_summary() -> PortfolioSummary:
    summary = _service.get_summary()
    if summary is None:
        raise HTTPException(
            status_code=404,
            detail="No portfolio loaded. POST /api/portfolio/upload first.",
        )
    return summary


@router.get("/available")
async def get_available() -> dict:
    return {"available": _service.portfolio_available()}
