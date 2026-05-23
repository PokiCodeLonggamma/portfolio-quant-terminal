I have everything I need. Producing the plan now.

---

# Phase 1 Implementation Plan — Quant Terminal Expansion

Single architect-authored plan. 5–6 implementation agents will execute clusters in parallel on disjoint file sets. Plan is read-only — no code changes performed.

---

## 0. Conventions binding ALL clusters

- Python 3.11+, strict PEP 484, `from __future__ import annotations` at top of every module.
- Logger: `from src.utils.logging import get_logger; log = get_logger(__name__)`.
- Config: `from src.utils.config import get_config`.
- Cache I/O: `from src.utils.cache import read as cache_read, write as cache_write` with explicit `namespace=` per cluster (cluster-prefixed: `sec_form4`, `sec_13f`, `sec_xbrl`, `sam`, `regime`, `liq`, `decision`, `journal`, `hedge`, `calendar`, `news`, `options_chain`, `gex`, `trading_journal`, `watchlist`, `backtest`).
- All EUR amounts already enforced at portfolio layer. New modules touching cash values must convert via existing `src.data.fx.convert_to_eur(...)` or accept already-EUR inputs.
- Plotly figures: `from src.viz.theme import PLOTLY_TEMPLATE, PALETTE` and call `fig.update_layout(template=PLOTLY_TEMPLATE)`.
- Streamlit render functions: prefix `render_` and accept only data (no side-effect fetches) — fetches happen in `app.py` and are passed in.
- Tests use `pytest`, `tmp_path`, `monkeypatch`, and respect the existing `tests/conftest.py` fixtures.
- Network access in tests: ALWAYS monkey-patched. No real HTTP in CI.
- No cluster agent may touch the PROHIBITED files listed in the brief.

---

## 1. Shared schemas — `src/common/schemas.py` (new file, owned jointly; Cluster 1 creates)

This file is created ONCE by Cluster 1's agent (lowest cluster number among consumers) and imported by every other cluster. Pydantic v2 used to keep validation/serialization cheap.

```text
src/common/__init__.py
src/common/schemas.py
```

### Dataclasses / Pydantic models declared

```python
from datetime import date, datetime
from enum import Enum
from typing import Literal
from pydantic import BaseModel, Field

class Side(str, Enum):
    LONG = "LONG"
    SHORT = "SHORT"

class OptionRight(str, Enum):
    CALL = "C"
    PUT = "P"

class OptionContract(BaseModel):
    underlying: str                    # universe_key (e.g. "ASTS")
    symbol: str                        # OCC symbol e.g. "ASTS250620C00040000"
    expiry: date
    strike: float                      # USD
    right: OptionRight
    bid: float | None = None
    ask: float | None = None
    last: float | None = None
    mid: float | None = None
    iv: float | None = None            # implied vol (annualised, decimal)
    delta: float | None = None
    gamma: float | None = None
    theta: float | None = None
    vega: float | None = None
    open_interest: int | None = None
    volume: int | None = None
    snapshot_ts: datetime
    source: Literal["alpaca", "yfinance"] = "alpaca"

class CalendarEvent(BaseModel):
    event_id: str                      # stable hash key
    ticker: str | None                 # universe_key, or None for macro
    category: Literal[
        "earnings", "fomc", "ecb", "opec", "cpi", "eia",
        "nrc", "launch", "contract_award", "dividend", "macro_other",
    ]
    start: datetime
    end: datetime | None = None
    title: str
    source: str                        # "yfinance", "fred", "manual", ...
    payload: dict = Field(default_factory=dict)

class WatchlistEntry(BaseModel):
    universe_key: str
    sub_theme: str
    list_name: Literal["quantum", "photonics", "pre_ipo", "defense"]
    conviction: Literal["core", "high", "medium", "speculative", "private"]
    catalyst: str | None = None
    peers: list[str] = Field(default_factory=list)
    private: bool = False
    notes: str | None = None

class FilingEvent(BaseModel):
    cik: str
    ticker: str | None                 # universe_key, may be None for HFs
    form: Literal[
        "4", "13F-HR", "13D", "13G", "13D/A", "13G/A",
        "10-Q", "10-K", "S-3", "S-3/A", "424B5", "8-K",
    ]
    accession: str
    filed: date
    period_of_report: date | None = None
    url: str
    payload: dict = Field(default_factory=dict)  # form-specific parsed body

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
    rr_1_to_1: float                  # R/R if underlying moves 1*expected_move
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
```

Tests for the schema file live at `tests/test_common_schemas.py` (round-trip JSON, enum coercion, required field rejection).

---

## 2. Cluster-by-cluster plan

### Cluster 1 — Data/SEC (modules B + C + G)

**Owner: data-sec agent**
**Target dir:** `src/data_sec/`

#### Directory tree

```text
src/common/__init__.py                            (created here)
src/common/schemas.py                             (created here — see Section 1)
src/data_sec/__init__.py
src/data_sec/edgar_client.py                      shared httpx wrapper with SEC_EMAIL UA + 10 req/s throttle
src/data_sec/forms_index.py                       submissions-API: list filings for a CIK / by form type
src/data_sec/form4.py                             Form 4 (insider transactions) XML parser
src/data_sec/form13f.py                           13F-HR information-table XML parser
sample_data_sec/form13d.py                        13D/13G beneficial ownership detection
src/data_sec/etf_flows.py                         thematic ETF flows (URA, ARKX, QTUM, XLE, GDX, SMH) via yfinance shares-outstanding * NAV-px delta
src/data_sec/xbrl_facts.py                        company facts API (XBRL frames) — cash, debt, FCF
src/data_sec/dilution.py                          ATM detection (S-3 + 424B5 keyword scan), convertibles outstanding, dilution score
src/data_sec/cash_runway.py                       runway = cash / TTM burn from xbrl_facts
src/data_sec/sam_gov.py                           SAM.gov contract awards REST scrape
src/data_sec/dod_budget.py                        manual yaml-backed top-line program allocations
src/data_sec/hyperscaler_capex.py                 manual yaml-backed quarterly capex figures
src/data_sec/hf_registry.py                       static list of ~30 quant/discretionary HF CIKs
config/hf_registry.yaml                           CIK -> name -> bucket (Quant / Macro / Activist)
config/dod_programs.yaml                          program -> ticker_mapping -> $B annual
config/hyperscaler_capex.yaml                     quarterly capex per hyperscaler (MSFT/META/GOOG/AMZN)
```

#### Public interface

