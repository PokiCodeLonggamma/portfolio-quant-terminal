"""Phase 2 — PortfolioService tests."""
from __future__ import annotations

import pandas as pd
import pytest

from src.portfolio.holdings import Portfolio
from src.services.portfolio_service import PortfolioService
from src.services.schemas import PortfolioSummary


def _stub_portfolio() -> Portfolio:
    """Build a minimal portfolio with 3 holdings."""
    df = pd.DataFrame([
        {"symbol": "ASTS", "name": "AST SpaceMobile", "quantity": 100,
         "value_eur": 5000.0, "currency": "USD"},
        {"symbol": "RKLB", "name": "Rocket Lab", "quantity": 50,
         "value_eur": 3000.0, "currency": "USD"},
        {"symbol": "GOOG", "name": "Alphabet", "quantity": 5,
         "value_eur": 2500.0, "currency": "USD"},
    ])
    return Portfolio(holdings=df)


@pytest.fixture
def service():
    return PortfolioService(portfolio_fetch_fn=_stub_portfolio)


@pytest.fixture
def empty_service():
    return PortfolioService(portfolio_fetch_fn=lambda: None)


# ---------------------------------------------------------------------------
# get_summary
# ---------------------------------------------------------------------------
def test_get_summary_returns_pydantic_with_3_holdings(service):
    out = service.get_summary()
    assert isinstance(out, PortfolioSummary)
    assert out.nav_eur == pytest.approx(10500.0)
    assert out.n_positions == 3
    tickers = {h.ticker for h in out.holdings}
    assert "ASTS" in tickers
    assert "RKLB" in tickers
    assert "GOOG" in tickers


def test_get_summary_none_when_no_portfolio(empty_service):
    assert empty_service.get_summary() is None


def test_portfolio_available_true(service):
    assert service.portfolio_available() is True


def test_portfolio_available_false(empty_service):
    assert empty_service.portfolio_available() is False


# ---------------------------------------------------------------------------
# Service contract
# ---------------------------------------------------------------------------
def test_portfolio_service_no_streamlit():
    import src.services.portfolio_service as mod
    with open(mod.__file__, encoding="utf-8") as f:
        content = f.read()
    assert "import streamlit" not in content
    assert "from streamlit" not in content
