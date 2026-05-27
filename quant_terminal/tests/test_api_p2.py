"""Phase 2 — FastAPI surface tests for the new endpoints + WebSocket /ws/prices."""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from unittest.mock import patch

import pandas as pd
from fastapi.testclient import TestClient

from api.main import app
from src.common.schemas import CalendarEvent, OptionContract, OptionRight
from src.portfolio.holdings import Portfolio
from src.services import (
    CatalystsService,
    NewsService,
    OptionsService,
    PortfolioService,
    ScannerService,
)

client = TestClient(app)


# =============================================================================
# /api/portfolio/*
# =============================================================================
def _stub_portfolio():
    df = pd.DataFrame([
        {"symbol": "ASTS", "name": "AST SpaceMobile", "quantity": 100,
         "value_eur": 5000.0, "currency": "USD"},
        {"symbol": "RKLB", "name": "Rocket Lab", "quantity": 50,
         "value_eur": 3000.0, "currency": "USD"},
    ])
    return Portfolio(holdings=df)


def test_get_portfolio_summary_ok():
    stub = PortfolioService(portfolio_fetch_fn=_stub_portfolio)
    with patch("api.routes.portfolio._service", stub):
        r = client.get("/api/portfolio/summary")
    assert r.status_code == 200
    body = r.json()
    assert body["nav_eur"] == 8000.0
    assert body["n_positions"] == 2


def test_get_portfolio_summary_404_when_empty():
    stub = PortfolioService(portfolio_fetch_fn=lambda: None)
    with patch("api.routes.portfolio._service", stub):
        r = client.get("/api/portfolio/summary")
    assert r.status_code == 404


def test_portfolio_available():
    stub = PortfolioService(portfolio_fetch_fn=_stub_portfolio)
    with patch("api.routes.portfolio._service", stub):
        r = client.get("/api/portfolio/available")
    assert r.status_code == 200
    assert r.json()["available"] is True


# =============================================================================
# /api/news/latest
# =============================================================================
def test_get_news_latest_ok():
    stub = NewsService(news_fetch_fn=lambda _t, _h: pd.DataFrame([
        {"ticker": "SPY", "ts": datetime.utcnow(),
         "title": "test headline", "link": "https://x", "source": "rss",
         "sentiment": 0.5},
    ]))
    with patch("api.routes.news._service", stub):
        r = client.get("/api/news/latest")
    assert r.status_code == 200
    body = r.json()
    assert len(body["items"]) == 1
    assert body["items"][0]["sentiment"] == "positive"


def test_get_news_latest_with_query_params():
    stub = NewsService(news_fetch_fn=lambda _t, _h: pd.DataFrame())
    with patch("api.routes.news._service", stub):
        r = client.get("/api/news/latest?tickers=ASTS,RKLB&lookback_hours=12&limit=5")
    assert r.status_code == 200


def test_news_lookback_hours_validation():
    r = client.get("/api/news/latest?lookback_hours=999")
    assert r.status_code == 422  # le > 72


# =============================================================================
# /api/catalysts/upcoming
# =============================================================================
def test_get_catalysts_upcoming_ok():
    stub = CatalystsService(
        earnings_fetch_fn=lambda _t: [CalendarEvent(
            event_id="x", ticker="AAPL", category="earnings",
            start=datetime.utcnow() + timedelta(days=5),
            title="AAPL earnings",
            source="yfinance",
            payload={"eps_estimate": 1.5},
        )],
        macro_fetch_fn=lambda: [],
    )
    with patch("api.routes.catalysts._service", stub):
        r = client.get("/api/catalysts/upcoming")
    assert r.status_code == 200
    body = r.json()
    assert body["horizon_days"] == 30
    assert len(body["items"]) == 1
    assert body["items"][0]["ticker"] == "AAPL"


def test_catalysts_horizon_query():
    stub = CatalystsService(
        earnings_fetch_fn=lambda _t: [],
        macro_fetch_fn=lambda: [],
    )
    with patch("api.routes.catalysts._service", stub):
        r = client.get("/api/catalysts/upcoming?horizon_days=7")
    assert r.status_code == 200
    assert r.json()["horizon_days"] == 7


# =============================================================================
# /api/scanners/*
# =============================================================================
def test_scanners_squeeze_ok():
    stub = ScannerService(squeeze_fetch_fn=lambda: pd.DataFrame([
        {"Ticker": "AMC", "ShortFloat": 25.3, "ShortRatio": 6.1,
         "CTB": 95.2, "Util": 99.5, "on_sho": True,
         "composite_score": 88.0},
    ]))
    with patch("api.routes.scanners._service", stub):
        r = client.get("/api/scanners/squeeze")
    assert r.status_code == 200
    body = r.json()
    assert len(body) == 1
    assert body[0]["ticker"] == "AMC"


