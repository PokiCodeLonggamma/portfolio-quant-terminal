from __future__ import annotations


from src.portfolio.analytics import (
    cumulative_pnl,
    drawdown,
    portfolio_returns,
    returns,
)
from src.portfolio.holdings import Portfolio, from_degiro


def test_portfolio_enriches_holdings(holdings_df):
    pf = Portfolio(holdings=holdings_df)
    # universe_key resolved from universe.yaml
    assert "GOOG" in pf.holdings["universe_key"].tolist()
    assert "theme" in pf.holdings.columns
    assert "region" in pf.holdings.columns


def test_total_value_weights_sum_to_one(holdings_df):
    pf = Portfolio(holdings=holdings_df)
    assert pf.total_value_eur == holdings_df["value_eur"].sum()
    assert abs(pf.weights.sum() - 1.0) < 1e-9


def test_by_groupbys(holdings_df):
    pf = Portfolio(holdings=holdings_df)
    assert pf.by_theme().sum() == pf.total_value_eur
    assert pf.by_region().sum() == pf.total_value_eur


def test_returns_pipeline(holdings_df, price_panel):
    pf = from_degiro(holdings_df)
    # Align price panel columns to portfolio universe keys
    panel = price_panel.copy()
    panel.columns = pf.universe_keys[: len(panel.columns)]
    # Sanity: per-asset returns are well-formed
    assert not returns(panel).empty
    port_ret = portfolio_returns(pf, panel)
    assert not port_ret.empty
    pnl = cumulative_pnl(port_ret, initial_value_eur=pf.total_value_eur)
    dd = drawdown(port_ret)
    assert pnl.index.equals(port_ret.index)
    assert dd.max() <= 0  # drawdown is always non-positive