```python
# edgar_client.py
def edgar_get(path: str, *, params: dict | None = None) -> httpx.Response: ...
def edgar_json(path: str, *, params: dict | None = None) -> dict: ...
SEC_BASE: str = "https://data.sec.gov"
WWW_BASE: str = "https://www.sec.gov"

# forms_index.py
def cik_for_ticker(ticker: str) -> str | None: ...
def list_filings(cik: str, *, forms: list[str], since: date | None = None) -> list[FilingEvent]: ...
def fulltext_search(query: str, *, forms: list[str], dateRange: tuple[date, date] | None = None) -> list[FilingEvent]: ...

# form4.py
class InsiderTransaction(BaseModel):
    cik: str
    reporter_name: str
    reporter_role: str
    ticker: str
    transaction_date: date
    code: str                                     # P, S, A, M, F...
    shares: float
    price: float                                  # USD
    value_usd: float
    post_holding_shares: float
    accession: str

def parse_form4(filing: FilingEvent) -> list[InsiderTransaction]: ...
def insider_summary(ticker: str, *, lookback_days: int = 180) -> pd.DataFrame: ...
# columns: ticker, net_shares, net_usd, n_buyers, n_sellers, last_filing

# form13f.py
class Holding13F(BaseModel):
    cik_fund: str
    fund_name: str
    cusip: str
    ticker: str | None
    name_of_issuer: str
    shares: int
    value_usd_000: int
    period_of_report: date

def parse_13f_information_table(filing: FilingEvent) -> list[Holding13F]: ...
def smart_money_tape(tickers: list[str], *, quarter: str | None = None) -> pd.DataFrame: ...
# columns: ticker, n_funds_long, qoq_delta_funds, sum_value_usd, top5_funds

# form13d.py
def detect_13d_13g(ticker: str, *, since: date) -> list[FilingEvent]: ...

# etf_flows.py
def etf_flows(ticker: str, *, window_days: int = 90) -> pd.DataFrame: ...
# columns: date, shares_out, nav, aum_usd, daily_flow_usd
def thematic_flows_panel() -> pd.DataFrame: ...   # one column per of URA, ARKX, QTUM, XLE, GDX, SMH

# xbrl_facts.py
def company_facts(cik: str) -> dict: ...          # raw concept dict
def get_concept(cik: str, concept: str, *, taxonomy: str = "us-gaap") -> pd.DataFrame: ...
def quarterly_cash_and_burn(ticker: str) -> pd.DataFrame: ...
# columns: period_end, cash_eq, op_cf, fcf, burn_qoq

# dilution.py
class DilutionAssessment(BaseModel):
    ticker: str
    atm_active: bool
    atm_remaining_usd: float | None
    convertibles_outstanding_usd: float | None
    shares_outstanding: float
    dilution_score: int                           # 1-5
    rationale: list[str]

def assess_dilution(ticker: str) -> DilutionAssessment: ...
def portfolio_dilution_panel(tickers: list[str]) -> pd.DataFrame: ...

# cash_runway.py
class RunwayAssessment(BaseModel):
    ticker: str
    cash_eur: float
    quarterly_burn_eur: float
    runway_quarters: float
    period_end: date
    confidence: Literal["high", "medium", "low"]

def assess_runway(ticker: str) -> RunwayAssessment: ...
def portfolio_runway_panel(tickers: list[str]) -> pd.DataFrame: ...

# sam_gov.py
class ContractAward(BaseModel):
    awarded_to: str
    ticker: str | None
    award_id: str
    amount_usd: float
    awarded_on: date
    description: str
    agency: str

def search_awards(tickers: list[str], *, since: date) -> list[ContractAward]: ...
def awards_dataframe(tickers: list[str], *, lookback_days: int = 365) -> pd.DataFrame: ...

# dod_budget.py
def budget_allocations() -> pd.DataFrame: ...
# columns: program, ticker_exposure, fy_usd_billion, source_note

# hyperscaler_capex.py
def capex_panel() -> pd.DataFrame: ...
# columns: quarter, msft, meta, goog, amzn, total
```

#### Data sources
SEC EDGAR (submissions, company facts, full-text search), SAM.gov REST, yfinance (ETF shares-outstanding fallback), local YAML for DoD / hyperscaler.

#### Dependencies on other clusters
- IMPORTS: only `src.common.schemas`, `src.utils.*`, `src.data.fx.convert_to_eur`.
- EXPORTS consumed by: Cluster 3 (decision/conviction reads `assess_dilution`, `assess_runway`, `smart_money_tape`), Cluster 4 (calendar reads `awards_dataframe` to surface SAM events), Cluster 5 (trading reads `insider_summary` for gating).

#### Integration touchpoints (Phase 2 by main agent)
- `app.py` — add new tab `tab_smart` ("Smart-Money & Filings"); inside it call `render_smart_money_panel`, `render_dilution_panel`, `render_runway_panel`, `render_etf_flows_panel`, `render_gov_capex_panel` from new dashboard module `src/data_sec/dashboards.py` (Cluster 1 creates).
- `src/viz/dashboards.py` — UNCHANGED. New render functions live inside the cluster's own dashboards module.
- Sidebar — add lookback selector `lookback_days` (90/180/365) wired into smart-money fetch.

`src/data_sec/dashboards.py` exposes:
```python
def render_smart_money_panel(df_form4: pd.DataFrame, df_13f: pd.DataFrame) -> None: ...
def render_filings_table(filings: list[FilingEvent]) -> None: ...
def render_dilution_panel(df: pd.DataFrame) -> None: ...
def render_runway_panel(df: pd.DataFrame) -> None: ...
def render_etf_flows_panel(panel: pd.DataFrame) -> None: ...
def render_gov_capex_panel(awards: pd.DataFrame, dod: pd.DataFrame, capex: pd.DataFrame) -> None: ...
```

#### Tests — `tests/test_data_sec.py`
- `test_edgar_client_sets_ua` — monkeypatch httpx, assert header contains SEC_EMAIL.
- `test_cik_for_ticker_known` — assert known ticker resolves (mock response).
- `test_parse_form4_buy_aggregates` — fixture XML, assert net_shares > 0.
- `test_parse_13f_information_table_count` — assert holdings count matches sample.
- `test_quarterly_cash_and_burn_columns` — assert dataframe columns.
- `test_assess_dilution_score_bounds` — 1 ≤ score ≤ 5.
- `test_assess_runway_low_cash_confidence` — when burn=0 → confidence == "low".
- `test_sam_gov_filter_by_ticker` — fixture JSON, assert mapping.
- `test_thematic_flows_panel_columns` — 6 expected ETFs as columns.

#### Complexity: **L** (SEC + XBRL + SAM is the heaviest cluster).

#### Risks
1. SEC rate-limits (10 req/s) and intermittent 403; throttle + retry must be airtight.
2. XBRL concept naming drift between filers (us-gaap vs ifrs-full); need fallback ladder of concept names per metric.
3. 13F lag is 45 days — UI must show "as of" period_end clearly to avoid stale-signal misuse.

---

### Cluster 2 — Macro/Régime (modules D + F)

**Owner: macro-liquidity agent**
**Target dirs:** `src/macro/`, `src/liquidity/`

#### Directory tree

```text
src/macro/__init__.py
src/macro/regime.py                               regime classifier from FRED panel
src/macro/correlations.py                         rolling correlation engine + regime-change alerts
src/macro/pair_trade.py                           cointegration + momentum-gap screener
src/macro/dashboards.py                           render_regime_card, render_corr_alerts, render_pair_candidates
src/liquidity/__init__.py
src/liquidity/adv.py                              average daily $-volume per holding
src/liquidity/impact.py                           Almgren-Chriss simplified slippage cost
src/liquidity/borrow.py                           IB short-borrow proxy / yfinance short interest fallback
src/liquidity/dashboards.py                       render_liquidity_table, render_borrow_panel
config/regime_thresholds.yaml                     CPI/PMI/DFF thresholds defining each box of the 2x2x2
```

#### Public interface

