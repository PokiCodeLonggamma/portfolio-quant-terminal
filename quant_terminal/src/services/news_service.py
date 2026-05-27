"""News service — pulls headlines, scores sentiment, returns Pydantic DTOs.

Wraps :func:`src.news.realtime.refresh_realtime` (RSS aggregator + sentiment).
``news_fetch_fn`` is dependency-injected so tests stay offline.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable

import pandas as pd

from src.services.schemas import NewsItem, NewsPulse


def _default_fetcher(tickers: list[str], lookback_hours: int) -> pd.DataFrame:
    """Production fetcher — calls into src.news.realtime."""
    try:
        from src.news.realtime import refresh_realtime
        return refresh_realtime(
            tickers,
            lookback_hours=lookback_hours,
            dispatch=False,  # the service is read-only; alerts route owns dispatch
        )
    except Exception:
        return pd.DataFrame()


def _classify_sentiment(score: float | None) -> str | None:
    if score is None:
        return None
    if score >= 0.3:
        return "positive"
    if score <= -0.3:
        return "negative"
    return "neutral"


@dataclass
class NewsService:
    """Read-only news aggregation."""
    news_fetch_fn: Callable[[list[str], int], pd.DataFrame] = _default_fetcher
    default_tickers: list[str] = field(
        default_factory=lambda: ["SPY", "QQQ", "ES=F", "NQ=F", "VIX"]
    )

    # ------------------------------------------------------------------
    # latest
    # ------------------------------------------------------------------
    def get_latest(
        self,
        *,
        tickers: list[str] | None = None,
        lookback_hours: int = 6,
        limit: int = 50,
    ) -> NewsPulse:
        """Pull fresh headlines for ``tickers`` (or default watchlist)."""
        watchlist = tickers if tickers else list(self.default_tickers)
        df = self.news_fetch_fn(watchlist, lookback_hours)
        items: list[NewsItem] = []
        if df is not None and not df.empty:
            for _, row in df.head(limit).iterrows():
                ts = row.get("ts")
                if hasattr(ts, "to_pydatetime"):
                    ts = ts.to_pydatetime()
                elif isinstance(ts, str):
                    try:
                        ts = datetime.fromisoformat(ts)
                    except ValueError:
                        ts = None
                sent_score = row.get("sentiment")
                items.append(NewsItem(
                    title=str(row.get("title", "")),
                    url=str(row.get("link", "")),
                    source=str(row.get("source", "rss") or "rss"),
                    published_at=ts if isinstance(ts, datetime) else None,
                    tickers=[str(row.get("ticker"))] if row.get("ticker") else [],
                    sentiment=_classify_sentiment(
                        float(sent_score) if sent_score is not None and sent_score == sent_score  # noqa: PLR0124
                        else None
                    ),
                ))
        return NewsPulse(items=items, asof=datetime.utcnow())
