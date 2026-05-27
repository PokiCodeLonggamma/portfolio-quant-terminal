"""Macro snapshot endpoint — VIX + term + DXY + US10Y + SPY 200d."""
from __future__ import annotations

from fastapi import APIRouter

from api.cache import cached
from src.services import MacroService
from src.services.schemas import MacroRegimeSnapshot

router = APIRouter(prefix="/api/regime", tags=["regime"])
_service = MacroService()


@router.get("/macro", response_model=MacroRegimeSnapshot)
@cached(ttl_seconds=300, prefix="regime.macro", model_cls=MacroRegimeSnapshot)
async def get_macro() -> MacroRegimeSnapshot:
    return _service.get_snapshot()
