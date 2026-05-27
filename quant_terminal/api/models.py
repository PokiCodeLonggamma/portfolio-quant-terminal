"""Pydantic v2 response models for the FastAPI layer.

These mirror the dataclasses from ``src/`` (notably ``src/universe/cross_asset``)
but are kept separate so the API surface evolves independently from the core.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# CDC §1 — Cross-asset universe
# ---------------------------------------------------------------------------
class ContractResponse(BaseModel):
    """Single contract from ``config/universe_cross_asset.yaml``."""
    logical: str = Field(..., description="Canonical key (e.g. 'ES')")
    name: str
    tier: Literal["standard", "mini", "micro"]
    root: str
    exchange: str
    asset_class: str
    yfinance: str = ""
    alpaca: str = ""
    tradingview: str = ""
    multiplier: float = 1.0
    currency: str = "USD"
    tick_size: float = 0.01
    tick_value: float = 0.01
    option_market: bool = False
    notes: str = ""


class AssetClassResponse(BaseModel):
    """One bucket of contracts (us_indices, energy, …)."""
    key: str
    label: str
    icon: str
    order: int
    contracts: list[ContractResponse]


class UniverseResponse(BaseModel):
    """Top-level cross-asset universe envelope."""
    asset_classes: list[AssetClassResponse]
    theme_to_drivers: dict[str, dict[str, list[str]]] = Field(default_factory=dict)


class SymbolResolveResponse(BaseModel):
    """Single-flavor symbol resolution result."""
    logical: str
    flavor: Literal["yfinance", "alpaca", "tradingview", "logical"]
    symbol: str


# ---------------------------------------------------------------------------
# Meta
# ---------------------------------------------------------------------------
class HealthResponse(BaseModel):
    status: Literal["ok"]
    version: str
    redis: Literal["up", "down"]