```python
# regime.py
class Regime(BaseModel):
    inflation: Literal["high", "low"]
    growth: Literal["high", "low"]
    policy: Literal["tight", "loose"]
    confidence: float                              # [0,1]
    asof: date
    metrics: dict[str, float]                      # CPI_yoy, PMI_proxy, DFF, T10Y2Y

def classify_regime(asof: date | None = None) -> Regime: ...
def regime_history(*, start: date, end: date) -> pd.DataFrame: ...
# columns: date, inflation, growth, policy, confidence

# correlations.py
def rolling_correlations(
    portfolio_returns_panel: pd.DataFrame,        # date x universe_key
    benchmarks_returns: pd.DataFrame,             # date x bench
    *, window: int = 60,
) -> pd.DataFrame: ...                            # multi-index (date, ticker), columns = benchmarks

def correlation_change_alerts(
    rolling_corr: pd.DataFrame,
    *, delta_threshold: float = 0.3, lookback: int = 30,
) -> pd.DataFrame: ...
# columns: ticker, benchmark, corr_now, corr_then, delta, asof

BENCHMARKS: list[str] = ["SPY", "QQQ", "URA", "XLE", "GLD", "DXY", "VIX"]

# pair_trade.py
class PairCandidate(BaseModel):
    long_ticker: str
    short_ticker: str
    coint_pvalue: float
    halflife_days: float
    spread_z: float
    momentum_gap: float
    rationale: str

def screen_pairs(
    candidate_pool: list[str], *,
    lookback_days: int = 252,
    pvalue_threshold: float = 0.05,
) -> list[PairCandidate]: ...

# liquidity/adv.py
def adv_panel(
    tickers: list[str], *, window_days: int = 20,
) -> pd.DataFrame: ...
# columns: ticker, adv_usd, adv_eur, last_px_eur, source

# liquidity/impact.py
def days_to_liquidate(
    weight_eur: float, adv_eur: float, *, participation: float = 0.10,
) -> float: ...

def slippage_cost(
    weight_eur: float, adv_eur: float, sigma_daily: float,
    *, participation: float = 0.10, eta: float = 0.142,
) -> float: ...

def liquidity_table(portfolio: "Portfolio") -> pd.DataFrame: ...
# columns: ticker, weight_eur, adv_eur, days_to_liq_10pct, days_to_liq_20pct,
#          slippage_eur_10pct, slippage_bps_10pct

# liquidity/borrow.py
def borrow_rate(ticker: str) -> float | None: ...
def short_interest(ticker: str) -> dict: ...
def borrow_panel(tickers: list[str]) -> pd.DataFrame: ...
# columns: ticker, short_interest_pct, days_to_cover, borrow_rate_proxy
```

#### Data sources
FRED (existing wrapper), Alpaca + yfinance via existing `src.data.loaders.download_prices`, yfinance for short-interest metadata.

#### Dependencies on other clusters
- IMPORTS: `src.common.schemas` (none used directly, but reserved), `src.data.fred_client`, `src.data.loaders`, `src.portfolio.holdings.Portfolio`, `src.utils.*`.
- EXPORTS consumed by: Cluster 3 (decision module reads `liquidity_table` for the liquidity score), Cluster 5 (trading reads `borrow_rate` for short candidates exclusion).

#### Integration touchpoints (Phase 2)
- `app.py` — inside existing Portfolio tab, add 2 sub-sections under `section`: "Régime macro" and "Liquidity & borrow"; call `render_regime_card`, `render_corr_alerts`, `render_pair_candidates`, `render_liquidity_table`, `render_borrow_panel`.
- `src/viz/dashboards.py` — UNCHANGED.

Render functions:
```python
# src/macro/dashboards.py
def render_regime_card(regime: Regime) -> None: ...
def render_regime_history(history: pd.DataFrame) -> None: ...
def render_corr_alerts(alerts: pd.DataFrame) -> None: ...
def render_pair_candidates(pairs: list[PairCandidate]) -> None: ...

# src/liquidity/dashboards.py
def render_liquidity_table(df: pd.DataFrame) -> None: ...
def render_borrow_panel(df: pd.DataFrame) -> None: ...
```

#### Tests — `tests/test_macro_liquidity.py`
- `test_classify_regime_mock_fred` — assert four-field tuple returned.
- `test_regime_change_alert_above_threshold` — synthetic series, assert one alert produced.
- `test_screen_pairs_returns_sorted_by_pvalue`.
- `test_adv_panel_eur_conversion` — synthetic USD prices, verify EUR mapping via fx fixture.
- `test_days_to_liquidate_zero_adv` — returns inf or sentinel.
- `test_slippage_cost_monotonic_in_weight`.

#### Complexity: **M**

#### Risks
1. FRED series can be empty (CI without API key) — regime classifier needs deterministic fallback returning Regime(confidence=0).
2. Engle-Granger cointegration is fragile on short windows — must enforce min sample size.
3. Short-interest data via yfinance is sparse and stale; mark all borrow outputs as "estimate".

---

### Cluster 3 — Decision Support (modules E + H + I)

**Owner: decision agent**
**Target dir:** `src/decision/`

#### Directory tree

```text
src/decision/__init__.py
src/decision/conviction.py                        scoring engine (E)
src/decision/sizing.py                            Kelly/4, risk-parity preview, VaR-contribution
src/decision/journal.py                           thesis journal persistence (H)
src/decision/rerating.py                          re-rating score from price vs target + milestones
src/decision/hedge.py                             collar / futures / vanilla put hedge cost (I)
src/decision/dashboards.py                        render_conviction_matrix, render_sizing_table, render_journal_editor, render_hedge_panel
data/journal/                                     created lazily; one yaml per ticker
config/conviction_weights.yaml                    weights of each score axis
config/hedge_defaults.yaml                        default collar offsets, 3x ETP mappings
```

#### Public interface

```python
# conviction.py
class ConvictionScore(BaseModel):
    ticker: str
    thesis_quality: int                           # 1..5
    downside: int
    liquidity: int
    catalyst_proximity: int
    composite: float                              # weighted mean
    grade: Literal["A", "B", "C", "D"]
    rationale: list[str]

def score_position(
    ticker: str, *,
    dilution: "DilutionAssessment | None" = None,
    runway: "RunwayAssessment | None" = None,
    liquidity_row: pd.Series | None = None,
    next_catalyst_days: int | None = None,
    user_inputs: dict | None = None,
) -> ConvictionScore: ...

def score_portfolio(portfolio: "Portfolio", **kwargs) -> pd.DataFrame: ...

# sizing.py
def kelly_fraction(edge: float, odds: float, *, haircut: float = 0.25) -> float: ...
def suggest_weight_kelly(
    conviction: ConvictionScore, expected_return: float, daily_vol: float,
) -> float: ...
def var_contribution_sizing(
    portfolio: "Portfolio",
    per_position_returns: pd.DataFrame,
    *, target_var_pct: float = 0.02,
) -> pd.Series: ...
def risk_parity_preview(per_position_returns: pd.DataFrame) -> pd.Series: ...
def sizing_table(
    portfolio: "Portfolio", scores: pd.DataFrame,
    per_position_returns: pd.DataFrame,
) -> pd.DataFrame: ...
# columns: ticker, current_weight, kelly_weight, var_contrib_weight, risk_parity_weight, delta_vs_current

# journal.py
class ThesisEntry(BaseModel):
    ticker: str
    thesis: str
    entry_rationale: str
    entry_date: date
    price_target_eur: float | None = None
    stop_loss_thesis: str | None = None
    re_rating_triggers: list[str] = Field(default_factory=list)
    pre_mortem: str | None = None
    updated_at: datetime

def journal_dir() -> Path: ...
def load_thesis(ticker: str) -> ThesisEntry | None: ...
def save_thesis(entry: ThesisEntry) -> Path: ...
def all_theses() -> list[ThesisEntry]: ...

# rerating.py
class RerateAssessment(BaseModel):
    ticker: str
    spot_eur: float
    target_eur: float | None
    progress_pct: float | None                    # spot / target
    triggers_hit: list[str]
    triggers_pending: list[str]
    score: int                                    # 1..5
    advice: Literal["hold", "trim", "add", "exit", "review"]

def assess_rerate(ticker: str, *, spot_eur: float) -> RerateAssessment: ...

# hedge.py
class HedgeQuote(BaseModel):
    ticker: str
    underlying_px_eur: float
    expiry: date
    structure: Literal["collar", "long_put", "futures_short"]
    long_put_strike: float | None = None
    short_call_strike: float | None = None
    net_cost_eur: float
    cost_pct_notional: float
    breakeven_eur: float | None = None
    notes: str

def collar_cost(
    ticker: str, *,
    dte: int = 90,
    call_offset_pct: float = 0.15,
    put_offset_pct: float = -0.10,
) -> HedgeQuote: ...

def vanilla_put_cost(ticker: str, *, dte: int = 90, otm_pct: float = -0.10) -> HedgeQuote: ...
def futures_proxy(etp_ticker: str) -> HedgeQuote: ...
def portfolio_hedge_panel(portfolio: "Portfolio") -> pd.DataFrame: ...
```

