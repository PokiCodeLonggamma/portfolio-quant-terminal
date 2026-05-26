"""Simplified Almgren-Chriss slippage model.

We use a permanent-impact-free, square-root form:

    impact (fraction of price) = k * sigma_daily * sqrt(trade_usd / adv_usd)

Output is converted to basis points for display. ``k`` is the dimensionless
intensity (defaults to 0.1, calibrated to mid-cap US equities); ``sigma_daily``
is the asset's daily return volatility expressed as a decimal (0.02 = 2%/d).

All cash inputs share the same currency (USD or EUR) — this module is
unit-agnostic as long as ``adv`` and ``trade`` are in the same unit.
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

from src.utils.logging import get_logger

log = get_logger(__name__)


# ---------------------------------------------------------------------------
# Scalars
# ---------------------------------------------------------------------------
def expected_slippage_bps(
    adv_usd: float,
    trade_usd: float,
    vol_daily: float,
    k: float = 0.1,
) -> float:
    """Almgren-Chriss simplified slippage in basis points (one-side cost).

    Returns 0 if ``trade_usd`` is non-positive, ``inf`` if ``adv_usd`` is
    non-positive (no liquidity available).
    """
    if trade_usd is None or trade_usd <= 0:
        return 0.0
    if adv_usd is None or adv_usd <= 0 or not math.isfinite(adv_usd):
        return float("inf")
    if vol_daily is None or not math.isfinite(vol_daily) or vol_daily < 0:
        vol_daily = 0.0
    participation = trade_usd / adv_usd
    impact = k * vol_daily * math.sqrt(participation)
    return float(impact * 10_000.0)


def days_to_liquidate(
    position_usd: float,
    adv_usd: float,
    participation: float = 0.10,
) -> float:
    """How many trading days to fully exit ``position_usd`` at ``participation`` of ADV."""
    if position_usd is None or position_usd <= 0:
        return 0.0
    if adv_usd is None or adv_usd <= 0 or not math.isfinite(adv_usd):
        return float("inf")
    if participation is None or participation <= 0:
        return float("inf")
    return float(position_usd / (adv_usd * participation))


def slippage_cost(
    weight_usd: float,
    adv_usd: float,
    sigma_daily: float,
    *,
    participation: float = 0.10,
    eta: float = 0.142,
) -> float:
    """Total dollar slippage when liquidating ``weight_usd`` at ``participation`` of ADV.

    Multi-day execution: cost ≈ eta * sigma_daily * weight * sqrt(days).
    Returns a dollar amount in the same unit as the inputs.
    """
    if weight_usd is None or weight_usd <= 0:
        return 0.0
    days = days_to_liquidate(weight_usd, adv_usd, participation=participation)
    if not math.isfinite(days) or days <= 0:
        return float("inf")
    if sigma_daily is None or not math.isfinite(sigma_daily):
        sigma_daily = 0.0
    bps_cost = eta * sigma_daily * math.sqrt(days)
    return float(weight_usd * bps_cost)


# ---------------------------------------------------------------------------
# Vectorised batch (panel)
# ---------------------------------------------------------------------------
def slippage_panel(
    weights_usd: pd.Series,
    adv_usd: pd.Series,
    vol_daily: pd.Series,
    *,
    trade_size_pct: float = 0.01,
    k: float = 0.1,
) -> pd.DataFrame:
    """Vectorised slippage table for a portfolio.

    Returns columns: ticker, weight_usd, adv_usd, vol_daily, trade_usd,
    slippage_bps, days_to_liq_10pct, days_to_liq_20pct.
    """
    idx = weights_usd.index.union(adv_usd.index).union(vol_daily.index)
    w = weights_usd.reindex(idx).fillna(0.0).astype(float)
    a = adv_usd.reindex(idx).astype(float)
    s = vol_daily.reindex(idx).fillna(0.0).astype(float)

    portfolio_total = float(w.sum())
    trade_usd = portfolio_total * trade_size_pct

    a_safe = a.replace(0, np.nan)
    participation = (trade_usd / a_safe).clip(lower=0)
    impact = k * s * np.sqrt(participation)
    slippage_bps = (impact * 10_000.0).fillna(float("inf"))

    days_10 = (w / (a_safe * 0.10)).replace([np.inf, -np.inf], np.nan)
    days_20 = (w / (a_safe * 0.20)).replace([np.inf, -np.inf], np.nan)

    return pd.DataFrame({
        "ticker": idx,
        "weight_usd": w.values,
        "adv_usd": a.values,
        "vol_daily": s.values,
        "trade_usd": trade_usd,
        "slippage_bps": slippage_bps.values,
        "days_to_liq_10pct": days_10.values,
        "days_to_liq_20pct": days_20.values,
    })
