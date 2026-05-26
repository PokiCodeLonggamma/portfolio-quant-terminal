"""Composite gamma-squeeze score (0-100).

Sub-components (each clipped 0-100, then averaged with weights):
    A. **Negative GEX near spot** — total GEX < 0 inside spot ±5%. Magnitude
       scaled by |GEX_neg| / sum |GEX_in_zone|.        weight 0.4
    B. **Call volume burst** — today's call volume vs 20-day rolling mean of
       call volume. Score = max(0, ratio - 1) * 50, capped 100.   weight 0.3
    C. **OTM call OI delta +30% over 5D** — total OI on strikes > spot.
       Score = max(0, oi_pct_change / 0.30) * 100, capped 100.    weight 0.3

Total = 0.4*A + 0.3*B + 0.3*C, returned alongside the component breakdown.
"""
from __future__ import annotations

from typing import Iterable

import pandas as pd

from src.common.schemas import OptionContract, OptionRight
from src.trading.gex import compute_gex
from src.utils.logging import get_logger

log = get_logger(__name__)


def _component_negative_gex(
    contracts: list[OptionContract], spot: float, pct: float = 0.05,
) -> float:
    df = compute_gex(contracts, spot)
    if df.empty or spot is None or spot <= 0:
        return 0.0
    lo, hi = spot * (1 - pct), spot * (1 + pct)
    sub = df[(df["strike"] >= lo) & (df["strike"] <= hi)]
    if sub.empty:
        return 0.0
    total_abs = sub["net_gex_usd"].abs().sum()
    if total_abs <= 0:
        return 0.0
    neg = -sub.loc[sub["net_gex_usd"] < 0, "net_gex_usd"].sum()
    return float(max(0.0, min(100.0, (neg / total_abs) * 100.0)))


def _component_call_volume_burst(
    today_call_volume: float, mean_20d_call_volume: float | None,
) -> float:
    if mean_20d_call_volume is None or mean_20d_call_volume <= 0:
        return 0.0
    ratio = today_call_volume / mean_20d_call_volume
    return float(max(0.0, min(100.0, (ratio - 1.0) * 50.0)))


def _component_otm_call_oi_delta(
    contracts: list[OptionContract], oi_5d_ago_total: float | None, spot: float,
) -> float:
    if oi_5d_ago_total is None or oi_5d_ago_total <= 0 or spot is None or spot <= 0:
        return 0.0
    otm_call_oi = sum(
        (c.open_interest or 0)
        for c in contracts
        if c.right == OptionRight.CALL and c.strike > spot
    )
    pct_change = (otm_call_oi - oi_5d_ago_total) / oi_5d_ago_total
    return float(max(0.0, min(100.0, (pct_change / 0.30) * 100.0)))


def compute_squeeze_score(
    contracts: Iterable[OptionContract], *,
    spot: float,
    today_call_volume: float = 0.0,
    mean_20d_call_volume: float | None = None,
    oi_5d_ago_total: float | None = None,
    pct_zone: float = 0.05,
) -> dict:
    """Return ``{"score": float, "negative_gex_score": ..., "call_volume_score": ...,
    "otm_oi_score": ...}``. Score is in [0, 100].
    """
    contracts = list(contracts)
    a = _component_negative_gex(contracts, spot, pct=pct_zone)
    b = _component_call_volume_burst(today_call_volume, mean_20d_call_volume)
    c = _component_otm_call_oi_delta(contracts, oi_5d_ago_total, spot)
    total = 0.4 * a + 0.3 * b + 0.3 * c
    return {
        "score": float(round(total, 1)),
        "negative_gex_score": float(round(a, 1)),
        "call_volume_score": float(round(b, 1)),
        "otm_oi_score": float(round(c, 1)),
    }


def summary_table(
    payloads: dict[str, dict],
) -> pd.DataFrame:
    """Convert {ticker: payload} into a sortable DataFrame for dashboards."""
    if not payloads:
        return pd.DataFrame(columns=["ticker", "score", "negative_gex_score",
                                     "call_volume_score", "otm_oi_score"])
    rows = []
    for ticker, payload in payloads.items():
        rows.append({"ticker": ticker, **payload})
    return pd.DataFrame(rows).sort_values("score", ascending=False).reset_index(drop=True)
