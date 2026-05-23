"""Risk engine — vectorised, EUR-normalised.

Inputs are expected to come from `src.portfolio.analytics` (already in EUR).

Provides:
  - risk_metrics: vol / Sharpe / Sortino / max drawdown / VaR / CVaR
  - parametric_var / historical_var
  - marginal contribution to VaR per position
  - monte_carlo_pnl simulation
  - stress_scenarios: apply parametric shocks to a portfolio
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from src.utils.config import get_config
from src.utils.logging import get_logger

log = get_logger(__name__)


@dataclass
class RiskMetrics:
    ann_return: float
    ann_vol: float
    sharpe: float
    sortino: float
    max_drawdown: float
    var_95_daily: float
    cvar_95_daily: float
    sample_size: int

    def as_dict(self) -> dict[str, float]:
        return {
            "ann_return": self.ann_return,
            "ann_vol": self.ann_vol,
            "sharpe": self.sharpe,
            "sortino": self.sortino,
            "max_drawdown": self.max_drawdown,
            "var_95_daily": self.var_95_daily,
            "cvar_95_daily": self.cvar_95_daily,
            "sample_size": self.sample_size,
        }


def risk_metrics(returns: pd.Series, rf_annual: float | None = None) -> RiskMetrics:
    """Compute the standard risk metrics on a daily-return series."""
    cfg = get_config()
    if rf_annual is None:
        rf_annual = float(cfg.settings.get("risk", {}).get("rf_annual", 0.0))
    trading_days = int(cfg.settings.get("risk", {}).get("trading_days", 252))

    r = returns.dropna().astype(float)
    n = len(r)
    if n < 5:
        return RiskMetrics(0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, n)

    mean_daily = float(r.mean())
    vol_daily = float(r.std(ddof=1))
    ann_ret = (mean_daily - rf_annual / trading_days) * trading_days
    ann_vol = vol_daily * np.sqrt(trading_days)
    sharpe = ann_ret / ann_vol if ann_vol > 0 else 0.0

    downside = r[r < 0]
    ann_down = float(downside.std(ddof=1) * np.sqrt(trading_days)) if len(downside) > 1 else 0.0
    sortino = ann_ret / ann_down if ann_down > 0 else 0.0

    nav = (1.0 + r).cumprod()
    peak = nav.cummax()
    dd = float((nav / peak - 1.0).min())

    q = float(np.quantile(r, 0.05))
    cvar = float(r[r <= q].mean()) if (r <= q).any() else q

    return RiskMetrics(
        ann_return=ann_ret,
        ann_vol=ann_vol,
        sharpe=sharpe,
        sortino=sortino,
        max_drawdown=dd,
        var_95_daily=q,
        cvar_95_daily=cvar,
        sample_size=n,
    )


def parametric_var(returns: pd.Series, alpha: float = 0.95) -> float:
    """Gaussian VaR (z * sigma - mu) on daily returns. Negative = loss."""
    r = returns.dropna()
    if len(r) < 5:
        return 0.0
    from scipy.stats import norm
    z = norm.ppf(1.0 - alpha)
    return float(r.mean() + z * r.std(ddof=1))


def historical_var(returns: pd.Series, alpha: float = 0.95) -> float:
    r = returns.dropna()
    if len(r) < 5:
        return 0.0
    return float(np.quantile(r, 1.0 - alpha))


def marginal_var(per_position_returns: pd.DataFrame, weights: pd.Series, alpha: float = 0.95) -> pd.Series:
    """Marginal VaR per position: d VaR / d w_i ≈ rho_i * sigma_i * VaR / sigma_p."""
    aligned = per_position_returns.dropna(how="any")
    w = weights.reindex(aligned.columns).fillna(0.0)
    if w.sum() == 0 or aligned.empty:
        return pd.Series(0.0, index=aligned.columns)
    port_ret = aligned.dot(w)
    sigma_p = port_ret.std(ddof=1)
    if sigma_p == 0:
        return pd.Series(0.0, index=aligned.columns)
    cov = aligned.cov().values
    marginal = (cov @ w.values) / sigma_p
    var_p = parametric_var(port_ret, alpha=alpha)
    contrib = pd.Series(marginal * w.values, index=aligned.columns) * (var_p / sigma_p if sigma_p else 0)
    contrib.name = f"marginal_var_{int(alpha * 100)}"
    return contrib


def monte_carlo_pnl(
    per_position_returns: pd.DataFrame,
    weights: pd.Series,
    horizon_days: int = 5,
    n_paths: int | None = None,
    seed: int = 42,
) -> pd.Series:
    """Multivariate-normal MC over the daily return covariance, returns horizon-cumulative PnL distribution."""
    cfg = get_config()
    if n_paths is None:
        n_paths = int(cfg.settings.get("risk", {}).get("monte_carlo_paths", 5000))
    aligned = per_position_returns.dropna(how="any")
    if aligned.empty:
        return pd.Series(dtype=float)
    w = weights.reindex(aligned.columns).fillna(0.0).values
    mu = aligned.mean().values
    cov = aligned.cov().values
    rng = np.random.default_rng(seed)
    # Daily MV-normal draws, summed across horizon_days
    L = np.linalg.cholesky(cov + 1e-12 * np.eye(len(mu)))
    daily = mu + (rng.standard_normal((n_paths, horizon_days, len(mu))) @ L.T)
    portfolio_daily = daily @ w
    horizon_ret = portfolio_daily.sum(axis=1)  # log-style additive approx
    return pd.Series(horizon_ret, name=f"mc_pnl_{horizon_days}d")


def stress_scenarios(per_position_returns: pd.DataFrame, weights: pd.Series,
                     shocks: dict[str, dict[str, float]]) -> pd.DataFrame:
    """Apply named shocks to specific tickers, evaluate impact at portfolio level.

    `shocks` = {"scenario_name": {"TICKER_OR_UNIVERSE_KEY": -0.30, ...}}

    For tickers not listed in a scenario, a beta-zero shock is assumed (0%).
    Returns a tidy DataFrame (scenario, portfolio_pct).
    """
    rows: list[dict[str, float | str]] = []
    w = weights.reindex(per_position_returns.columns).fillna(0.0)
    for name, mapping in shocks.items():
        shock_vec = pd.Series(0.0, index=w.index)
        for ticker, pct in mapping.items():
            if ticker in shock_vec.index:
                shock_vec[ticker] = pct
        portfolio_shock = float((shock_vec * w).sum())
        rows.append({"scenario": name, "portfolio_pct": portfolio_shock})
    return pd.DataFrame(rows)