#### Data sources
- Cluster 1: `assess_dilution`, `assess_runway`.
- Cluster 2: `liquidity_table`.
- Cluster 4: next catalyst days.
- Cluster 5: `OptionContract` chain via `src.trading.options_chain.fetch_chain` (for hedge module).
- Existing: `src.portfolio.holdings.Portfolio`, `src.portfolio.risk.parametric_var`.

#### Dependencies on other clusters
- HARD: Cluster 1 (dilution/runway), Cluster 2 (liquidity), Cluster 4 (catalyst proximity), Cluster 5 (option chain for hedge).
- Cluster 3 must NOT block on these — if imports fail at fetch time, return graceful defaults so cluster 3 can be developed against stubs.

#### Integration touchpoints (Phase 2)
- `app.py` — add new tab `tab_decision` ("Decision Support") with sub-sections "Conviction matrix", "Sizing", "Thesis journal", "Hedge calculator". Wire to the 4 render functions.
- `src/viz/dashboards.py` — UNCHANGED.

```python
# src/decision/dashboards.py
def render_conviction_matrix(scores: pd.DataFrame) -> None: ...
def render_sizing_table(table: pd.DataFrame) -> None: ...
def render_journal_editor(theses: list[ThesisEntry], current_ticker: str) -> None: ...
def render_rerating_panel(rows: list[RerateAssessment]) -> None: ...
def render_hedge_panel(panel: pd.DataFrame) -> None: ...
```

#### Tests — `tests/test_decision.py`
- `test_score_position_clamps_to_1_5`.
- `test_kelly_fraction_haircut_applied`.
- `test_save_then_load_thesis_roundtrip` (uses tmp_path monkeypatched journal_dir).
- `test_rerate_progress_pct_caps_at_one`.
- `test_collar_cost_uses_provided_chain` (chain passed in via fixture).
- `test_sizing_table_columns_present`.

#### Complexity: **M**

#### Risks
1. Hedge module depends on Cluster 5's chain fetcher — must develop against stub interface only, NOT a hard import at module top.
2. Journal YAML schema migration risk — version field in ThesisEntry recommended (add `schema_version: int = 1`).
3. Sizing math must NOT recommend leverage > available cash; gate clearly.

---

### Cluster 4 — Calendar/News (modules A + J)

**Owner: calendar-news agent**
**Target dirs:** `src/calendar_engine/`, `src/news/`

#### Directory tree

```text
src/calendar_engine/__init__.py
src/calendar_engine/earnings.py                   yfinance + Nasdaq scrape for earnings dates
src/calendar_engine/macro.py                      FOMC, CPI, ECB, EIA from FRED + hardcoded schedules
src/calendar_engine/commodities.py                OPEC+ meetings, EIA Wednesdays
src/calendar_engine/space.py                      SpaceX + RocketLab manifest scrape (best-effort) + manual yaml
src/calendar_engine/nrc.py                        NRC SMR application milestones (yaml-backed)
src/calendar_engine/implied_move.py               ATM straddle / spot implied move
src/calendar_engine/aggregator.py                 unify all sources into List[CalendarEvent]
src/calendar_engine/dashboards.py                 render_calendar_timeline, render_implied_move_table
config/macro_calendar.yaml                        manual FOMC/ECB/OPEC dates (fallback when FRED absent)
config/space_launches.yaml                        SpaceX + RocketLab planned launches
config/nrc_milestones.yaml                        NRC dockets per portfolio holding

src/news/__init__.py
src/news/google_rss.py                            Google News RSS scraper per ticker
src/news/sentiment.py                             VADER + rule-based sentiment scorer
src/news/heatmap.py                               weekly noise heatmap dataframe
src/news/dashboards.py                            render_news_heatmap, render_news_stream
```

#### Public interface

```python
# calendar_engine/earnings.py
def next_earnings_date(ticker: str) -> date | None: ...
def earnings_history(ticker: str, *, n_quarters: int = 8) -> pd.DataFrame: ...
# columns: report_date, eps_est, eps_actual, surprise_pct, px_move_1d, px_move_5d

# calendar_engine/macro.py
def fomc_schedule(*, since: date) -> list[CalendarEvent]: ...
def cpi_release_schedule(*, since: date) -> list[CalendarEvent]: ...
def ecb_schedule(*, since: date) -> list[CalendarEvent]: ...

# calendar_engine/commodities.py
def opec_meetings(*, since: date) -> list[CalendarEvent]: ...
def eia_weekly(*, since: date) -> list[CalendarEvent]: ...

# calendar_engine/space.py
def upcoming_launches() -> list[CalendarEvent]: ...

# calendar_engine/nrc.py
def smr_milestones() -> list[CalendarEvent]: ...

# calendar_engine/implied_move.py
def implied_move(ticker: str, *, expiry_target: date | None = None) -> dict: ...
# {ticker, expiry, atm_straddle_pct, days_to_event, hist_realised_8q_avg}
def implied_move_panel(tickers: list[str], events_by_ticker: dict[str, date]) -> pd.DataFrame: ...

# calendar_engine/aggregator.py
def aggregate_events(
    portfolio_tickers: list[str],
    watchlist_tickers: list[str],
    *, horizon_days: int = 60,
) -> list[CalendarEvent]: ...

def next_catalyst_days(ticker: str, events: list[CalendarEvent]) -> int | None: ...

# news/google_rss.py
def fetch_headlines(ticker: str, *, days: int = 7, max_items: int = 50) -> pd.DataFrame: ...
# columns: ticker, ts, title, source, url

# news/sentiment.py
def score_headline(title: str, *, use_vader: bool = True) -> float: ...
def score_headlines_df(df: pd.DataFrame) -> pd.DataFrame: ...
# adds: sentiment in [-1, 1], category

# news/heatmap.py
def weekly_news_heatmap(
    tickers: list[str], *, days: int = 28,
) -> pd.DataFrame: ...                            # rows=ticker, cols=day, values=count+avg_sentiment
```

#### Data sources
yfinance (earnings, options chain for implied-move), FRED (FOMC), Google News RSS, manual YAML for OPEC/launches/NRC.

#### Dependencies on other clusters
- Cluster 5 `fetch_chain` (for implied-move ATM straddle). Cluster 4 may compute its own via yfinance only — but PREFERRED to import `from src.trading.options_chain import fetch_chain` so we don't fetch twice.
- IMPORTS: `src.common.schemas.CalendarEvent`, `src.utils.*`. Optional soft import of Cluster 5.

#### Integration touchpoints (Phase 2)
- `app.py` — add new tab `tab_calendar` ("Calendar & News") with `render_calendar_timeline`, `render_implied_move_table`, `render_news_heatmap`, `render_news_stream`.
- `src/viz/dashboards.py` — UNCHANGED.

```python
# calendar_engine/dashboards.py
def render_calendar_timeline(events: list[CalendarEvent]) -> None: ...
def render_implied_move_table(df: pd.DataFrame) -> None: ...

# news/dashboards.py
def render_news_heatmap(matrix: pd.DataFrame) -> None: ...
def render_news_stream(df: pd.DataFrame) -> None: ...
```

