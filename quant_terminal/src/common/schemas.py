"""Cross-cluster typed schemas.

These models are the **only** type-level contract between the feature clusters
implemented in Phase 1. Every cluster imports the dataclasses it needs from
here; no cluster invents its own duplicate.

Pydantic v2 is used for cheap validation + JSON round-trip serialisation
(needed by `src.utils.cache` parquet adapters and the trading journal).
"""
from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Common enums
# ---------------------------------------------------------------------------
class Side(str, Enum):
    LONG = "LONG"
    SHORT = "SHORT"


class OptionRight(str, Enum):
    CALL = "C"
    PUT = "P"


# ---------------------------------------------------------------------------
# Trading / options
# ---------------------------------------------------------------------------
class OptionContract(BaseModel):
    underlying: str                      # universe_key (e.g. "ASTS")
    symbol: str                          # OCC symbol e.g. "ASTS250620C00040000"
    expiry: date
    strike: float                        # in underlying listing currency
    right: OptionRight
    bid: float | None = None
    ask: float | None = None
    last: float | None = None
    mid: float | None = None
    iv: float | None = None              # implied vol (annualised, decimal)
    delta: float | None = None
    gamma: float | None = None
    theta: float | None = None
    vega: float | None = None
    open_interest: int | None = None
    volume: int | None = None
    snapshot_ts: datetime
    source: Literal["alpaca", "yfinance"] = "alpaca"


class TradeTicket(BaseModel):
    ticker: str
    direction: Literal["LONG_CALL", "LONG_PUT"]
    expiry: date
    strike: float
    mid_eur: float
    debit_eur: float
    target_delta: float
    actual_delta: float
    breakeven: float
    rr_1_to_1: float                     # R/R if underlying moves 1*expected_move
    pct_of_net_ev: float
    refused_reasons: list[str] = Field(default_factory=list)
    contract_symbol: str
    snapshot_ts: datetime


class JournalTradeRow(BaseModel):
    trade_id: str
    opened_ts: datetime
    closed_ts: datetime | None = None
    ticker: str
    direction: Literal["LONG_CALL", "LONG_PUT"]
    contract_symbol: str
    strike: float
    expiry: date
    debit_eur: float
    qty: int
    exit_credit_eur: float | None = None
    pnl_eur: float | None = None
    notes: str | None = None
    catalyst_event_id: str | None = None


# ---------------------------------------------------------------------------
# Calendar / catalysts
# ---------------------------------------------------------------------------
class CalendarEvent(BaseModel):
    event_id: str                        # stable hash key
    ticker: str | None                   # universe_key, or None for macro
    category: Literal[
        "earnings", "fomc", "ecb", "opec", "cpi", "eia",
        "nrc", "launch", "contract_award", "dividend", "macro_other",
    ]
    start: datetime
    end: datetime | None = None
    title: str
    source: str                          # "yfinance", "fred", "manual", ...
    payload: dict = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Watchlists
# ---------------------------------------------------------------------------
class WatchlistEntry(BaseModel):
    universe_key: str
    sub_theme: str
    list_name: Literal["quantum", "photonics", "pre_ipo", "defense"]
    conviction: Literal["core", "high", "medium", "speculative", "private"]
    catalyst: str | None = None
    peers: list[str] = Field(default_factory=list)
    private: bool = False
    notes: str | None = None
    # Universe-metadata mini-block — lets the loader bypass Portfolio._enrich
    # for tickers that aren't in config/universe.yaml.
    yfinance: str | None = None
    alpaca: str | None = None
    isin: str | None = None
    name_hints: list[str] = Field(default_factory=list)
    currency: str = "USD"
    region: str = "US"
    theme: str | None = None
    asset_class: str = "equity"


# ---------------------------------------------------------------------------
# SEC filings
# ---------------------------------------------------------------------------
class FilingEvent(BaseModel):
    cik: str
    ticker: str | None                   # universe_key, may be None for HF filings
    form: Literal[
        "4", "13F-HR", "13D", "13G", "13D/A", "13G/A",
        "10-Q", "10-K", "S-3", "S-3/A", "424B5", "8-K",
    ]
    accession: str
    filed: date
    period_of_report: date | None = None
    url: str
    payload: dict = Field(default_factory=dict)  # form-specific parsed body
