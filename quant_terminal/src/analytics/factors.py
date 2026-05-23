"""Factor model — multi-benchmark OLS betas + rolling betas.

Benchmarks are declared in `config/settings.yaml::factors`.
Factor prices go through the same EUR-normalisation pipeline as portfolio assets.
"""
from __future__ import annotations

from datetime import datetime

import numpy as np
import pandas as pd

from src.data.fx import series_to_eur
from src.data.loaders import _yfinance_history
from src.utils.config import get_config
from src.utils.logging import get_logger

log = get_logger(__name__)


def fetch_factor_prices(start: datetime, end: datetime) -> pd.DataFrame:
    """Load factor benchmarks (SPY, QQQ, URA, …) via yfinance, EUR-normalised."""
    cfg = get_config()
    factors_cfg: dict[str, str] = cfg.settings.get("factors", {})
    series: dict[str, pd.Series] = {}
    for label, ticker in factors_cfg.items():
        s = _yfinance_history(ticker, start, end)
        if s is None or s.empty:
            log.warning("factor %s (%s) returned empty", label, ticker)
            continue
        # Factor benchmarks are almost always USD; normalise to EUR.
        # VIX and DXY are unitless / index-like — pass-through.
        if label.lower() in {"vix", "dxy"}:
            series[label] = s
        else:
            series[label] = series_to_eur(s, "USD")
    if not series:
        return pd.DataFrame()
    return pd.concat(series.values(), axis=1, keys=series.keys()).sort_index()


def estimate_betas(portfolio_ret: pd.Series, factor_returns: pd.DataFrame) -> pd.Series:
    """Multi-factor OLS regression. Returns coefficient series (with `const`)."""
    import statsmodels.api as sm
    df = pd.concat([portfolio_ret.rename("y"), factor_returns], axis=1).dropna()
    if len(df) < 30:
        log.warning("estimate_betas: too few rows (%d)", len(df))
        return pd.Series(dtype=float)
    y = df["y"]
    X = sm.add_constant(df.drop(columns="y"))
    model = sm.OLS(y, X).fit()
    return model.params


def rolling_beta(portfolio_ret: pd.Series, benchmark_ret: pd.Series, window: int = 60) -> pd.Series:
    """Rolling univariate beta."""
    aligned = pd.concat([portfolio_ret, benchmark_ret], axis=1).dropna()
    if len(aligned) < window:
        return pd.Series(dtype=float, name=f"rolling_beta_{window}")
    y = aligned.iloc[:, 0]
    x = aligned.iloc[:, 1]
    cov = y.rolling(window).cov(x)
    var = x.rolling(window).var()
    return (cov / var).rename(f"rolling_beta_{window}")


def correlation_matrix(returns: pd.DataFrame, method: str = "pearson") -> pd.DataFrame:
    return returns.dropna(how="all").corr(method=method).replace([np.inf, -np.inf], np.nan).fillna(0.0)
