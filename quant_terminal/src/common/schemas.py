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


# ---------------------------------------------------------------------------
# SEC-derived analytics (Cluster 1)
# ---------------------------------------------------------------------------
class InsiderTransaction(BaseModel):
    """One row parsed from a Form 4 nonDerivativeTransaction element."""

    cik: str
    reporter_name: str
    reporter_role: str                   # "officer", "director", "10%owner"
    ticker: str | None
    transaction_date: date
    code: str                            # P, S, A, M, F, D, G ...
    shares: float
    price: float                         # USD per share (0 for grants)
    value_usd: float
    post_holding_shares: float
    accession: str


class Holding13F(BaseModel):
    """One row of an institutional 13F-HR information-table."""

    cik_fund: str
    fund_name: str
    cusip: str
    ticker: str | None
    name_of_issuer: str
    shares: int
    value_usd_000: int                   # SEC reports value in $thousands
    period_of_report: date


class DilutionAssessment(BaseModel):
    """Output of `assess_dilution(ticker)` — see dilution.py."""

    ticker: str
    atm_active: bool
    atm_remaining_usd: float | None = None
    convertibles_outstanding_usd: float | None = None
    shares_outstanding: float = 0.0
    dilution_score: int                  # 1 (low) -> 5 (severe)
    rationale: list[str] = Field(default_factory=list)


class RunwayAssessment(BaseModel):
    """Output of `assess_runway(ticker)` — see cash_runway.py."""

    ticker: str
    cash_eur: float
    quarterly_burn_eur: float            # signed positive = cash being consumed
    runway_quarters: float               # cash / quarterly_burn; inf if burn<=0
    period_end: date
    confidence: Literal["high", "medium", "low"] = "medium"


class ContractAward(BaseModel):
    """One government contract award (e.g. SAM.gov)."""

    awarded_to: str
    ticker: str | None
    award_id: str
    amount_usd: float
    awarded_on: date
    description: str
    agency: str


# ---------------------------------------------------------------------------
# Macro / régime (Cluster 2)
# ---------------------------------------------------------------------------
class RegimeSnapshot(BaseModel):
    """One row of the regime lattice — 2x2x2 (inflation x growth x policy)."""

    asof: date
    inflation: Literal["high", "low"]
    growth: Literal["high", "low"]
    policy: Literal["tight", "loose"]
    label: str                           # e.g. "Stagflation", "Goldilocks"


# ---------------------------------------------------------------------------
# Execution / OMS (Feature 1)
# ---------------------------------------------------------------------------
class OrderRequest(BaseModel):
    """Pre-submission order intent — produced by the UI ticket helpers."""

    ticker: str                          # underlying universe key
    qty: int                             # positive integer; side carries the sign
    side: Literal["BUY", "SELL"]
    asset_class: Literal["stock", "option"]
    order_type: Literal["market", "limit"]
    limit_price: float | None = None
    contract_symbol: str | None = None   # OCC option symbol when asset_class=="option"
    time_in_force: Literal["day", "gtc"] = "day"
    mode: Literal["paper", "live"] = "paper"
    notes: str | None = None
    requested_at: datetime = Field(default_factory=datetime.utcnow)


class OrderRecord(BaseModel):
    """Order lifecycle row — persisted in `data/execution/orders.parquet`."""

    order_id: str                        # local UUID
    broker_order_id: str | None = None
    status: Literal[
        "pending", "submitted", "filled", "partially_filled",
        "canceled", "rejected", "expired",
    ] = "pending"
    request: OrderRequest
    submitted_at: datetime | None = None
    filled_at: datetime | None = None
    filled_qty: int = 0
    avg_fill_price: float | None = None
    error: str | None = None
    audit_log: list[str] = Field(default_factory=list)


class BrokerAccount(BaseModel):
    """Snapshot of the trading account at a point in time."""

    mode: Literal["paper", "live"]
    cash_usd: float
    buying_power_usd: float
    portfolio_value_usd: float
    daytrade_count: int = 0
    pattern_day_trader: bool = False
    status: str = "ACTIVE"
    asof: datetime = Field(default_factory=datetime.utcnow)


