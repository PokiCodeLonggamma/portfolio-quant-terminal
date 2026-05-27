"""Regime endpoints — wires RegimeService.

Phase 1: HMM regime fit.
Phase 3: @cached (HMM fit is expensive — 1h TTL).
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from api.cache import cached
from src.services import RegimeService
from src.services.schemas import HMMRegime

router = APIRouter(prefix="/api/regime", tags=["regime"])

_service = RegimeService()


@router.get("/hmm/{ticker}", response_model=HMMRegime)
@cached(ttl_seconds=3600, prefix="regime.hmm", model_cls=HMMRegime)
async def get_hmm(
    ticker: str,
    n_states: int = Query(3, ge=2, le=5, description="Number of HMM states"),
) -> HMMRegime:
    out = _service.fit_hmm(ticker.upper(), n_states=n_states)
    if out is None:
        raise HTTPException(
            status_code=503,
            detail=(
                f"HMM unavailable for {ticker}: history fetch failed or "
                "insufficient observations (need ≥60)."
            ),
        )
    return out
