"""Portfolio-level analytics — every value normalised to EUR.

Pipeline:
  1. Pull price series (listing ccy) via `src.data.loaders.download_prices`.
  2. Convert each series to EUR via `src.data.fx.series_to_eur` using the
     instrument's declared currency.
  3. Compute returns, weighted portfolio returns, cumulative PnL, drawdown.

Forex normalisation happens BEFORE any return is computed — this is the
contract: callers never have to think about FX.
"""
from __future__ import annotations

from datetime import datetime

import numpy as np
import pandas as pd

from src.data.fx import series_to_eur
from src.data.loaders import download_prices
from src.portfolio.holdings import Portfolio
from src.utils.config import get_config
from src.utils.logging import get_logger

log = get_logger(__name__)


def fetch_prices_eur(portfolio: Portfolio, start: datetime | str | None = None,
                    end: datetime | str | None = None) -> pd.DataFrame:
    """Return a wide DataFrame (date x universe_key) of prices in EUR."""
    keys = portfolio.universe_keys
    raw = download_prices(keys, start=start, end=end)
    if raw.empty:
        return raw
    cfg = get_config()
    eur_cols: dict[str, pd.Series] = {}
    for col in raw.columns:
        ccy = cfg.currency_of(col)
        eur_cols[col] = series_to_eur(raw[col].dropna(), ccy)
    out = pd.concat(eur_cols.values(), axis=1, keys=eur_cols.keys()).sort_index()
    out = out.ffill().dropna(how="all")
    return out


def returns(prices_eur: pd.DataFrame) -> pd.DataFrame:
    return prices_eur.pct_change().replace([np.inf, -np.inf], np.nan)


def portfolio_returns(portfolio: Portfolio, prices_eur: pd.DataFrame) -> pd.Series:
    """Weighted daily returns, using current EUR weights as a static approximation."""
    r = returns(prices_eur).dropna(how="all")
    w = portfolio.weights.reindex(r.columns).fillna(0.0)
    if w.sum() <= 0:
        return pd.Series(dtype=float)
    w = w / w.sum()
    return (r * w).sum(axis=1).rename("portfolio_return")


def cumulative_pnl(portfolio_ret: pd.Series, initial_value_eur: float) -> pd.Series:
    cum = (1.0 + portfolio_ret.fillna(0.0)).cumprod()
    return (cum - 1.0) * initial_value_eur


def drawdown(portfolio_ret: pd.Series) -> pd.Series:
    nav = (1.0 + portfolio_ret.fillna(0.0)).cumprod()
    peak = nav.cummax()
    return nav / peak - 1.0


def contribution_to_return(portfolio: Portfolio, prices_eur: pd.DataFrame) -> pd.Series:
    """Per-line contribution to the latest 1-day return (in EUR weight units)."""
    r = returns(prices_eur)
    if r.empty:
        return pd.Series(dtype=float)
    latest = r.iloc[-1]
    w = portfolio.weights.reindex(latest.index).fillna(0.0)
    contrib = (latest * w).sort_values(ascending=False)
    contrib.name = "contribution"
    return contrib
