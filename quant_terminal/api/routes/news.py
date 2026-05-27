"""News endpoints.

Phase 2: latest pulse.
Phase 3: @cached (5min TTL — RSS aggregation is heavy).
"""
from __future__ import annotations

from fastapi import APIRouter, Query

from api.cache import cached
from src.services import NewsService
from src.services.schemas import NewsPulse

router = APIRouter(prefix="/api/news", tags=["news"])

_service = NewsService()


@router.get("/latest", response_model=NewsPulse)
@cached(ttl_seconds=300, prefix="news.latest", model_cls=NewsPulse)
async def get_latest(
    tickers: str | None = Query(
        None,
        description="Comma-separated tickers. Defaults to SPY,QQQ,ES=F,NQ=F,VIX.",
    ),
    lookback_hours: int = Query(6, ge=1, le=72),
    limit: int = Query(50, ge=1, le=200),
) -> NewsPulse:
    parsed_tickers = (
        [t.strip().upper() for t in tickers.split(",") if t.strip()]
        if tickers else None
    )
    return _service.get_latest(
        tickers=parsed_tickers,
        lookback_hours=lookback_hours,
        limit=limit,
    )
