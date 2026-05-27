"""Options endpoints (Phase 1 — wires OptionsService).

- GET /api/options/{ticker}/gex                → GexSummary
- GET /api/options/{ticker}/iv_term_structure  → list[IVTermStructurePoint]
- GET /api/options/{ticker}/available          → boolean
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from src.services import OptionsService
from src.services.schemas import GexSummary, IVTermStructurePoint

router = APIRouter(prefix="/api/options", tags=["options"])

# Singleton — production fetchers (Alpaca → yfinance fallback)
_service = OptionsService()


@router.get("/{ticker}/gex", response_model=GexSummary)
async def get_gex(ticker: str) -> GexSummary:
    summary = _service.get_gex_summary(ticker.upper())
    if summary is None:
        raise HTTPException(
            status_code=503,
            detail=(
                f"GEX unavailable for {ticker}: chain or spot fetch failed. "
                "Check upstream providers."
            ),
        )
    return summary


@router.get("/{ticker}/iv_term_structure", response_model=list[IVTermStructurePoint])
async def get_iv_term_structure(ticker: str) -> list[IVTermStructurePoint]:
    return _service.get_iv_term_structure(ticker.upper())


@router.get("/{ticker}/available")
async def get_chain_available(ticker: str) -> dict:
    return {
        "ticker": ticker.upper(),
        "available": _service.chain_available(ticker.upper()),
    }