#### Tests — `tests/test_calendar_news.py`
- `test_aggregate_events_dedup` — duplicate dates collapsed.
- `test_next_catalyst_days_returns_min`.
- `test_implied_move_handles_empty_chain` — returns dict with None values.
- `test_score_headline_positive_keyword`.
- `test_score_headline_negative_keyword`.
- `test_weekly_news_heatmap_dims` — n_tickers rows × n_days cols.

#### Complexity: **M**

#### Risks
1. yfinance `Ticker.calendar` is unreliable — scrape fallback path must be best-effort with logged failures, not exceptions.
2. Google News RSS occasionally returns HTML or rate-limits — cache (TTL 30 min) + degraded mode.
3. Heuristic sentiment is noisy by design; UI must label it "indicative".

---

### Cluster 5 — Trading section (NEW tab — directional long options)

**Owner: trading agent**
**Target dir:** `src/trading/`

#### Directory tree

```text
src/trading/__init__.py
src/trading/options_chain.py                      Alpaca primary + yfinance fallback chain fetcher
src/trading/greeks.py                             BS pricer + inverse IV + greeks (used only on yf fallback)
src/trading/iv_rank.py                            IV rank vs 1Y range
src/trading/gex.py                                Net Gamma Exposure per strike, gamma flip
src/trading/delta_finder.py                       closest-delta strike picker
src/trading/trade_ticket.py                       trade ticket generator + gating rules
src/trading/journal.py                            parquet-persisted open/closed trades + live MTM
src/trading/dashboards.py                         all Streamlit blocks for the new tab
config/trading_gates.yaml                         IV rank, OI min, debit max, target delta, DTE bounds
data/trading_journal.parquet                     created lazily by journal.open_trade
```

#### Public interface

```python
# options_chain.py
def fetch_chain(
    ticker: str, *,
    expiries: list[date] | None = None,
    rights: list[OptionRight] | None = None,
) -> list[OptionContract]: ...

def expiries_available(ticker: str) -> list[date]: ...

def chain_dataframe(
    contracts: list[OptionContract], *, sort: str = "strike",
) -> pd.DataFrame: ...

# greeks.py
def bs_price(S: float, K: float, T: float, r: float, sigma: float, right: OptionRight) -> float: ...
def bs_delta(S: float, K: float, T: float, r: float, sigma: float, right: OptionRight) -> float: ...
def bs_gamma(S: float, K: float, T: float, r: float, sigma: float) -> float: ...
def bs_theta(S: float, K: float, T: float, r: float, sigma: float, right: OptionRight) -> float: ...
def bs_vega(S: float, K: float, T: float, r: float, sigma: float) -> float: ...
def implied_vol(price: float, S: float, K: float, T: float, r: float, right: OptionRight) -> float | None: ...
def enrich_with_greeks(contracts: list[OptionContract], *, spot: float, r: float = 0.04) -> list[OptionContract]: ...

# iv_rank.py
def iv_history(ticker: str, *, days: int = 365) -> pd.Series: ...
def iv_rank(ticker: str, *, current_iv: float | None = None) -> dict: ...
# {ticker, current_iv, iv_low_1y, iv_high_1y, iv_rank, iv_percentile}

# gex.py
class GammaCurve(BaseModel):
    ticker: str
    asof: datetime
    spot: float
    flip_strike: float | None
    negative_zone_lo: float | None
    negative_zone_hi: float | None
    per_strike: list[dict]                        # [{strike, net_gamma_eur_per_1pct}]

def compute_gex(chain: list[OptionContract], *, spot: float) -> GammaCurve: ...
def render_gex_payload(curve: GammaCurve) -> dict: ...

# delta_finder.py
def find_strike_by_delta(
    chain: list[OptionContract], *,
    right: OptionRight, target_delta: float, dte_min: int = 14, dte_max: int = 45,
) -> OptionContract | None: ...

def candidates_table(
    ticker: str, *, target_delta: float = 0.25, dte_min: int = 14, dte_max: int = 45,
) -> pd.DataFrame: ...

# trade_ticket.py
GATE_DEFAULTS = {
    "iv_rank_max": 80.0,
    "oi_min": 100,
    "debit_max_pct_net_ev": 0.02,
    "target_delta": 0.25,
    "dte_min": 14, "dte_max": 45,
}

def generate_ticket(
    ticker: str, *, direction: Literal["LONG_CALL", "LONG_PUT"],
    net_ev_eur: float, target_delta: float = 0.25,
    max_debit_eur: float | None = None,
) -> TradeTicket: ...

def evaluate_gates(ticket: TradeTicket, *, iv_rank_val: float) -> list[str]: ...  # returns refused_reasons

# journal.py
def open_trade(ticket: TradeTicket, *, qty: int = 1, notes: str | None = None) -> JournalTradeRow: ...
def close_trade(trade_id: str, *, exit_credit_eur: float, ts: datetime | None = None) -> JournalTradeRow: ...
def load_journal() -> pd.DataFrame: ...           # both open and closed
def mark_to_market(open_rows: pd.DataFrame) -> pd.DataFrame: ...
# adds: mtm_credit_eur, mtm_pnl_eur, mtm_pct
```

#### Data sources
Alpaca options data primary, yfinance options fallback. Spot from `src.data.loaders.load_one`. FX via `src.data.fx`.

#### Dependencies on other clusters
- IMPORTS: `src.common.schemas.{OptionContract, OptionRight, TradeTicket, JournalTradeRow}`, `src.data.loaders`, `src.data.fx`, `src.utils.*`.
- EXPORTS consumed by: Cluster 3 (hedge.py), Cluster 4 (implied_move.py).

#### Integration touchpoints (Phase 2)
- `app.py` — add new tab `tab_trading` ("Options Trading"). Five sub-sections: "Chain explorer", "GEX", "Trade ticket", "Journal", "Greeks playground".
- `src/viz/dashboards.py` — UNCHANGED.

```python
# trading/dashboards.py
def render_chain_explorer(chain_df: pd.DataFrame, spot_eur: float) -> None: ...
def render_gex_panel(curve: GammaCurve) -> None: ...
def render_trade_ticket_form(portfolio_net_ev_eur: float) -> TradeTicket | None: ...
def render_journal_table(journal_df: pd.DataFrame) -> None: ...
def render_iv_rank_pill(iv_rank_payload: dict) -> None: ...
```

#### Tests — `tests/test_trading.py`
- `test_bs_price_call_put_parity` — `C - P == S - K*exp(-rT)` to 1e-6.
- `test_implied_vol_recovers_input_sigma`.
- `test_find_strike_by_delta_returns_closest`.
- `test_chain_dataframe_columns`.
- `test_iv_rank_handles_constant_history` — returns 0 or 100 sentinel.
- `test_generate_ticket_refuses_high_iv_rank` — mocked iv_rank=90 → refused.
- `test_generate_ticket_refuses_low_oi` — refused.
- `test_generate_ticket_refuses_oversized_debit` — refused.
- `test_open_close_journal_roundtrip` (tmp_path).
- `test_mark_to_market_pnl_signs`.
- `test_compute_gex_flip_strike_detected` — synthetic chain.

#### Complexity: **L**

#### Risks
1. Alpaca options API is paid-tier on some plans — fallback to yfinance must be bulletproof and silent. Greeks then computed via BS inverse → 200-500ms per chain.
2. EUR / USD FX must be applied consistently to debit_eur (Alpaca options are USD-denominated).
3. yfinance OI/volume often null — gates must short-circuit cleanly when fields are None.

---

### Cluster 6 — Watchlists (Quantum + Photonics + Pre-IPO/Defense)

**Owner: watchlist agent**
**Target dir:** `src/watchlist/`

#### Directory tree

