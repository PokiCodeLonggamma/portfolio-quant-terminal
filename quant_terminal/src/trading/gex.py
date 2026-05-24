"""Net Gamma Exposure (GEX) — dealer hedging pressure per strike.

Convention used here (standard dealer-positioning model)
--------------------------------------------------------
For each strike `K`, the **net** dealer gamma exposure in dollars per 1% move
of spot is:

    gex(K) = (gamma_call * OI_call - gamma_put * OI_put) * 100 * spot^2 * 0.01

Why this sign convention?
* Calls are typically **sold** by retail / **bought** by dealers — so OI_call
  generates *positive* gamma for the dealer book (they buy as spot rises).
* Puts are typically **bought** by retail / **sold** by dealers — so OI_put
  generates *negative* gamma for the dealer book.

The aggregate `total_gex` summed across all strikes is also returned. Negative
total → MMs are short gamma → they sell on the way down and buy on the way up,
amplifying directional moves (the regime users hunt for gamma-squeeze entries).

The **gamma flip strike** is the zero-crossing of cumulative GEX as a function
of spot — the price level at which dealer gamma flips from positive to
negative. Spot below the flip = the negative-gamma zone.

The brief specifies one-leg convention `Σ OI_call*γ - Σ OI_put*γ` times
`100 * spot²`; that is what's implemented (calls minus puts).
"""
from __future__ import annotations

from datetime import datetime

import numpy as np
import pandas as pd
from pydantic import BaseModel

from src.common.schemas import OptionContract, OptionRight
from src.utils.logging import get_logger

log = get_logger(__name__)

_CONTRACT_MULT = 100.0       # US equity options multiplier


# ---------------------------------------------------------------------------
# Pydantic payload
# ---------------------------------------------------------------------------
class GammaCurve(BaseModel):
    ticker: str
    asof: datetime
    spot: float
    flip_strike: float | None = None
    negative_zone_lo: float | None = None
    negative_zone_hi: float | None = None
    total_gex_usd: float = 0.0
    per_strike: list[dict] = []      # [{strike, net_gex_usd, call_gex_usd, put_gex_usd}]


# ---------------------------------------------------------------------------
# Core
# ---------------------------------------------------------------------------
def _contract_gex_usd(c: OptionContract, spot: float) -> float:
    """Per-contract dollar gamma exposure contribution (no OI scaling)."""
    if c.gamma is None or c.gamma <= 0:
        return 0.0
    return float(c.gamma) * _CONTRACT_MULT * spot * spot


def compute_gex(contracts: list[OptionContract], spot: float) -> pd.DataFrame:
    """Net GEX per strike.

    Returns a DataFrame with columns:
        strike, net_gex_usd, call_gex_usd, put_gex_usd, call_oi, put_oi.

    Sorted ascending by strike.
    """
    if not contracts or spot is None or spot <= 0:
        return pd.DataFrame(columns=[
            "strike", "net_gex_usd", "call_gex_usd", "put_gex_usd", "call_oi", "put_oi",
        ])

    rows: dict[float, dict[str, float]] = {}
    for c in contracts:
        if c.gamma is None or c.open_interest is None or c.open_interest <= 0:
            continue
        per = _contract_gex_usd(c, spot) * c.open_interest
        bucket = rows.setdefault(float(c.strike), {
            "call_gex_usd": 0.0, "put_gex_usd": 0.0,
            "call_oi": 0, "put_oi": 0,
        })
        if c.right == OptionRight.CALL:
            bucket["call_gex_usd"] += per
            bucket["call_oi"] += int(c.open_interest)
        else:
            bucket["put_gex_usd"] += per
            bucket["put_oi"] += int(c.open_interest)

    if not rows:
        return pd.DataFrame(columns=[
            "strike", "net_gex_usd", "call_gex_usd", "put_gex_usd", "call_oi", "put_oi",
        ])

    df = pd.DataFrame([
        {
            "strike": k,
            "net_gex_usd": v["call_gex_usd"] - v["put_gex_usd"],
            "call_gex_usd": v["call_gex_usd"],
            "put_gex_usd": v["put_gex_usd"],
            "call_oi": v["call_oi"],
            "put_oi": v["put_oi"],
        }
        for k, v in rows.items()
    ]).sort_values("strike").reset_index(drop=True)
    return df


def gamma_flip_strike(gex_df: pd.DataFrame) -> float | None:
    """First strike (ascending) where cumulative net GEX crosses zero.

    Returns None if no zero-crossing detected (all-positive or all-negative
    cumulative gamma regimes).
    """
    if gex_df is None or gex_df.empty:
        return None
    cum = gex_df["net_gex_usd"].cumsum().to_numpy()
    strikes = gex_df["strike"].to_numpy()
    if (cum >= 0).all() or (cum <= 0).all():
        return None
    for i in range(1, len(cum)):
        if cum[i - 1] * cum[i] <= 0:
            # Linear interp between adjacent strikes
            x0, x1 = strikes[i - 1], strikes[i]
            y0, y1 = cum[i - 1], cum[i]
            if y1 == y0:
                return float(x1)
            t = -y0 / (y1 - y0)
            return float(x0 + t * (x1 - x0))
    return None


def negative_gamma_zone(
    gex_df: pd.DataFrame, spot: float, pct: float = 0.05,
) -> tuple[float | None, float | None]:
    """Detect the [lo, hi] strike envelope around spot where net GEX < 0.

    `pct` is the +/- envelope around spot to scan (default ±5%).
    Returns (lo, hi) — None when no negative zone is detected.
    """
    if gex_df is None or gex_df.empty or spot is None or spot <= 0:
        return None, None
    lo_bound = spot * (1.0 - pct)
    hi_bound = spot * (1.0 + pct)
    sub = gex_df[(gex_df["strike"] >= lo_bound) & (gex_df["strike"] <= hi_bound)]
    neg = sub[sub["net_gex_usd"] < 0]
    if neg.empty:
        return None, None
    return float(neg["strike"].min()), float(neg["strike"].max())


def render_gex_payload(
    ticker: str, contracts: list[OptionContract], spot: float,
) -> GammaCurve:
    """One-shot helper returning the full `GammaCurve` payload."""
    df = compute_gex(contracts, spot)
    flip = gamma_flip_strike(df)
    lo, hi = negative_gamma_zone(df, spot)
    return GammaCurve(
        ticker=ticker,
        asof=datetime.utcnow(),
        spot=float(spot),
        flip_strike=flip,
        negative_zone_lo=lo,
        negative_zone_hi=hi,
        total_gex_usd=float(df["net_gex_usd"].sum()) if not df.empty else 0.0,
        per_strike=df.to_dict(orient="records"),
    )