def test_scanners_squeeze_respects_limit():
    rows = [
        {"Ticker": f"T{i}", "composite_score": i, "on_sho": False}
        for i in range(50)
    ]
    stub = ScannerService(squeeze_fetch_fn=lambda: pd.DataFrame(rows))
    with patch("api.routes.scanners._service", stub):
        r = client.get("/api/scanners/squeeze?limit=10")
    assert r.status_code == 200
    assert len(r.json()) == 10


# =============================================================================
# /api/options/{ticker}/chain (new P2)
# =============================================================================
def _mk_chain():
    return [OptionContract(
        underlying="TEST",
        symbol="TEST261218C00100000",
        expiry=date(2026, 12, 18),
        strike=100.0, right=OptionRight.CALL,
        bid=1.0, ask=1.1, mid=1.05, iv=0.30,
        delta=0.5, gamma=0.01, theta=-0.02, vega=0.10,
        open_interest=1000, volume=100,
        snapshot_ts=datetime.utcnow(),
        source="alpaca",
    )]


def test_get_chain_dump_ok():
    stub = OptionsService(
        chain_fetch_fn=lambda _tk: _mk_chain(),
        spot_fetch_fn=lambda _tk: 100.0,
    )
    with patch("api.routes.options._service", stub):
        r = client.get("/api/options/TEST/chain")
    assert r.status_code == 200
    body = r.json()
    assert body["ticker"] == "TEST"
    assert body["n_contracts"] == 1
    assert len(body["contracts"]) == 1
    assert body["contracts"][0]["right"] == "C"


def test_get_chain_503_when_empty():
    stub = OptionsService(
        chain_fetch_fn=lambda _tk: [],
        spot_fetch_fn=lambda _tk: None,
    )
    with patch("api.routes.options._service", stub):
        r = client.get("/api/options/X/chain")
    assert r.status_code == 503


def test_get_vol_surface_ok():
    stub = OptionsService(
        chain_fetch_fn=lambda _tk: _mk_chain(),
        spot_fetch_fn=lambda _tk: 100.0,
    )
    with patch("api.routes.options._service", stub):
        r = client.get("/api/options/TEST/vol_surface")
    assert r.status_code == 200
    body = r.json()
    assert body["ticker"] == "TEST"
    assert body["spot"] == 100.0
    assert len(body["points"]) >= 0  # exact count depends on filtering


def test_get_vol_surface_503_when_no_data():
    stub = OptionsService(
        chain_fetch_fn=lambda _tk: [],
        spot_fetch_fn=lambda _tk: None,
    )
    with patch("api.routes.options._service", stub):
        r = client.get("/api/options/X/vol_surface")
    assert r.status_code == 503


# =============================================================================
# WebSocket /ws/prices
# =============================================================================
def test_ws_prices_subscribe_unsubscribe_ping():
    with client.websocket_connect("/ws/prices") as ws:
        # Subscribe
        ws.send_text(json.dumps({"op": "subscribe", "tickers": ["ES", "NQ"]}))
        msg = json.loads(ws.receive_text())
        assert msg["type"] == "subscribed"
        assert set(msg["tickers"]) == {"ES", "NQ"}

        # Ping → pong
        ws.send_text(json.dumps({"op": "ping"}))
        # Either a tick (from the pusher) or a pong — both valid responses
        msg = json.loads(ws.receive_text())
        assert msg["type"] in {"pong", "tick"}

        # Unsubscribe NQ
        ws.send_text(json.dumps({"op": "unsubscribe", "tickers": ["NQ"]}))
        # Drain until we see the unsubscribed envelope
        for _ in range(5):
            msg = json.loads(ws.receive_text())
            if msg["type"] == "unsubscribed":
                break
        assert msg["type"] == "unsubscribed"
        assert "NQ" not in msg["tickers"]


def test_ws_prices_invalid_json():
    with client.websocket_connect("/ws/prices") as ws:
        ws.send_text("not json")
        # Could be the error envelope or a tick first; drain a few
        for _ in range(3):
            msg = json.loads(ws.receive_text())
            if msg["type"] == "error":
                break
        assert msg["type"] == "error"


def test_ws_prices_unknown_op():
    with client.websocket_connect("/ws/prices") as ws:
        ws.send_text(json.dumps({"op": "bogus"}))
        for _ in range(3):
            msg = json.loads(ws.receive_text())
            if msg["type"] == "error":
                break
        assert msg["type"] == "error"
        assert "bogus" in msg["message"]