```text
src/watchlist/__init__.py
src/watchlist/loader.py                           parse watchlists.yaml -> List[WatchlistEntry] + Portfolio-like df
src/watchlist/private.py                          parse private_watchlist.yaml
src/watchlist/cards.py                            per-ticker mini-card data assembly (price, 1D/1W/1M/3M/YTD, BBands ribbon)
src/watchlist/dashboards.py                       tabbed sub-list rendering
config/watchlists.yaml                            Quantum/Photonics/Defense
config/private_watchlist.yaml                     Pre-IPO
```

#### Public interface

```python
# loader.py
def load_watchlists(list_name: Literal["quantum", "photonics", "defense"]) -> list[WatchlistEntry]: ...
def to_portfolio_stub(entries: list[WatchlistEntry]) -> pd.DataFrame: ...
# columns: symbol, name, quantity=1, value_eur=1, currency, then enriched downstream

# private.py
class PrivateEntry(BaseModel):
    name: str
    sub_theme: str
    last_valuation_usd_b: float | None
    last_round_date: date | None
    last_round_stage: str | None
    listed_proxies: list[str]
    notes: str | None = None

def load_private_watchlist() -> list[PrivateEntry]: ...

# cards.py
class MiniCard(BaseModel):
    universe_key: str
    name: str
    spot_eur: float | None
    ret_1d: float | None
    ret_1w: float | None
    ret_1m: float | None
    ret_3m: float | None
    ret_ytd: float | None
    bbands_upper: float | None
    bbands_lower: float | None
    sub_theme: str
    conviction: str
    next_catalyst: str | None
    next_catalyst_days: int | None

def build_mini_card(
    entry: WatchlistEntry, *,
    events: list[CalendarEvent] | None = None,
) -> MiniCard: ...

def build_all_cards(
    list_name: Literal["quantum", "photonics", "defense"], *,
    events: list[CalendarEvent] | None = None,
) -> list[MiniCard]: ...
```

#### Data sources
- `src.data.loaders.download_prices` for price series.
- Cluster 4 `aggregate_events` for next catalysts (soft import).
- YAML only for private list.

#### Dependencies on other clusters
- IMPORTS: `src.common.schemas.{WatchlistEntry, CalendarEvent}`, `src.data.loaders`, `src.portfolio.holdings.Portfolio` (to reuse enrichment), `src.utils.*`.
- Cluster 4 optional.

#### Integration touchpoints (Phase 2)
- `app.py` — add new tab `tab_watchlist` ("Watchlists") with sub-tabs `[Quantum | Photonics | Defense | Pre-IPO]`. Call `render_watchlist_grid` for each list and `render_private_grid` for Pre-IPO.
- `src/viz/dashboards.py` — UNCHANGED.
- `config/universe.yaml` — UNTOUCHED. Watchlists carry their own symbol metadata, but tickers also present in universe.yaml will be auto-enriched by Portfolio._enrich when fed via `to_portfolio_stub` + `Portfolio(holdings=...)`.

```python
# watchlist/dashboards.py
def render_watchlist_grid(cards: list[MiniCard]) -> None: ...
def render_private_grid(entries: list[PrivateEntry]) -> None: ...
def render_minicard(card: MiniCard) -> None: ...
```

#### Tests — `tests/test_watchlist.py`
- `test_load_watchlists_yaml_roundtrip`.
- `test_to_portfolio_stub_columns`.
- `test_mini_card_returns_handle_missing_prices`.
- `test_load_private_watchlist_parses_valuation`.

#### Complexity: **S–M**

#### Risks
1. Many quantum/photonics tickers are not in universe.yaml — the watchlist agent MUST NOT edit universe.yaml; instead watchlists.yaml carries currency/region/yfinance metadata of its own, and loader normalises into the Portfolio stub schema directly without going through universe enrichment.
2. Pre-IPO valuations are manual — UI must display "as of" date prominently.
3. Bollinger ribbon on illiquid microcaps can be visually noisy — clamp to 20D MA ± 2*sigma even with NaN-padded series.

---

### Cluster 7 — Backtest (module K)

**Owner: backtest agent**
**Target dir:** `src/backtest/`

#### Directory tree

```text
src/backtest/__init__.py
src/backtest/rules.py                             Rule dataclasses + registry
src/backtest/engine.py                            historical replay with/without rules
src/backtest/walk_forward.py                      threshold sweeps for entry signals (momentum, mean-reversion)
src/backtest/metrics.py                           equity-vs-equity, Sharpe delta, MDD delta
src/backtest/dashboards.py                        render_rules_compare, render_walk_forward_heatmap
config/backtest_rules.yaml                        user-defined rule library
```

#### Public interface

```python
# rules.py
class Rule(BaseModel):
    name: str
    rule_type: Literal["max_single_pct", "max_drawdown_trigger", "theme_cap", "stop_loss_pct"]
    params: dict

def load_rules() -> list[Rule]: ...
def apply_rule(
    rule: Rule,
    weights: pd.Series,
    prices: pd.DataFrame,
    *, asof: pd.Timestamp,
) -> pd.Series: ...                              # returns adjusted weights

# engine.py
class BacktestResult(BaseModel):
    rule_name: str | None
    equity_eur: list[float]
    index: list[date]
    sharpe: float
    max_drawdown: float
    final_eur: float

def run_backtest(
    portfolio_initial_weights: pd.Series,
    prices_eur: pd.DataFrame,
    *, rule: Rule | None = None,
    rebalance: Literal["never", "monthly", "quarterly"] = "monthly",
    initial_eur: float = 100_000.0,
) -> BacktestResult: ...

def compare_rules(
    portfolio_initial_weights: pd.Series,
    prices_eur: pd.DataFrame,
    rules: list[Rule],
) -> list[BacktestResult]: ...

# walk_forward.py
def sweep_momentum_threshold(
    prices_eur: pd.DataFrame,
    *, windows: list[int] = [20, 60, 120],
    thresholds: list[float] = [0.0, 0.02, 0.05, 0.10],
) -> pd.DataFrame: ...                           # rows=window, cols=threshold, values=sharpe

def sweep_mean_reversion(
    prices_eur: pd.DataFrame, *, lookback: int = 20, z_thresholds: list[float] = [1.0, 1.5, 2.0],
) -> pd.DataFrame: ...

# metrics.py
def equity_delta(a: BacktestResult, b: BacktestResult) -> pd.Series: ...
def sharpe_delta(a: BacktestResult, b: BacktestResult) -> float: ...
```

#### Data sources
- `src.data.loaders.download_prices` (existing).
- `src.portfolio.risk.risk_metrics` for Sharpe/MDD.

#### Dependencies on other clusters
- None. Pure offline math on price panels.

#### Integration touchpoints (Phase 2)
- `app.py` — add sub-tab inside Portfolio tab named "Backtest" (or new top tab `tab_backtest`). Renders `render_rules_compare`, `render_walk_forward_heatmap`.
- `src/viz/dashboards.py` — UNCHANGED.

```python
# backtest/dashboards.py
def render_rules_compare(results: list[BacktestResult]) -> None: ...
def render_walk_forward_heatmap(grid: pd.DataFrame) -> None: ...
def render_rules_editor(rules: list[Rule]) -> list[Rule]: ...
```

#### Tests — `tests/test_backtest.py`
- `test_run_backtest_no_rule_equals_buy_and_hold`.
- `test_apply_rule_max_single_pct_caps_weight`.
- `test_apply_rule_theme_cap_redistributes`.
- `test_sweep_momentum_threshold_dims`.
- `test_sharpe_delta_sign`.

#### Complexity: **M**

#### Risks
1. Survivorship bias is real — disclaimer + note in UI.
2. Rebalance cadence vs daily compounding details — must document the convention chosen (end-of-month last available bar).
3. Walk-forward over short history (small caps with < 3y) produces spurious results — enforce min sample.

