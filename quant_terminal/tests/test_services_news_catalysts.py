"""Phase 2 — NewsService + CatalystsService tests."""
from __future__ import annotations

from datetime import datetime, timedelta

import pandas as pd
import pytest

from src.common.schemas import CalendarEvent
from src.services.catalysts_service import CatalystsService
from src.services.news_service import NewsService
from src.services.schemas import CatalystFeed, NewsPulse


# =============================================================================
# NewsService
# =============================================================================
def _stub_news_df(tickers: list[str], _hours: int) -> pd.DataFrame:
    return pd.DataFrame([
        {"ticker": "SPY", "ts": datetime.utcnow(),
         "title": "Stocks rip higher on rate cut bets",
         "link": "https://example.com/1", "source": "rss",
         "sentiment": 0.6},
        {"ticker": "QQQ", "ts": datetime.utcnow(),
         "title": "Nasdaq dumps on guidance cut",
         "link": "https://example.com/2", "source": "rss",
         "sentiment": -0.5},
        {"ticker": "VIX", "ts": datetime.utcnow(),
         "title": "Vol grinds lower",
         "link": "https://example.com/3", "source": "rss",
         "sentiment": 0.1},
    ])


@pytest.fixture
def news_service():
    return NewsService(news_fetch_fn=_stub_news_df)


def test_news_get_latest_returns_pulse(news_service):
    out = news_service.get_latest()
    assert isinstance(out, NewsPulse)
    assert len(out.items) == 3
    assert out.items[0].sentiment == "positive"
    assert out.items[1].sentiment == "negative"
    assert out.items[2].sentiment == "neutral"


def test_news_get_latest_respects_limit(news_service):
    out = news_service.get_latest(limit=2)
    assert len(out.items) == 2


def test_news_get_latest_empty_when_no_data():
    s = NewsService(news_fetch_fn=lambda _t, _h: pd.DataFrame())
    out = s.get_latest()
    assert out.items == []


def test_news_service_no_streamlit():
    import src.services.news_service as mod
    with open(mod.__file__, encoding="utf-8") as f:
        content = f.read()
    assert "import streamlit" not in content


# =============================================================================
# CatalystsService
# =============================================================================
def _stub_earnings(_tickers):
    return [
        CalendarEvent(
            event_id="evt_aapl",
            ticker="AAPL",
            category="earnings",
            start=datetime.utcnow() + timedelta(days=5),
            end=None,
            title="AAPL earnings",
            source="yfinance",
            payload={"eps_estimate": 1.45},
        )
    ]


def _stub_macro():
    return [
        CalendarEvent(
            event_id="evt_fomc",
            ticker=None,
            category="fomc",
            start=datetime.utcnow() + timedelta(days=15),
            end=None,
            title="FOMC rate decision",
            source="manual",
        )
    ]


@pytest.fixture
def catalysts_service():
    return CatalystsService(
        earnings_fetch_fn=_stub_earnings,
        macro_fetch_fn=_stub_macro,
    )


def test_catalysts_get_upcoming_returns_feed(catalysts_service):
    out = catalysts_service.get_upcoming()
    assert isinstance(out, CatalystFeed)
    assert out.horizon_days == 30
    assert len(out.items) == 2
    # Sorted by start ascending
    starts = [i.start for i in out.items]
    assert starts == sorted(starts)


def test_catalysts_horizon_filters_far_events():
    far_macro = [CalendarEvent(
        event_id="x", ticker=None, category="fomc",
        start=datetime.utcnow() + timedelta(days=400),
        end=None, title="Very far", source="manual",
    )]
    s = CatalystsService(
        earnings_fetch_fn=lambda _t: [],
        macro_fetch_fn=lambda: far_macro,
    )
    out = s.get_upcoming(horizon_days=30)
    assert out.items == []


def test_catalysts_earnings_payload_passthrough(catalysts_service):
    out = catalysts_service.get_upcoming()
    aapl = next((i for i in out.items if i.ticker == "AAPL"), None)
    assert aapl is not None
    assert aapl.estimated_eps == 1.45


def test_catalysts_service_no_streamlit():
    import src.services.catalysts_service as mod
    with open(mod.__file__, encoding="utf-8") as f:
        content = f.read()
    assert "import streamlit" not in content