class BrokerPosition(BaseModel):
    """One row of broker-side positions for reconciliation."""

    symbol: str
    asset_class: Literal["stock", "option", "crypto"]
    qty: float
    avg_entry_price: float
    market_value_usd: float
    unrealized_pl_usd: float
    side: Literal["LONG", "SHORT"] = "LONG"


# ---------------------------------------------------------------------------
# Snapshots (Feature 5a)
# ---------------------------------------------------------------------------
class SnapshotMeta(BaseModel):
    """Metadata of one daily portfolio snapshot."""

    asof: date
    net_value_eur: float
    gross_long_eur: float
    cash_eur: float
    n_positions: int
    n_open_options: int = 0
    fx_rates: dict[str, float] = Field(default_factory=dict)  # ccy -> EUR/ccy
    notes: str = ""
    created_at: datetime = Field(default_factory=datetime.utcnow)


# ---------------------------------------------------------------------------
# Tax lots (Feature 5b)
# ---------------------------------------------------------------------------
class TaxLot(BaseModel):
    """One acquisition lot. Cost basis stored in BOTH listing ccy + EUR."""

    lot_id: str
    ticker: str
    qty: float                           # remaining qty (initial - consumed)
    qty_initial: float                   # qty at acquisition
    acquired_at: date
    price_local: float                   # per-share price in listing ccy
    currency: str = "USD"
    fx_rate_eur: float = 1.0             # 1 EUR = fx_rate_eur units of `currency` at purchase
    cost_eur: float = 0.0                # qty_initial × price_local / fx_rate_eur (or × for EUR)
    account: str = "CTO"
    notes: str = ""


class RealisedTrade(BaseModel):
    """One sale event matched against one or more lots (FIFO)."""

    sale_id: str
    ticker: str
    sold_at: date
    qty_sold: float
    sale_price_local: float
    sale_currency: str = "USD"
    sale_fx_rate_eur: float = 1.0
    sale_proceeds_eur: float = 0.0
    consumed_lots: list[dict] = Field(default_factory=list)   # [{lot_id, qty, cost_eur}]
    cost_basis_eur: float = 0.0
    realised_pnl_eur: float = 0.0
    holding_period_days: int = 0
    account: str = "CTO"


# ---------------------------------------------------------------------------
# Event trading (Feature 6)
# ---------------------------------------------------------------------------
class EventSetup(BaseModel):
    """One candidate trade setup ranked by the pre-event wizard."""

    ticker: str
    event_id: str | None = None          # link to CalendarEvent.event_id
    event_category: str
    direction: Literal["LONG_CALL", "LONG_PUT", "STRADDLE"] = "LONG_CALL"
    iv_rank: float | None = None
    implied_move_pct: float | None = None
    historical_avg_move_pct: float | None = None
    target_delta: float = 0.25
    strike: float | None = None
    expiry: date | None = None
    debit_usd: float | None = None
    debit_eur: float | None = None
    score: float = 0.0                   # composite expected-value score
    rationale: list[str] = Field(default_factory=list)


class EarningsScenario(BaseModel):
    """Output of the earnings simulator for one position under a shock."""

    ticker: str
    contract_symbol: str
    spot_now: float
    spot_after: float
    iv_now: float
    iv_after: float
    price_now: float
    price_after: float
    pnl_per_contract_local: float
    pnl_total_eur: float
    notes: str = ""
    confidence: float = 1.0              # [0,1]; 0 if FRED unavailable
    metrics: dict[str, float] = Field(default_factory=dict)
    # CPI_yoy, PMI_proxy, DFF_chg_6m, T10Y2Y, T10Y3M, VIX, DXY