---

## 3. Dependency graph

```
                  +---------- common/schemas.py (created by Cluster 1) -----------+
                  |                |                |              |              |
            Cluster 1         Cluster 2         Cluster 5      Cluster 6     Cluster 7
            data_sec          macro/liq        trading        watchlist     backtest
              ^  ^                  ^               ^              ^
              |  |                  |               |              |
              |  +-----+---+-+------+--+            |              |
              |        |   |   |       |            |              |
              +------- Cluster 4 calendar/news -----+              |
                                ^                                  |
                                |                                  |
                                +------- Cluster 3 decision  ------+
                                          (consumes 1, 2, 4, 5)
```

- **Cluster 1, 2, 5, 6, 7** have NO inter-cluster dependencies (beyond shared schemas + existing src/*). They can run in parallel.
- **Cluster 4** soft-depends on Cluster 5 (`fetch_chain` for implied_move). Can develop against a stub function with the OptionContract signature.
- **Cluster 3** depends on Cluster 1 (dilution/runway), Cluster 2 (liquidity), Cluster 4 (catalyst), Cluster 5 (option chain). Must be last.

---

## 4. Vague schedule (parallel waves)

### Wave 1 (parallel — 5 agents in parallel)
- **Cluster 1** (data_sec) — also produces `src/common/schemas.py` (priority deliverable, day 1 morning, so others can import).
- **Cluster 2** (macro/liq)
- **Cluster 5** (trading)
- **Cluster 6** (watchlist)
- **Cluster 7** (backtest)

Rationale: zero inter-cluster code dependencies once schemas.py is on `main`. Cluster 1 should commit and push schemas.py FIRST (within 1h) so the other four agents can rebase and import it.

### Wave 2 (parallel — 2 agents)
- **Cluster 4** (calendar/news) — needs Cluster 5's `fetch_chain` to compute implied moves.
- **Cluster 3** (decision) — needs outputs of 1, 2, 4, 5.

Cluster 3 can start in Wave 1 against stubbed return shapes for `assess_dilution`/`assess_runway`/`liquidity_table`/`fetch_chain` — but its integration tests must be run in Wave 2.

### Wave 3 (single agent — main agent, Phase 2 integration)
- I (main agent) wire each cluster's `render_*` into `app.py` tabs.
- I do not touch any cluster's internal files.

---

## 5. Watchlists content (cluster 6 copies this verbatim into `config/watchlists.yaml`)

YAML structure: top-level keys `quantum`, `photonics`, `defense`. Each ticker entry carries `sub_theme`, `conviction`, `catalyst`, `peers`, plus the universe-metadata mini-block (`yfinance`, `alpaca`, `currency`, `region`, `isin?`, `name_hints?`, `theme`, `asset_class`) so loader can build a Portfolio stub without editing `universe.yaml`.

```yaml
quantum:
  IONQ:
    sub_theme: Trapped_Ion
    conviction: core
    catalyst: "AQ64 system deployment + DARPA QBI milestones 2026"
    peers: ["RGTI", "QBTS", "QUBT"]
    yfinance: IONQ
    alpaca: IONQ
    currency: USD
    region: US
    theme: Quantum
    asset_class: equity
  RGTI:
    sub_theme: Superconducting
    conviction: high
    catalyst: "Ankaa-3 + 84-qubit benchmark mid-2026; DARPA QBI Stage B selection"
    peers: ["IONQ", "QBTS"]
    yfinance: RGTI
    alpaca: RGTI
    currency: USD
    region: US
    theme: Quantum
    asset_class: equity
  QBTS:
    sub_theme: Annealing
    conviction: speculative
    catalyst: "Advantage2 commercial traction; AQC-2026 product announcements"
    peers: ["IONQ", "RGTI"]
    yfinance: QBTS
    alpaca: QBTS
    currency: USD
    region: US
    theme: Quantum
    asset_class: equity
  QUBT:
    sub_theme: Photonics_Quantum
    conviction: speculative
    catalyst: "TFLN foundry ramp; QAaaS revenue inflection"
    peers: ["IONQ", "IBM", "GOOG"]
    yfinance: QUBT
    alpaca: QUBT
    currency: USD
    region: US
    theme: Quantum
    asset_class: equity
  ARQQ:
    sub_theme: Post_Quantum_Crypto
    conviction: medium
    catalyst: "NIST PQC standard rollouts; defense contracts 2026"
    peers: ["IONQ"]
    yfinance: ARQQ
    alpaca: ARQQ
    currency: USD
    region: US
    theme: Quantum
    asset_class: equity
  IBM:
    sub_theme: Big_Tech_Quantum_Adjacent
    conviction: medium
    catalyst: "Quantum System Two; Heron r2 + Condor follow-up"
    peers: ["GOOG", "MSFT"]
    yfinance: IBM
    alpaca: IBM
    currency: USD
    region: US
    theme: Quantum
    asset_class: equity
  HON:
    sub_theme: Big_Tech_Quantum_Adjacent
    conviction: medium
    catalyst: "Quantinuum IPO timing (currently private — see pre_ipo list)"
    peers: ["IBM"]
    yfinance: HON
    alpaca: HON
    currency: USD
    region: US
    theme: Quantum
    asset_class: equity
  QTUM:
    sub_theme: ETF
    conviction: core
    catalyst: "thematic flow proxy; rebalances quarterly"
    peers: []
    yfinance: QTUM
    alpaca: QTUM
    currency: USD
    region: US
    theme: Quantum
    asset_class: etf

photonics:
  AAOI:
    sub_theme: Datacenter_Optics
    conviction: core
    catalyst: "Hyperscaler 1.6T transceiver ramps; Microsoft design wins"
    peers: ["COHR", "LITE", "FN"]
    yfinance: AAOI
    alpaca: AAOI
    currency: USD
    region: US
    theme: Photonics
    asset_class: equity
  COHR:
    sub_theme: Datacenter_Optics
    conviction: high
    catalyst: "EML laser shortage premium; AI optics share gains"
    peers: ["AAOI", "LITE", "FN"]
    yfinance: COHR
    alpaca: COHR
    currency: USD
    region: US
    theme: Photonics
    asset_class: equity
  LITE:
    sub_theme: Datacenter_Optics
    conviction: high
    catalyst: "Indium phosphide capacity build; cloud capex tailwind"
    peers: ["AAOI", "COHR", "FN"]
    yfinance: LITE
    alpaca: LITE
    currency: USD
    region: US
    theme: Photonics
    asset_class: equity
  FN:
    sub_theme: Datacenter_Optics
    conviction: medium
    catalyst: "Nvidia partner; CPO transition"
    peers: ["AAOI", "COHR", "LITE"]
    yfinance: FN
    alpaca: FN
    currency: USD
    region: US
    theme: Photonics
    asset_class: equity
  ANET:
    sub_theme: Networking_Photonics
    conviction: medium
    catalyst: "800G + 1.6T deployment cadence"
    peers: ["CSCO", "NVDA"]
    yfinance: ANET
    alpaca: ANET
    currency: USD
    region: US
    theme: Photonics
    asset_class: equity
  MRVL:
    sub_theme: Optical_DSP
    conviction: high
    catalyst: "Custom AI silicon ramp; PAM4 DSP share"
    peers: ["AVGO", "NVDA"]
    yfinance: MRVL
    alpaca: MRVL
    currency: USD
    region: US
    theme: Photonics
    asset_class: equity
  IPGP:
    sub_theme: Industrial_Lasers
    conviction: medium
    catalyst: "Cyclical recovery; defense laser demand"
    peers: ["COHR"]
    yfinance: IPGP
    alpaca: IPGP
    currency: USD
    region: US
    theme: Photonics
    asset_class: equity
  NVMI:
    sub_theme: Metrology_Photonics
    conviction: medium
    catalyst: "Advanced packaging metrology pull-through"
    peers: ["KLAC"]
    yfinance: NVMI
    alpaca: NVMI
    currency: USD
    region: US
    theme: Photonics
    asset_class: equity
  POET:
    sub_theme: Silicon_Photonics
    conviction: speculative
    catalyst: "Optical interposer commercial sampling; CPO partnerships"
    peers: ["AAOI", "LITE"]
    yfinance: POET
    alpaca: POET
    currency: USD
    region: US
    theme: Photonics
    asset_class: equity

defense:
  KTOS:
    sub_theme: Drones_Defense
    conviction: high
    catalyst: "Valkyrie + Athena CCA; DoD FY27 budget pull-through"
    peers: ["AVAV", "PLTR"]
    yfinance: KTOS
    alpaca: KTOS
    currency: USD
    region: US
    theme: Defense
    asset_class: equity
  AVAV:
    sub_theme: Drones_Defense
    conviction: high
    catalyst: "Switchblade restocks; Ukraine + Pacific theatre"
    peers: ["KTOS"]
    yfinance: AVAV
    alpaca: AVAV
    currency: USD
    region: US
    theme: Defense
    asset_class: equity
  LMT:
    sub_theme: Prime_Defense
    conviction: medium
    catalyst: "F-35 sustainment + missile defense"
    peers: ["RTX", "NOC"]
    yfinance: LMT
    alpaca: LMT
    currency: USD
    region: US
    theme: Defense
    asset_class: equity
  NOC:
    sub_theme: Prime_Defense
    conviction: medium
    catalyst: "B-21 ramp; Sentinel ICBM"
    peers: ["LMT", "RTX"]
    yfinance: NOC
    alpaca: NOC
    currency: USD
    region: US
    theme: Defense
    asset_class: equity
  HEI:
    sub_theme: Aerospace_Parts
    conviction: medium
    catalyst: "Aftermarket margin expansion"
    peers: ["TDG"]
    yfinance: HEI
    alpaca: HEI
    currency: USD
    region: US
    theme: Defense
    asset_class: equity
  PLTR:
    sub_theme: Defense_Software
    conviction: speculative
    catalyst: "DoD AIP expansion; allied governments adoption"
    peers: ["MSFT"]
    yfinance: PLTR
    alpaca: PLTR
    currency: USD
    region: US
    theme: Defense
    asset_class: equity
```

For `config/private_watchlist.yaml` (Cluster 6 — module L):

```yaml
private:
  SpaceX:
    sub_theme: Launch_Constellation
    last_valuation_usd_b: 350.0
    last_round_date: 2025-12-01
    last_round_stage: "Secondary tender"
    listed_proxies: ["RKLB", "ASTS", "BKSY", "RDW", "ARKX"]
    notes: "Use ARKX + RKLB + ASTS as listed proxy basket."
  PsiQuantum:
    sub_theme: Photonics_Quantum
    last_valuation_usd_b: 6.0
    last_round_date: 2024-09-01
    last_round_stage: "Series E"
    listed_proxies: ["IONQ", "RGTI", "QUBT", "QTUM"]
  Pasqal:
    sub_theme: Neutral_Atom_Quantum
    last_valuation_usd_b: 0.5
    last_round_date: 2024-01-01
    last_round_stage: "Series B"
    listed_proxies: ["IONQ", "QTUM"]
  Helion:
    sub_theme: Fusion
    last_valuation_usd_b: 5.4
    last_round_date: 2025-01-01
    last_round_stage: "Series F"
    listed_proxies: ["CCJ", "BWXT"]
  Vast:
    sub_theme: Space_Station
    last_valuation_usd_b: 1.0
    last_round_date: 2024-06-01
    last_round_stage: "Series A extension"
    listed_proxies: ["RKLB", "RDW"]
  Astranis:
    sub_theme: Satellites
    last_valuation_usd_b: 1.6
    last_round_date: 2024-03-01
    last_round_stage: "Series D"
    listed_proxies: ["ASTS", "BKSY", "RKLB"]
  Stoke:
    sub_theme: Launch
    last_valuation_usd_b: 0.5
    last_round_date: 2025-04-01
    last_round_stage: "Series C"
    listed_proxies: ["RKLB"]
  IQM:
    sub_theme: Superconducting_Quantum
    last_valuation_usd_b: 0.4
    last_round_date: 2024-03-01
    last_round_stage: "Series A2"
    listed_proxies: ["IONQ", "RGTI", "QTUM"]
  Quantinuum:
    sub_theme: Trapped_Ion_Quantum
    last_valuation_usd_b: 5.0
    last_round_date: 2025-01-01
    last_round_stage: "Series B"
    listed_proxies: ["HON", "IONQ", "QTUM"]
  Atom_Computing:
    sub_theme: Neutral_Atom_Quantum
    last_valuation_usd_b: 0.3
    last_round_date: 2024-01-01
    last_round_stage: "Series B"
    listed_proxies: ["IONQ", "QTUM"]
```

Notes — values are approximations rounded to one decimal `usd_b` and dates rounded to month. Cluster 6 must include a `notes` field reading "valuations approximated, refresh manually" in the loader to flag user-side maintenance.

---

## 6. Risks & open questions (top 5)

1. **Alpaca options entitlement** — free tier supports only US listings since Feb-2024 with greeks; if the user's plan is the very basic data subscription, several endpoints return 403. yfinance fallback must compute greeks via BS inverse and the latency penalty has to be acceptable (~0.5s per chain). Verify entitlement before Cluster 5 commits.
2. **SEC + SAM.gov reliability** — both endpoints intermittently return 403/429. Cluster 1 must (a) honour the SEC 10 req/s rate limit, (b) ALWAYS pass a `User-Agent: quant-terminal <SEC_EMAIL>` header, (c) cache aggressively (24h TTL). If `SEC_EMAIL` is missing, modules must degrade gracefully — return empty DataFrames with a warning, not crash.
3. **Shared schemas commit ordering** — Cluster 1 MUST commit `src/common/schemas.py` first and push to main within the first hour so the other four agents can rebase. If Cluster 1 starts late, the dependency graph collapses to sequential. Mitigation: I (main) pre-create an empty `src/common/schemas.py` with stubs ahead of Wave 1 kickoff.
4. **Universe.yaml lock-in** — watchlist tickers not in universe.yaml (RGTI, QBTS, QUBT, ARQQ, COHR, LITE, FN, KTOS, AVAV, IBM, etc.) cannot be added by Cluster 6 (prohibited file). Cluster 6 must carry the same metadata fields IN watchlists.yaml and bypass `Portfolio._enrich` for these — return a DataFrame with all enrichment columns pre-populated. Document this clearly in `src/watchlist/loader.py` docstring.
5. **Streamlit state explosion** — 7 new tabs and the trade-ticket form (Cluster 5) will introduce stateful widgets. Each cluster's render function MUST use unique `key=` prefixes (`key=f"trading_ticket_{ticker}"`, `key=f"journal_close_{trade_id}"`, etc.) to avoid Streamlit DuplicateWidgetID errors. I (main) will audit this during Phase 2 integration but each cluster owner is responsible for namespacing within their dashboards.py.

Additional open questions to flag back to the user before kickoff:
- Do we want a separate "watchlist universe expansion" PR before Phase 1, OR do we accept the duplication of metadata in watchlists.yaml? (Current plan accepts duplication.)
- For the trading journal — single broker account or multi-account? Plan assumes single, EUR-denominated.
- Confirm SEC_EMAIL is set in `.env`. Without it, Cluster 1 modules produce empty output.

---

End of plan. Ready for cluster agents to fan out.