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
# Phase 2 — Portfolio service
# =============================================================================
class Holding(BaseModel):
    """One row of the portfolio."""
    ticker: str
    isin: str | None = None
    name: str | None = None
    quantity: float
    price_eur: float | None = None
    market_value_eur: float
    currency: str = "EUR"
    theme: str | None = None
    region: str | None = None


class PortfolioSummary(BaseModel):
    """Top-level portfolio snapshot."""
    nav_eur: float
    n_positions: int
    holdings: list[Holding] = Field(default_factory=list)
    asof: datetime


# =============================================================================
# Phase 2 — Options service extensions (chain dump + vol surface)
# =============================================================================
class ChainContractOut(BaseModel):
    """JSON-safe option contract (subset of src.common.schemas.OptionContract)."""
    underlying: str
    symbol: str
    expiry: date
    strike: float
    right: Literal["C", "P"]
    bid: float | None = None
    ask: float | None = None
    mid: float | None = None
    iv: float | None = None
    delta: float | None = None
    gamma: float | None = None
    theta: float | None = None
    vega: float | None = None
    open_interest: int | None = None
    volume: int | None = None


class ChainDump(BaseModel):
    """Full chain dump for a ticker."""
    ticker: str
    spot: float | None
    n_contracts: int
    expiries: list[date]
    contracts: list[ChainContractOut] = Field(default_factory=list)
    asof: datetime


class VolSurfacePoint(BaseModel):
    """One (expiry, strike, right) sample of the IV surface."""
    expiry: date
    dte_days: int
    strike: float
    right: Literal["C", "P"]
    iv: float
    moneyness: float


class VolSurfaceDump(BaseModel):
    """Vol surface grid for the 3D viz."""
    ticker: str
    spot: float
    points: list[VolSurfacePoint] = Field(default_factory=list)
    asof: datetime


# =============================================================================
# Phase 2 — News service
# =============================================================================
class NewsItem(BaseModel):
    """One headline."""
    title: str
    url: str
    source: str
    published_at: datetime | None = None
    summary: str | None = None
    tickers: list[str] = Field(default_factory=list)
    sentiment: Literal["positive", "neutral", "negative"] | None = None


class NewsPulse(BaseModel):
    """Aggregated news feed."""
    items: list[NewsItem] = Field(default_factory=list)
    asof: datetime


# =============================================================================
# Phase 2 — Catalysts service
# =============================================================================
class CatalystOut(BaseModel):
    """Calendar event for the frontend."""
    event_id: str
    ticker: str | None
    category: Literal[
        "earnings", "fomc", "ecb", "opec", "cpi", "eia",
        "nrc", "launch", "contract_award", "dividend", "macro_other",
    ]
    title: str
    start: datetime
    end: datetime | None = None
    notes: str | None = None
    estimated_eps: float | None = None
    actual_eps: float | None = None


class CatalystFeed(BaseModel):
    horizon_days: int
    items: list[CatalystOut] = Field(default_factory=list)
    asof: datetime


# =============================================================================
# Phase 2 — Scanner services (universe + squeeze)
# =============================================================================
class UniverseScanRow(BaseModel):
    """One row of the options universe scanner (cf src.trading.universe_scanner)."""
    ticker: str
    spot: float
    chain_size: int
    atm_iv_pct: float | None
    delta25_call_strike: float | None
    delta25_call_premium_usd: float | None
    delta25_put_strike: float | None
    delta25_put_premium_usd: float | None
    gamma_flip: float | None
    neg_gamma_lo: float | None
    neg_gamma_hi: float | None
    put_call_ratio: float
    score: float
    notes: str
    asof: str


class SqueezeRow(BaseModel):
    """One row of the short-squeeze scanner."""
    ticker: str
    short_pct_float: float | None = None
    days_to_cover: float | None = None
    cost_to_borrow_pct: float | None = None
    utilization_pct: float | None = None
    on_sho_threshold: bool = False
    composite_score: float | None = None


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