class PairCandidate(BaseModel):
    """Cointegration + momentum-gap screener row."""

    long_ticker: str
    short_ticker: str
    coint_pvalue: float
    halflife_days: float | None = None
    spread_z: float | None = None
    momentum_gap: float | None = None    # 12M-1M of long minus short
    rationale: str = ""


# ---------------------------------------------------------------------------
# Liquidity (Cluster 2)
# ---------------------------------------------------------------------------
class LiquidityRow(BaseModel):
    """Per-holding liquidity / impact snapshot."""

    ticker: str
    adv_usd: float                       # 20D rolling $-volume
    adv_eur: float
    weight_eur: float                    # portfolio weight (EUR)
    days_to_liq_10pct: float             # at 10% participation
    days_to_liq_20pct: float             # at 20% participation
    slippage_bps_1pct_trade: float       # cost (bps) of trading 1% of book
    short_interest_pct: float | None = None
    days_to_cover: float | None = None
    borrow_estimate: str = "n/a"         # "n/a" | "available" | "hard_to_borrow"


# ---------------------------------------------------------------------------
# Decision support (Cluster 3)
# ---------------------------------------------------------------------------
class ConvictionScore(BaseModel):
    """Composite conviction score for a single position.

    Each axis is rated 1 (poor) to 5 (excellent). The composite is a
    weighted mean (see `config/conviction_weights.yaml` defaults).
    """

    ticker: str
    thesis_quality: int                  # 1..5 — from user's journal pre-mortem & re-rating triggers
    downside: int                        # 1..5 — inverse of dilution + runway risk
    liquidity: int                       # 1..5 — derived from days_to_liq + slippage_bps
    catalyst_proximity: int              # 1..5 — inverse of days-to-next-catalyst
    composite: float                     # weighted mean, [1, 5]
    grade: Literal["A", "B", "C", "D"]
    rationale: list[str] = Field(default_factory=list)


class JournalMilestone(BaseModel):
    """One date-stamped milestone in a thesis journal."""

    date: str                            # ISO date or quarter label (e.g. "2026-Q3")
    label: str
    hit: bool = False
    weight: float = 1.0                  # contribution to milestones_hit_pct


class JournalEntry(BaseModel):
    """Per-ticker thesis YAML — one file per holding under data/journal/."""

    ticker: str
    thesis: str = ""
    entry_rationale: str = ""
    entry_price_eur: float | None = None
    entry_date: date | None = None
    position_target_pct: float | None = None
    price_target_eur: float | None = None
    stop_loss_thesis_eur: float | None = None       # "thèse cassée" stop
    stop_loss_technical_eur: float | None = None
    milestones: list[JournalMilestone] = Field(default_factory=list)
    pre_mortem: str = ""
    re_rating_triggers: list[str] = Field(default_factory=list)
    catalyst_event_ids: list[str] = Field(default_factory=list)
    last_updated: date | None = None
    schema_version: int = 1


class ReratingScore(BaseModel):
    """Output of compute_rerating_score — how much of the thesis is "in"."""

    ticker: str
    score: float                                    # [0, 100]
    price_progress_pct: float | None = None         # spot / target, capped at 100
    milestones_hit_pct: float                       # weighted fraction of milestones hit
    days_since_entry: int | None = None
    recommendation: Literal["hold", "trim", "add", "exit", "review"]
    rationale: list[str] = Field(default_factory=list)


class CollarQuote(BaseModel):
    """A 90-DTE protective collar quote for one position."""

    ticker: str
    underlying_px_eur: float
    expiry: date
    long_put_strike: float
    short_call_strike: float
    put_debit_eur: float                            # cost paid for the put leg
    call_credit_eur: float                          # premium received for the call leg
    net_premium_eur: float                          # put_debit - call_credit (positive = cost)
    cost_pct_notional: float
    breakeven_low: float                            # spot at expiry below which losses kick in
    breakeven_high: float                           # spot at expiry above which gains are capped
    max_loss_eur: float                             # signed negative
    max_gain_eur: float                             # signed positive
    notes: str = ""
