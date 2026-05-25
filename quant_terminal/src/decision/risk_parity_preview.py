"""Volatility-target risk-parity preview weights.

Inverse-volatility weighting normalised so each position contributes the
same daily-vol budget (default 1%). This is a *preview* — actual rebalance
must respect risk-limit caps. We then normalise the sum to 1.0 so the
output is directly comparable to ``portfolio.weights``.

  w_i = (vol_target / sigma_i)
  w_i /= sum(w_i)

For positions with insufficient samples / zero variance, we drop them.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from src.utils.logging import get_logger

log = get_logger(__name__)


def risk_parity_weights(
    returns: pd.DataFrame,
    vol_target: float = 0.01,
    *,
    min_samples: int = 20,
    fill_missing: str = "drop",
) -> pd.Series:
    """Return vol-target inverse-vol weights summing to 1.0.

    Parameters
    ----------
    returns : pd.DataFrame
        Per-position daily returns. Columns = tickers.
    vol_target : float
        Per-position daily-vol target (default 1% = 0.01).
    min_samples : int
        Minimum non-null samples required to keep a ticker.
    fill_missing : str
        Currently only "drop" is supported.

    Returns
    -------
    pd.Series
        Index = tickers; values in [0, 1] summing to 1.0 (or empty if no
        valid columns).
    """
    if returns is None or returns.empty:
        return pd.Series(dtype="float64", name="risk_parity")

    sigmas: dict[str, float] = {}
    for col in returns.columns:
        s = returns[col].dropna()
        if len(s) < max(5, int(min_samples)):
            continue
        sigma = float(s.std(ddof=1))
        if not np.isfinite(sigma) or sigma <= 0:
            continue
        sigmas[col] = sigma

    if not sigmas:
        log.warning("risk_parity_weights: no valid columns")
        return pd.Series(dtype="float64", name="risk_parity")

    raw = pd.Series(
        {k: float(vol_target) / v for k, v in sigmas.items()},
        name="risk_parity",
    )
    total = raw.sum()
    if total <= 0:
        return pd.Series(dtype="float64", name="risk_parity")
    return (raw / total).rename("risk_parity")
