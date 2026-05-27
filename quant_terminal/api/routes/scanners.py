"""Scanner endpoints (Phase 2) — universe (Δ-25) + short-squeeze."""
from __future__ import annotations

from fastapi import APIRouter, Query

from src.services import ScannerService
from src.services.schemas import SqueezeRow, UniverseScanRow

router = APIRouter(prefix="/api/scanners", tags=["scanners"])

_service = ScannerService()


@router.get("/universe", response_model=list[UniverseScanRow])
async def scan_universe_endpoint(
    universe: str | None = Query(
        None,
        description="Comma-separated tickers. Defaults to the curated DEFAULT_UNIVERSE.",
    ),
) -> list[UniverseScanRow]:
    parsed = (
        [t.strip().upper() for t in universe.split(",") if t.strip()]
        if universe else None
    )
    return _service.scan_options_universe(universe=parsed)


@router.get("/squeeze", response_model=list[SqueezeRow])
async def scan_squeeze_endpoint(
    limit: int = Query(20, ge=1, le=100),
) -> list[SqueezeRow]:
    return _service.get_squeeze_top(limit=limit)
