# Quant Terminal — Dashboard Documentation

**Institutional-grade portfolio analytics, options trading bench, smart-money tracking, regime detection and event-driven execution — all in one Streamlit app.**

---

## Table of Contents

- [Overview](#overview)
- [Architecture](#architecture)
- [Data sources](#data-sources)
- [Sidebar](#sidebar)
- [The 16 tabs](#the-16-tabs)
  1. [📈 Portfolio Analytics](#1--portfolio-analytics)
  2. [🎯 Trading Bench](#2--trading-bench)
  3. [🛰️ Watchlists](#3-️-watchlists)
  4. [🌐 Macro & Regime](#4--macro--regime)
  5. [💸 Smart-Money & Fundamentals](#5--smart-money--fundamentals)
  6. [🧠 Decision Support](#6--decision-support)
  7. [📅 Catalysts & News](#7--catalysts--news)
  8. [🎬 Event Trading](#8--event-trading)
  9. [📒 Backtest](#9--backtest)
  10. [🔔 Alerts](#10--alerts)
  11. [📡 Execution](#11--execution)
  12. [📊 Snapshot & Tax](#12--snapshot--tax)
  13. [🔥 Short Squeeze Scanner](#13--short-squeeze-scanner)
  14. [🌀 HMM Regime Engine](#14--hmm-regime-engine)
  15. [🤖 Kalman Elastic Trading](#15--kalman-elastic-trading)
  16. [☀️ Daily Brief](#16-️-daily-brief)
- [Configuration files](#configuration-files)
- [Secrets / API keys](#secrets--api-keys)
- [Setup / Run / Deploy](#setup--run--deploy)
- [Caching](#caching)
- [Testing](#testing)

---

## Overview

The Quant Terminal is built for an **event-driven options trader** focused on tech, space, uranium and quantum small-caps. The product surfaces, in one screen:

- **Portfolio risk** marked in EUR across DEGIRO holdings
- **Live options chains** with Greeks, IV analytics, GEX dealer-positioning
- **Smart-money signals** from SEC EDGAR (Form 4 insider, 13F institutional, dilution radar)
- **Catalysts** — earnings, macro events, satellite launches
- **News pulse** — RSS + sentiment + LLM summaries + Stocktwits cashtag
- **Decision support** — conviction matrix, VaR-contribution sizing, hedge cost
- **Execution** via Alpaca paper/live OMS
- **Persistence** — snapshots, tax lots (FIFO, French PFU 30%), trade journal
- **Regime engine** — HMM volatility-state detection
- **Daily AI brief** — Claude-generated morning summary

Total: **16 top-level tabs**, **70+ sub-tabs**, **~25,000 lines of Python**, **166 passing tests**.

---

## Architecture

```
quant_terminal/
├── app.py                          # Main Streamlit entry — 2,500 lines, all tab wiring
├── pyproject.toml                  # Deps, pin Python 3.11
├── requirements.txt                # Streamlit Cloud install file
├── runtime.txt                     # Pin python-3.11 for Streamlit
├── .streamlit/
│   ├── config.toml                 # Dark theme + headless server settings
│   └── secrets.toml.example        # Template for API keys
├── config/                         # YAML config — editable without touching code
│   ├── universe.yaml               # Ticker → broker symbol + currency + theme map
│   ├── watchlists.yaml             # Quantum / photonics / defense baskets
│   ├── surveillance.yaml           # Free-form user watchlist (Stocktwits, news)
│   ├── bookmarks.yaml              # Pinned tickers in the sidebar
│   ├── trading_watchlist.yaml      # Futures + sector ETFs cross-asset board
│   ├── risk_limits.yaml            # VaR cap, concentration, sector caps
│   ├── alerts.yaml                 # Alert triggers + dispatcher channels
│   ├── execution.yaml              # Pre-trade gates + paper/live mode defaults
│   ├── hedge_defaults.yaml         # Collar offsets + linear hedge alternatives
│   ├── macro_calendar_2026.yaml    # FOMC / ECB / OPEC dates
│   ├── launches_2026.yaml          # Rocket launch schedule
│   ├── dod_programs.yaml           # US DoD program → ticker exposure
│   ├── hyperscaler_capex.yaml      # AWS / Azure / GCP quarterly capex
│   ├── hf_registry.yaml            # Hedge fund 13F filers tracked
│   ├── private_watchlist.yaml      # Pre-IPO names + signals
│   ├── conviction_weights.yaml     # Conviction axis weights
│   └── settings.yaml               # Cache dirs, history horizons, FX defaults
├── src/                            # Python sources (DON'T touch backend without good reason)
│   ├── alerts/                     # Trigger engine + Discord/Email/Telegram channels
│   ├── analytics/                  # Risk metrics, betas, scenarios
│   ├── backtest/                   # Rules engine + walk-forward simulator
│   ├── calendar_engine/            # Earnings, macro events, launches, implied moves
│   ├── common/                     # Shared pydantic schemas
│   ├── data/                       # Loaders (Alpaca, yfinance), FX, FRED, FMP analyst ratings
│   ├── data_sec/                   # EDGAR client + Form 4 / 13F / XBRL parsers
│   ├── decision/                   # Conviction, hedge cost, sizing, journal
│   ├── event_trading/              # Pre-event wizard + earnings simulator
│   ├── execution/                  # Alpaca OMS + validators + audit log
│   ├── kalman/                     # Read-only loader for Kalman pipeline artefacts
│   ├── liquidity/                  # ADV, borrow rate, slippage estimator
│   ├── macro/                      # FRED panel, regime classifier, pair screener
│   ├── news/                       # RSS, sentiment, LLM, Stocktwits, daily brief
│   ├── portfolio/                  # Position model, Greeks aggregator
│   ├── regime/                     # HMM volatility engine + sizing nudge
│   ├── scanners/                   # Short-squeeze quick scan + legacy 4-pillar adapter
│   ├── snapshot/                   # Daily portfolio capture + replay
│   ├── tax/                        # FIFO lots + realised P&L + 2074-CMV export
│   ├── trading/                    # Options chain · GEX · IV · live book · IV crush
│   ├── utils/                      # config / cache / logging primitives
│   ├── viz/                        # Theme, palette, reusable HTML builders
│   └── watchlist/                  # Loader, enricher, surveillance, trading_board, bookmarks
├── vendor/
│   └── legacy_squeeze/             # Read-only mirror of the short-squeeze-scanner project
└── tests/                          # 166 pytest test cases
```

---

## Data sources

| Source | Endpoint / Lib | Used for | Auth |
|---|---|---|---|
| **Alpaca Markets** | `alpaca-py` SDK | Spot prices, options chains + Greeks, OMS execution | `APCA_API_KEY_ID` + `APCA_API_SECRET_KEY` |
| **yfinance** | `yfinance` lib | Fallback prices, options OI, history, fast_info | none |
| **SEC EDGAR** | `data.sec.gov` REST | Form 4, 13F, S-3, SHO threshold list, XBRL facts | `SEC_EMAIL` (UA header) |
| **FRED** | `fredapi` | Macro time series (CPI, NFP, yield curve) | `FRED_API_KEY` (free) |
| **FMP** | REST API | Earnings dates, analyst ratings, price targets | `FMP_API_KEY` (free tier) |
| **Finviz** | HTML scrape | Short-squeeze screener | none |
| **Google News** | RSS | Per-ticker news headlines | none |
| **Stocktwits** | Free REST API | Cashtag posts + bull/bear sentiment | none |
| **Anthropic Claude** | `anthropic` SDK | Transcript summary, news bursts, daily brief | `ANTHROPIC_API_KEY` |
| **DEGIRO** | CSV / XLSX export | Local portfolio positions | manual upload |
| **TradingView** | Free embed widget | Advanced charts (RSI / MACD / BB) | none |

Resolution order for prices is: **Alpaca → yfinance fallback → cached parquet → empty**.

---

## Sidebar

The sidebar is split in 6 grouped sections:

1. **Brand identity** — logo + version pill
2. **Data sources status** — pills showing Alpaca/SEC/FRED keys configured
3. **Portfolio input** — DEGIRO CSV/XLSX uploader
4. **Analysis window** — start/end date pickers (default = last 3y)
5. **Live mode** — auto-refresh selector (Off / 15s / 30s / 60s / 5min) with `streamlit-autorefresh`. Cache TTLs tighten in live mode.
6. **Bookmarks** — pinned tickers chips + edit expander (persisted to `config/bookmarks.yaml`)

A footer at the bottom shows build info.

---

## The 16 tabs

### 1. 📈 Portfolio Analytics

Loaded **only after DEGIRO upload**. Otherwise shows an empty-state card.

**Sub-tabs**:
- **Overview** — allocation panels (by theme / by sector / by region), holdings table, EUR equity curve + drawdown
- **Risk engine** — Sharpe, Sortino, max DD, VaR 95/99 historical + parametric, CVaR. Limit-violations check against `config/risk_limits.yaml`
- **Greeks** — aggregated portfolio Greeks (stocks treated as Δ=1, options pulled from journal). Beta-weighted Δ vs SPY.
- **Factors & correlations** — rolling correlations to SPY / TLT / GLD / DXY, factor regressions, beta tables
- **Scenarios** — stress tests (2008 / COVID / 2022 / +1σ macro shock) applied to current weights
- **Position explorer** — per-ticker price chart (lightweight-charts or Plotly fallback)

**Key modules**: `src/portfolio/`, `src/analytics/`, `src/data/loaders.py`, `src/data/fx.py`

### 2. 🎯 Trading Bench

The trading workhorse — 10 sub-tabs.

- **🎯 Universe Scanner** — scans the default universe (sector ETFs + portfolio tickers) for best Δ-25 setups. Score = low-IV bias + negative-gamma zone hit + extreme P/C ratio.
- **Chain Explorer** — full option chain for the selected ticker, sortable, with the Δ-25 strikes highlighted
- **GEX+ (max pain · P/C · skew)** — net Gamma Exposure profile per strike + max pain + P/C ratio + 25Δ IV skew + gamma flip strike. Diagnostic message when chain lacks Greeks/OI
- **IV Analytics** (4 sub-sub-tabs):
  - *Term structure* — ATM IV vs DTE
  - *Vol smile* — IV per strike at chosen expiry, call vs put
  - *RV vs IV* — Yang-Zhang realised vol vs ATM IV + premium %
  - *🧊 Vol Surface 3D* — Plotly 3D surface (DTE × moneyness × IV), call/put toggle
- **Trade Ticket** — composer for a long-call / long-put. Pre-trade gates: debit cap, IV-rank, OI. Inline HMM regime-sizing pill above the form.
- **Journal** — open + closed trades from `data/trading_journal/trades.parquet`
- **📡 Live Book** — refresh-able book monitor: per-position card (P&L, DTE, Greeks, theta burn, breakeven distance) + aggregate Greeks across the open book + P&L distribution chart
- **💥 IV Crush** — earnings IV crush forecaster. Project post-event premium given a crush ratio; solve for breakeven spot move; sensitivity grid across 30%→70% crush
- **Squeeze Score** — chain-derived composite gamma-squeeze score for the selected ticker; surfaces the latest persisted SHO+Finviz scan
- **🌐 Surveillance Trading** — cross-asset board from `config/trading_watchlist.yaml` (index futures, commodity futures, rates/FX, sector ETFs, thematic ETFs, broad benchmarks). Cards view with sparkline + RSI gauge + range bar + ATR & trend pills, or compact table view.

**Key modules**: `src/trading/options_chain.py`, `src/trading/gex.py`, `src/trading/gex_enrich.py`, `src/trading/iv_analytics.py`, `src/trading/vol_surface.py`, `src/trading/live_book.py`, `src/trading/iv_crush.py`, `src/trading/universe_scanner.py`, `src/trading/squeeze_score.py`, `src/trading/journal.py`, `src/trading/trade_ticket.py`

### 3. 🛰️ Watchlists

Themed lists with conviction tags + catalysts.

- **Quantum** — IONQ, RGTI, QUBT, ...
- **Photonics** — AAOI, COHR, IPGP, ...
- **Defense** — LMT, RTX, NOC, ASTS, RKLB, BWXT, ...
- **Pre-IPO** — Anthropic, SpaceX, Stripe (info only, no quotes)
- **🕵️ Surveillance editor** (bottom) — free-form ticker list (textarea + save button), persisted to `config/surveillance.yaml`. Consumed by Stocktwits + Daily Brief.

**Key modules**: `src/watchlist/loader.py`, `src/watchlist/enricher.py`, `src/watchlist/private.py`, `src/watchlist/surveillance.py`, `src/watchlist/dashboards.py`

### 4. 🌐 Macro & Regime

4 sub-tabs:

- **Regime** — 2×2×2 macro regime (growth × inflation × liquidity) classified from FRED panel + history
- **Correlations** — rolling 30/60/90d correlations across asset classes
- **Pair Screener** — z-score pair-trade screener with cointegration test
- **Liquidity** — global liquidity radar (USD index, financial conditions, repo rates)

**Key modules**: `src/macro/fred_series.py`, `src/macro/regime.py`, `src/macro/correlations.py`, `src/macro/pair_screener.py`, `src/liquidity/`

### 5. 💸 Smart-Money & Fundamentals

7 sub-tabs:

- **🌐 Overview** — cross-ticker pull aggregating insider transactions, dilution risk, runway, KPI strip
- **Insider (Form 4)** — per-ticker recent insider buys/sells with cluster detection
- **Dilution Radar** — flags S-3 ATM shelf filings, secondary offerings, dilution score 1-5
- **Cash Runway** — quarters of cash burn left, based on latest XBRL filings
- **ETF Flows** — signed turnover proxy on thematic ETFs (URA, ARKX, QTUM, XLE, GDX, SMH)
- **Gov Contracts** — SAM.gov awards + DoD program allocations + hyperscaler capex
- **Hyperscaler Capex** — quarterly capex tracking (Microsoft, Google, Amazon, Meta)

**Key modules**: `src/data_sec/`, `src/data_sec/overview.py`, `src/data_sec/sam_gov.py`, `src/data_sec/hyperscaler_capex.py`, `src/data_sec/dod_budget.py`

### 6. 🧠 Decision Support

3 sub-tabs:

- **Conviction & Sizing** — conviction matrix per position (5 axes: thesis, downside, liquidity, catalyst, composite) + Kelly/4 suggested weights. VaR-contribution trim suggestions. Risk-parity preview. Inline explainer for each axis source.
- **Thesis Journal** — write/update per-ticker theses (persisted to `data/decision/journal.parquet`)
- **Hedge Cost** — protective collar pricer (long OTM put + short OTM call, same expiry) + linear alternatives table (vanilla ETFs / futures) read from `config/hedge_defaults.yaml` (25 tickers mapped)

**Key modules**: `src/decision/conviction.py`, `src/decision/hedge_cost.py`, `src/decision/var_contribution_sizing.py`, `src/decision/journal_store.py`, `src/decision/rerating_score.py`, `src/decision/risk_parity_preview.py`

### 7. 📅 Catalysts & News

9 sub-tabs:

- **Catalyst Calendar** — all upcoming events (earnings + macro + launches) in a unified view
- **Earnings** — earnings dates + implied move + post-earnings drift historical
- **Macro Board** — FOMC, ECB, OPEC, NFP, CPI dates 2026
- **Launches** — rocket launches with affected tickers (RKLB, ASTS, BKSY, ...)
- **News Flow** — Google News RSS pulled per ticker, scored by sentiment, displayed as heatmap + feed
- **💬 Stocktwits cashtag** — free Stocktwits API for cashtag posts; covers portfolio ∪ surveillance tickers
- **🤖 Transcript LLM** — paste an earnings transcript → Claude returns beats/misses/guidance/sentiment/quotes
- **📡 Live news** — pulls past N hours of RSS, scores sentiment, **fires alerts** when net sentiment crosses thresholds
- **📈 Analyst ratings** — FMP upgrades/downgrades + consensus targets for portfolio ∪ surveillance

**Key modules**: `src/calendar_engine/`, `src/news/`, `src/data/analyst_ratings.py`

### 8. 🎬 Event Trading

2 sub-tabs:

- **Pre-event wizard** — for each upcoming catalyst, surfaces the best Δ-25 long call / put candidates with debit cost + IV + breakeven
- **Earnings simulator** — spot/IV shock grid: "if spot moves ±10% and IV crushes 50%, what's the P&L on this contract?"

**Key modules**: `src/event_trading/pre_event_wizard.py`, `src/event_trading/earnings_simulator.py`

### 9. 📒 Backtest

Apply rule sets to the loaded portfolio + window. Rules: max single position, max drawdown, stop-loss, momentum entry, etc. Compare baseline vs ruled equity curves + metrics diff.

**Key modules**: `src/backtest/engine.py`, `src/backtest/rules.py`, `src/backtest/metrics_diff.py`, `src/backtest/optimizer.py`

### 10. 🔔 Alerts

2 sub-tabs:

- **Triggers** — list of all alert rules from `config/alerts.yaml` (price thresholds, VaR breaches, drawdown, news sentiment, regime switch)
- **History** — last 100 fired alerts

Channels: Streamlit toast, Discord webhook, Telegram bot, Email SMTP. Each trigger evaluates on every refresh in live mode.

**Key modules**: `src/alerts/engine.py`, `src/alerts/triggers.py`, `src/alerts/channels.py`, `src/alerts/state.py`

### 11. 📡 Execution

Alpaca OMS integration. 4 sub-tabs:

- **Pre-trade** — order ticket with validators (notional cap, max position size, market hours)
- **Positions** — current Alpaca account positions, reconciled vs internal journal
- **Order history** — past orders with status (filled/cancelled/rejected)
- **Audit log** — immutable log of every OMS interaction

Defaults to **paper trading**. `EXECUTION_ALLOW_LIVE=0` is the safety latch.

**Key modules**: `src/execution/alpaca_broker.py`, `src/execution/oms.py`, `src/execution/validators.py`, `src/execution/modes.py`, `src/execution/positions.py`

### 12. 📊 Snapshot & Tax

5 sub-tabs:

- **Snapshot history** — daily portfolio snapshots (NAV, holdings, prices) stored in `data/snapshots/`
- **Replay a snapshot** — load a past snapshot and see the portfolio as it was that day
- **Tax lots** — FIFO lot tracker per ticker in EUR
- **Realised P&L** — closed trades with per-sale cost basis, formatted for French PFU 30% (form 2074-CMV)
- **Import / Manual** — CSV importer + manual lot/sale entry forms

**Key modules**: `src/snapshot/capture.py`, `src/snapshot/store.py`, `src/tax/lots.py`, `src/tax/importer.py`

### 13. 🔥 Short Squeeze Scanner

2 sub-tabs:

- **⚡ Quick scan (SHO + Finviz)** — SEC SHO threshold list intersected with Finviz high-short-float screener
- **🏛️ Legacy 4-pillar deep scan** — vendored from a standalone scanner project. 3 modes:
  - *Single ticker* — score one symbol
  - *From a list* — score N symbols
  - *Full Finviz screen* (slow, 3-8 min) — full universe scrape

  4 pillars (each 0-4): VAD structure (SI%, DTC, borrow, util) · Institutional (Inst Trans, 13F δ, Call OI Δ, P/C ratio) · Divergence · Technical (TTM squeeze, OBV, Keltner, vol spike, RSI, VWAP).

  Drill-down view per ticker with TradingView Advanced Chart + live GEX + per-pillar details.

**Key modules**: `src/scanners/short_squeeze.py`, `src/scanners/legacy_pipeline.py`, `src/scanners/squeeze_zoom.py`, `vendor/legacy_squeeze/`

### 14. 🌀 HMM Regime Engine

Gaussian Hidden Markov Model on benchmark log-returns. Configurable: ticker (SPY / QQQ / IWM / ^VIX / TLT / GLD / XLE / XLF), states (2-4), lookback (252-2000 days), feature (abs / sq / raw).

Renders:
- Hero badge with current regime + posterior probability
- Stacked-area posterior probabilities over time
- Price chart overlaid with regime ribbon (color per state)
- Transition matrix heatmap
- State stats table (mean return, σ, long-run frequency, expected duration)
- Model diagnostics (convergence, log-likelihood, AIC, BIC)

**Key modules**: `src/regime/hmm.py`, `src/regime/hmm_dashboards.py`

### 15. 🤖 Kalman Elastic Trading

Read-only viewer over artefacts from a separate Kalman pipeline (lives in `quant_terminal/data/kalman_artefacts/` or env-overridden path). Shows equity curve, trades, Phase 2 / Phase 3 metrics if available.

**Key modules**: `src/kalman/loader.py`

### 16. ☀️ Daily Brief

LLM-generated morning summary. Pulls together:
- Open positions snapshot (journal)
- Portfolio NAV + P&L
- Catalysts today + this week
- News headlines past 24h
- HMM regime + probabilities

Sends to Anthropic Claude (model `ANTHROPIC_MODEL`, default `claude-sonnet-4-5`) with a structured prompt. Output: 5-section Markdown brief — Book status / Catalysts today / News pulse / Regime & risk / Recommended actions.

**Falls back to data-only Markdown** when `ANTHROPIC_API_KEY` not set. Cached 1 hour by context hash (so opening the dashboard multiple times in the morning doesn't burn LLM quota). Regenerate button wipes the cache.

**Key modules**: `src/news/daily_brief.py`

---

## Configuration files

All in `quant_terminal/config/`. YAML, hot-editable (no restart needed for most).

| File | What it controls |
|---|---|
| `universe.yaml` | Per-ticker: Alpaca symbol, yfinance symbol, currency, ISIN, name hints, theme, region, asset class |
| `watchlists.yaml` | Public themed lists (quantum / photonics / defense) |
| `private_watchlist.yaml` | Pre-IPO names + signals (info only) |
| `surveillance.yaml` | Free-form ticker list for Stocktwits / news / Daily Brief |
| `bookmarks.yaml` | Pinned tickers in sidebar |
| `trading_watchlist.yaml` | Cross-asset board groups (futures, sector ETFs, etc.) |
| `risk_limits.yaml` | VaR cap, max single position %, sector concentration cap |
| `alerts.yaml` | Trigger rules + channels |
| `execution.yaml` | Pre-trade gates, paper/live mode default |
| `hedge_defaults.yaml` | Collar offsets + per-ticker linear hedge alternatives (25 mapped) |
| `macro_calendar_2026.yaml` | Macro events for the year |
| `launches_2026.yaml` | Rocket launches |
| `dod_programs.yaml` | DoD programs and ticker exposure |
| `hyperscaler_capex.yaml` | AWS/GCP/Azure quarterly capex |
| `hf_registry.yaml` | 13F filers tracked |
| `conviction_weights.yaml` | Weights for the conviction composite |
| `settings.yaml` | Cache dir, history years, FX defaults |

---

## Secrets / API keys

Templated in `quant_terminal/.streamlit/secrets.toml.example`. Set them on Streamlit Cloud → App settings → Secrets (or in a local `.env` for development).

| Variable | Required? | Used by |
|---|---|---|
| `APCA_API_KEY_ID` / `APCA_API_SECRET_KEY` | recommended | Alpaca chains, execution, OI fallback |
| `APCA_API_BASE_URL` | optional | Defaults to paper API |
| `SEC_EMAIL` | recommended | EDGAR User-Agent header (avoids 403) |
| `FRED_API_KEY` | recommended | Macro tab |
| `FMP_API_KEY` | optional | Earnings + analyst ratings |
| `ANTHROPIC_API_KEY` | optional | Transcript LLM + Daily Brief |
| `ANTHROPIC_MODEL` | optional | Default `claude-sonnet-4-5` |
| `DISCORD_WEBHOOK_URL` | optional | Alerts dispatcher |
| `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID` | optional | Alerts dispatcher |
| `ALERT_SMTP_*` | optional | Email alerts |
| `EXECUTION_ALLOW_LIVE` | optional | **Keep at `"0"` to prevent live trades** |

**Never commit a real secrets.toml.** The `.gitignore` covers `quant_terminal/.streamlit/secrets.toml`.

---

## Setup / Run / Deploy

### Local

```bash
git clone https://github.com/PokiCodeLonggamma/portfolio-quant-terminal
cd portfolio-quant-terminal/quant_terminal
cp .env.example .env                 # fill in your API keys
pip install -e .                     # editable install (uses pyproject.toml)
streamlit run app.py                 # opens http://localhost:8501
```

Python **3.11 or 3.12** required (pinned in `pyproject.toml` and `runtime.txt`). 3.13 / 3.14 untested — scipy / pyarrow wheels may not exist.

### Streamlit Cloud

1. https://share.streamlit.io → **Create app**
2. Repo: `PokiCodeLonggamma/portfolio-quant-terminal`
3. Branch: `main`
4. Main file path: `quant_terminal/app.py`
5. **Advanced settings → Python version: 3.11** (CRITICAL — Streamlit Cloud sometimes defaults to 3.14 which breaks scipy)
6. **Secrets** → paste from `.streamlit/secrets.toml.example` with your real keys
7. Deploy

Build takes ~5 minutes (scipy + lxml + pyarrow + hmmlearn compile).

### Tests

```bash
cd quant_terminal
python -m pytest tests/              # 166 tests
python -m pytest tests/ -k trading   # subset
python -m ruff check .               # lint
```

---

## Caching

Two layers:

1. **Streamlit `@st.cache_data` / `@st.cache_resource`** — per-session in-memory, TTL set per call (5 min in live mode, 30 min standard, 6 h for static reference data).

2. **Parquet on disk** — `src/utils/cache.py` writes to `data/cache/<namespace>/<key>.parquet`. Survives session boundaries but **not** Streamlit Cloud container restarts (filesystem is ephemeral).

Important: **journal, snapshots, tax lots, surveillance, bookmarks** are NOT cache — they are source-of-truth files under `data/` and `config/`. On Streamlit Cloud they reset on container redeploy unless backed by external storage (Postgres / S3).

---

## Testing

166 pytest test cases, organized by module:

```
tests/
├── test_alerts.py              # 11 tests
├── test_backtest.py            # 18 tests
├── test_calendar_news.py       # 15 tests
├── test_decision.py            # 22 tests
├── test_event_trading.py       # 7 tests
├── test_execution.py           # 12 tests
├── test_liquidity.py           # 10 tests
├── test_macro_regime.py        # 14 tests
├── test_portfolio.py           # 1 test
├── test_portfolio_greeks.py    # 11 tests
├── test_snapshot.py            # 6 tests
├── test_tax_lots.py            # 7 tests
├── test_trading.py             # 21 tests
└── test_watchlist.py           # 11 tests
```

CI runs lint (ruff) + compile-sweep + tests matrix (Python 3.11 + 3.12) + CodeQL on every PR. See `.github/workflows/`.

---

## Quick reference — where to do what

| I want to... | Go to |
|---|---|
| Check my portfolio NAV + risk | 📈 Portfolio → Overview |
| Place an options trade | 🎯 Trading Bench → Trade Ticket |
| See open positions live | 🎯 Trading Bench → 📡 Live Book |
| Project the earnings IV crush | 🎯 Trading Bench → 💥 IV Crush |
| Spot dealer gamma squeeze setups | 🎯 Trading Bench → GEX+ |
| Find best Δ-25 trades across universe | 🎯 Trading Bench → 🎯 Universe Scanner |
| Track sector momentum | 🎯 Trading Bench → 🌐 Surveillance Trading |
| Read morning summary | ☀️ Daily Brief |
| See current macro regime | 🌀 HMM Regime |
| Check insider activity | 💸 Smart-Money → Insider (Form 4) |
| Read upgrades/downgrades | 📅 Catalysts → 📈 Analyst ratings |
| Run short-squeeze deep scan | 🔥 Short Squeeze → 🏛️ Legacy 4-pillar |
| Edit my surveillance list | 🛰️ Watchlists → bottom editor |
| Pin a ticker | Sidebar → Bookmarks → Edit |
| Set up an alert | Edit `config/alerts.yaml` |
| Switch to live trading | Set `EXECUTION_ALLOW_LIVE=1` (DANGEROUS) |

---

*Last updated: May 2026 · 16 tabs · ~25k LoC Python · 166 tests · MIT-style internal license.*
