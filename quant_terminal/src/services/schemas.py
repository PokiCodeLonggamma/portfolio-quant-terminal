"""Pydantic v2 schemas — service layer DTOs (Phase 1 of portage).

These are the contracts between the pure Python services (``src/services/``)
and any caller — FastAPI handlers, Streamlit dashboards, CLI scripts.

Rules:
- Only POD-ish types. No DataFrames in fields (convert at boundaries).
- ISO-format dates/datetimes for JSON round-trip.
- Optional fields default to ``None`` (never ``NaN``).
- Field names match the FastAPI route response names.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


# =============================================================================
# Cross-asset service
# =============================================================================
class Quote(BaseModel):
    """Live-ish quote for one contract."""
    model_config = ConfigDict(populate_by_name=True)

    logical: str
    last: float | None = None
    chg_1d_pct: float | None = Field(default=None, description="day-over-day change %")
    chg_5d_pct: float | None = None
    asof: datetime | None = None
    source: Literal["yfinance", "alpaca", "stub"] = "yfinance"


class QuoteBatch(BaseModel):
    """Bulk-resolved quotes."""
    quotes: list[Quote]
    requested: int
    resolved: int
    asof: datetime


class HeatmapRow(BaseModel):
    """One row of the cross-asset heatmap (sorted by 1d %)."""
    asset_class: str
    logical: str
    name: str
    chg_1d_pct: float | None
    chg_5d_pct: float | None


# =============================================================================
# Options service
# =============================================================================
class GreeksRollup(BaseModel):
    """Aggregate Greeks across a chain / book."""
    delta: float
    gamma: float
    theta: float
    vega: float
    rho: float | None = None
    n_positions: int = 0


class GexBucket(BaseModel):
    """One strike's gamma exposure."""
    strike: float
    call_gex: float
    put_gex: float
    net_gex: float


class GexSummary(BaseModel):
    """Top-level GEX dashboard data."""
    ticker: str
    spot: float
    gamma_flip: float | None
    neg_gamma_lo: float | None
    neg_gamma_hi: float | None
    call_wall: float | None
    put_wall: float | None
    overall_pc_ratio: float
    n_strikes: int
    asof: datetime
    buckets: list[GexBucket] = Field(default_factory=list)


class IVTermStructurePoint(BaseModel):
    expiry: date
    dte_days: int
    atm_iv_avg: float | None
    contango_proxy: float | None = None


class IVSurfacePoint(BaseModel):
    """One (expiry, strike) point of the vol surface."""
    expiry: date
    strike: float
    iv: float
    moneyness: float | None = None


# =============================================================================
# Regime service
# =============================================================================
class HMMRegime(BaseModel):
    """Result of fitting / reading an HMM regime model."""
    ticker: str
    current_label: str
    current_probs: dict[str, float] = Field(
        default_factory=dict,
        description="State → posterior probability mapping.",
    )
    n_states: int
    sample_size: int
    asof: datetime


class MacroRegimeSnapshot(BaseModel):
    """Cross-asset macro positioning snapshot."""
    vix_level: float | None = None
    vix_term_structure: Literal["contango", "backwardation", "flat"] | None = None
    dxy: float | None = None
    us10y_yield: float | None = None
    spy_above_200d: bool | None = None
    asof: datetime


# =============================================================================
# Meta — service-level errors / status
# =============================================================================
class ServiceError(BaseModel):
    """Wrap a service error in a structured form (FastAPI handlers re-raise as HTTPException)."""
    code: Literal[
        "not_found", "upstream_unavailable", "stale_data",
        "bad_request", "internal",
    ]
    message: str
    detail: dict | None = None
