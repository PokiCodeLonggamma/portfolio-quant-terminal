"""Catalysts service — upcoming events (earnings, macro, FOMC, …).

Wraps :mod:`src.calendar_engine` providers into a unified DTO feed.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Callable

from src.common.schemas import CalendarEvent
from src.services.schemas import CatalystFeed, CatalystOut


def _default_earnings_fetcher(tickers: list[str]) -> list[CalendarEvent]:
    try:
        from src.calendar_engine.earnings import fetch_earnings
        return fetch_earnings(tickers)
    except Exception:
        return []


def _default_macro_fetcher() -> list[CalendarEvent]:
    """Pull FOMC + ECB + CPI + OPEC + EIA from the macro calendar config."""
    try:
        from src.calendar_engine.macro_events import load_macro_events
        return load_macro_events()
    except Exception:
        return []


@dataclass
class CatalystsService:
    """Aggregates earnings + macro events into one feed."""
    earnings_fetch_fn: Callable[[list[str]], list[CalendarEvent]] = _default_earnings_fetcher
    macro_fetch_fn: Callable[[], list[CalendarEvent]] = _default_macro_fetcher
    default_tickers: list[str] = field(
        default_factory=lambda: ["AAPL", "GOOG", "TSLA", "ASTS", "RKLB", "RDW", "IONQ", "CCJ"]
    )

    def get_upcoming(
        self,
        *,
        tickers: list[str] | None = None,
        horizon_days: int = 30,
    ) -> CatalystFeed:
        ticks = tickers if tickers else list(self.default_tickers)
        events: list[CalendarEvent] = []
        events.extend(self.earnings_fetch_fn(ticks))
        events.extend(self.macro_fetch_fn())

        today = date.today()
        cutoff = today + timedelta(days=horizon_days)
        items: list[CatalystOut] = []
        for e in events:
            if e.start.date() < today or e.start.date() > cutoff:
                continue
            items.append(CatalystOut(
                event_id=e.event_id,
                ticker=e.ticker,
                category=e.category,
                title=getattr(e, "title", f"{e.category}: {e.ticker or 'macro'}"),
                start=e.start,
                end=getattr(e, "end", None),
                notes=getattr(e, "notes", None) if hasattr(e, "notes") else None,
                estimated_eps=(e.payload or {}).get("eps_estimate") if hasattr(e, "payload") else None,
                actual_eps=(e.payload or {}).get("eps_actual") if hasattr(e, "payload") else None,
            ))
        items.sort(key=lambda x: x.start)
        return CatalystFeed(
            horizon_days=horizon_days,
            items=items,
            asof=datetime.utcnow(),
        )
