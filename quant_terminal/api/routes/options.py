"""Options endpoints — wires OptionsService.

Phase 1: gex, iv_term_structure, available.
Phase 2: chain dump, vol_surface.
Phase 3: @cached on GEX / chain / vol_surface / IV term (60-120s TTL).
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from api.cache import cached
from src.services import OptionsService
from src.services.schemas import (
    ChainDump,
    GexSummary,
    IVTermStructurePoint,
    VolSurfaceDump,
)

router = APIRouter(prefix="/api/options", tags=["options"])

# Singleton — production fetchers (Alpaca → yfinance fallback)
_service = OptionsService()


@router.get("/{ticker}/gex", response_model=GexSummary)
@cached(ttl_seconds=60, prefix="opts.gex", model_cls=GexSummary)
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
@cached(ttl_seconds=120, prefix="opts.iv_term", model_cls=IVTermStructurePoint)
async def get_iv_term_structure(ticker: str) -> list[IVTermStructurePoint]:
    return _service.get_iv_term_structure(ticker.upper())


@router.get("/{ticker}/available")
async def get_chain_available(ticker: str) -> dict:
    # Not cached — cheap boolean health check
    return {
        "ticker": ticker.upper(),
        "available": _service.chain_available(ticker.upper()),
    }


# --------------------------------------------------------------------------
# Phase 2 — chain dump + vol surface (cached in Phase 3)
# --------------------------------------------------------------------------
@router.get("/{ticker}/chain", response_model=ChainDump)
@cached(ttl_seconds=60, prefix="opts.chain", model_cls=ChainDump)
async def get_chain(
    ticker: str,
    max_contracts: int = Query(2000, ge=10, le=5000),
) -> ChainDump:
    dump = _service.get_chain_dump(ticker.upper(), max_contracts=max_contracts)
    if dump is None:
        raise HTTPException(
            status_code=503,
            detail=f"Chain unavailable for {ticker}.",
        )
    return dump


@router.get("/{ticker}/vol_surface", response_model=VolSurfaceDump)
@cached(ttl_seconds=120, prefix="opts.vol_surface", model_cls=VolSurfaceDump)
async def get_vol_surface(ticker: str) -> VolSurfaceDump:
    surface = _service.get_vol_surface_dump(ticker.upper())
    if surface is None:
        raise HTTPException(
            status_code=503,
            detail=f"Vol surface unavailable for {ticker}.",
        )
    return surface
