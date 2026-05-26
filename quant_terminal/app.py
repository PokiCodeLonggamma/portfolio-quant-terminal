"""Quant Terminal — Streamlit entry-point (8 top-level tabs).

Existing  : 📈 Portfolio Analytics · 🔥 Short Squeeze · 🤖 Kalman
Phase 1   : 🎯 Trading Bench · 🛰️ Watchlists · 🌐 Macro & Regime ·
            💸 Smart-Money & Fundamentals · 📒 Backtest
Phase 2   : 🎯 Conviction & Sizing · 📅 Catalysts & News (Wave 2 — coming)
"""
from __future__ import annotations

from datetime import date, datetime

import pandas as pd
import streamlit as st

# --- existing imports -------------------------------------------------------
from src.analytics.factors import (
    correlation_matrix,
    estimate_betas,
    fetch_factor_prices,
)
from src.analytics.optimizer import check_limits
from src.analytics.scenarios import apply_all as apply_scenarios
from src.data.degiro_parser import parse_degiro
from src.kalman.monitoring import artefacts_dir, load_run
from src.portfolio.analytics import (
    cumulative_pnl,
    drawdown,
    fetch_prices_eur,
    portfolio_returns,
    returns,
)
from src.portfolio.holdings import Portfolio, from_degiro
from src.portfolio.risk import risk_metrics
from src.scanners.short_squeeze import (
    fetch_finviz_short_interest,
    fetch_sec_form_sho,
    merge_signals,
)
from src.utils.config import get_config
from src.viz.dashboards import (
    render_allocation_panels,
    render_betas,
    render_corr_heatmap,
    render_holdings_table,
    render_kpi_strip,
    render_pnl_block,
    render_risk_metrics,
    render_scenarios,
    render_violations,
)
from src.viz.plots import lightweight_candles
from src.viz.theme import (
    PALETTE,
    hero_header_html,
    inject_streamlit_css,
    status_pill_html,
)

# --- new wave-1 cluster imports ---------------------------------------------
# Trading (cluster 5)
from src.trading.gex_enrich import max_pain, put_call_ratio, skew_25_delta
from src.trading.iv_analytics import (
    iv_term_structure,
    realised_vs_implied,
    vol_smile,
)
from src.trading.universe_scanner import DEFAULT_UNIVERSE, scan_universe
from src.data_sec.overview import (
    dilution_overview,
    insider_activity_overview,
    kpi_strip as smart_money_kpi_strip,
    runway_overview,
)
from src.scanners.short_squeeze import (
    persist_scan as squeeze_persist_scan,
    top_candidates as squeeze_top_candidates,
)
from src.news.stocktwits import aggregate_cashtag, fetch_cashtag

from src.trading.dashboards import (
    render_chain_explorer,
    render_gex_profile,
    render_journal,
    render_squeeze_board,
    render_trade_ticket_form,
)
from src.trading.gex import compute_gex
from src.trading.journal import load_journal
from src.trading.options_chain import fetch_chain

# Watchlists (cluster 6)
from src.watchlist.dashboards import render_watchlist_tabbed
from src.watchlist.enricher import fetch_panel_for_lists

# Macro + Liquidity (cluster 2)
from src.liquidity.dashboards import render_borrow_panel, render_liquidity_table
from src.macro.dashboards import (
    render_corr_alerts,
    render_corr_heatmap_extended,
    render_pair_screener_table,
    render_regime_board,
    render_regime_history,
)
from src.macro.fred_series import build_macro_panel
from src.macro.regime import classify_regime_from_panel, regime_history

# Data/SEC (cluster 1)
from src.data_sec.cash_runway import assess_runway
from src.data_sec.dashboards import (
    render_dilution_panel,
    render_etf_flows_panel,
    render_gov_capex_panel,
    render_runway_panel,
    render_smart_money_panel,
)
from src.data_sec.dilution import assess_dilution
from src.data_sec.dod_budget import budget_allocations
from src.data_sec.etf_flows import thematic_flows_panel
from src.data_sec.form4 import insider_summary
from src.data_sec.hyperscaler_capex import capex_panel
from src.data_sec.sam_gov import awards_dataframe

# Backtest (cluster 7)
from src.backtest.dashboards import (
    render_backtest_results,
    render_rule_picker,
)
from src.backtest.engine import simulate
from src.backtest.metrics_diff import comparison_table
from src.backtest.rules import build_rule

# Decision Support (cluster 3, wave 2)
from src.decision.conviction import score_portfolio
from src.decision.dashboards import (
    render_conviction_matrix,
    render_hedge_cost,
    render_journal_editor,
    render_journal_summary,
    render_rerating_dashboard,
    render_risk_parity_preview,
    render_var_sizing,
)
from src.decision.hedge_cost import compute_collar, linear_futures_alternatives
from src.decision.journal_store import list_journals, read_journal
from src.decision.rerating_score import compute_rerating_score
from src.decision.risk_parity_preview import risk_parity_weights
from src.decision.var_contribution_sizing import var_contribution_sizing

# Calendar + News (cluster 4, wave 2)
from src.calendar_engine.dashboards import (
    render_catalyst_calendar,
    render_earnings_board,
    render_launch_board,
    render_macro_board,
)
from src.calendar_engine.earnings import fetch_earnings
from src.calendar_engine.implied_moves import implied_move_summary
from src.calendar_engine.macro_events import load_2026
from src.calendar_engine.space_launches import load_launches
from src.news.aggregator import aggregate_news
from src.news.dashboards import render_news_feed, render_news_heatmap
from src.news.llm_summarizer import summarise_transcript as llm_summarise_transcript
from src.news.realtime import refresh_realtime
from src.news.rss_fetcher import fetch_news_multi

# Portfolio Greeks (Feature 3)
from src.portfolio.greeks import (
    aggregate_greeks,
    gamma_calendar,
    theta_decay_schedule,
)
from src.portfolio.greeks_dashboards import (
    render_gamma_calendar,
    render_greeks_by_ticker,
    render_greeks_strip,
    render_theta_decay_chart,
)
from src.trading.journal import list_open as journal_list_open

# Alerts (Feature 2)
import os as _os
from src.alerts.dashboards import (
    render_alerts_history,
    render_alerts_status,
    render_dispatcher_status,
    render_just_fired_toasts,
    render_triggers_table,
)
from src.alerts.engine import EvaluationContext, evaluate_all, load_triggers

# Execution / OMS (Feature 1)
from src.common.schemas import OrderRequest
from src.execution import oms as exec_oms
from src.execution.alpaca_broker import AlpacaBroker
from src.execution.dashboards import (
    render_account_summary,
    render_audit_log,
    render_mode_banner,
    render_open_orders_table,
    render_reconciliation,
    render_submit_form,
)
from src.execution.modes import resolve_mode
from src.execution.positions import get_positions as broker_get_positions
from src.execution.positions import reconcile as positions_reconcile

# Snapshot (Feature 5a)
from src.snapshot.capture import capture as snapshot_capture
from src.snapshot.dashboards import render_snapshot_history, render_snapshot_replay
from src.snapshot.store import list_dates as snapshot_list_dates
from src.snapshot.store import save as snapshot_save

# Tax (Feature 5b)
from src.tax.dashboards import (
    render_annual_summary,
    render_csv_import,
    render_lot_manual_form,
    render_lots_table,
    render_realised_table,
    render_sale_manual_form,
)

# Event trading (Feature 6)
from src.event_trading.dashboards import (
    render_earnings_simulator,
    render_pre_event_wizard,
)


# ============================================================================
# Page boilerplate
# ============================================================================
st.set_page_config(
    page_title="Quant Terminal",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)
st.markdown(inject_streamlit_css(), unsafe_allow_html=True)


# ============================================================================
# Sidebar
# ============================================================================
with st.sidebar:
    st.title("Quant Terminal")
    st.caption("Institutional-grade portfolio analytics")

    cfg = get_config()
    if not cfg.secrets.has_alpaca:
        st.warning("Alpaca keys absent — yfinance fallback only.")
    if not cfg.secrets.sec_email:
        st.info("`SEC_EMAIL` non défini — SEC EDGAR utilisera un UA générique.")
    if not cfg.secrets.fred_api_key:
        st.info("`FRED_API_KEY` non défini — régime macro en mode dégradé.")

    st.divider()
    st.subheader("DEGIRO input")
    uploaded = st.file_uploader("Positions CSV/XLSX", type=["csv", "xlsx", "xls"])

    st.divider()
    end_default = datetime.utcnow().date()
    start_default = end_default.replace(year=end_default.year - int(cfg.settings.get("history_years", 3)))
    period = st.date_input("Window", value=(start_default, end_default))
    if isinstance(period, tuple) and len(period) == 2:
        start_dt, end_dt = (datetime.combine(p, datetime.min.time()) for p in period)
    else:
        start_dt = datetime.combine(start_default, datetime.min.time())
        end_dt = datetime.combine(end_default, datetime.min.time())

    # --- Auto-refresh (Feature 4) ------------------------------------------
    st.divider()
    st.subheader("Live mode")
    refresh_choice = st.selectbox(
        "Auto-refresh",
        options=["Off", "15s", "30s", "60s", "5min"],
        index=0,
        help="Reruns the app on a timer. Cache TTLs are short on live data so refreshes are real.",
        key="sidebar_autorefresh",
    )
    _refresh_ms = {
        "Off": 0,
        "15s": 15_000, "30s": 30_000, "60s": 60_000, "5min": 300_000,
    }[refresh_choice]
    if _refresh_ms > 0:
        try:
            from streamlit_autorefresh import st_autorefresh
            st_autorefresh(interval=_refresh_ms, key="quant_live_tick")
            st.markdown(
                status_pill_html(f"LIVE · {refresh_choice}", "live"),
                unsafe_allow_html=True,
            )
        except ImportError:
            st.warning("`streamlit-autorefresh` non installé — `pip install streamlit-autorefresh`.")
    else:
        st.markdown(status_pill_html("idle", "idle"), unsafe_allow_html=True)


# ============================================================================
# Parse DEGIRO globally (so every tab knows whether portfolio is available)
# ============================================================================
portfolio: Portfolio | None = None
if uploaded is not None:
    try:
        positions = parse_degiro(uploaded)
        portfolio = from_degiro(positions)
    except Exception as exc:
        st.sidebar.error(f"Parsing DEGIRO échoué : {exc}")


@st.cache_data(show_spinner="Chargement des prix EUR…", ttl=60 * 5)  # tightened: 5 min for live mode
def _prices(keys: tuple[str, ...], start: datetime, end: datetime) -> pd.DataFrame:
    stub = pd.DataFrame({
        "symbol": list(keys),
        "name": list(keys),
        "quantity": [1.0] * len(keys),
        "value_eur": [1.0] * len(keys),
        "currency": ["EUR"] * len(keys),
    })
    return fetch_prices_eur(Portfolio(holdings=stub), start=start, end=end)


prices_eur = (
    _prices(tuple(portfolio.universe_keys), start_dt, end_dt)
    if portfolio is not None
    else pd.DataFrame()
)
port_ret = (
    portfolio_returns(portfolio, prices_eur)
    if portfolio is not None and not prices_eur.empty
    else pd.Series(dtype=float)
)
pnl_eur = (
    cumulative_pnl(port_ret, portfolio.total_value_eur)
    if portfolio is not None and not port_ret.empty
    else pd.Series(dtype=float)
)
dd = drawdown(port_ret) if not port_ret.empty else pd.Series(dtype=float)
metrics = risk_metrics(port_ret).as_dict() if not port_ret.empty else {}


# ============================================================================
# Page hero — title, subtitle, status pills (live/paper/data sources)
# ============================================================================
_pills: list[tuple[str, str]] = []
if _refresh_ms > 0:
    _pills.append((f"LIVE {refresh_choice}", "live"))
else:
    _pills.append(("IDLE", "idle"))
_exec_mode_hero = resolve_mode()
_pills.append(("PAPER" if _exec_mode_hero == "paper" else "LIVE TRADING",
               "info" if _exec_mode_hero == "paper" else "loss"))
_pills.append(("ALPACA" if cfg.secrets.has_alpaca else "YFINANCE ONLY",
               "live" if cfg.secrets.has_alpaca else "warning"))
if portfolio is not None:
    _pills.append((f"{len(portfolio.holdings)} POS", "info"))

st.markdown(
    hero_header_html(
        title="Quant Terminal",
        subtitle="Portfolio · Trading · Watchlists · Macro · Smart-Money · "
                 "Decision · Catalysts · Events · Backtest · Alerts · "
                 "Execution · Snapshot/Tax · Squeeze · Kalman",
        pills=_pills,
    ),
    unsafe_allow_html=True,
)


# ============================================================================
# Top-level tabs
# ============================================================================
tabs = st.tabs([
    "📈 Portfolio",
    "🎯 Trading Bench",
    "🛰️ Watchlists",
    "🌐 Macro & Regime",
    "💸 Smart-Money & Fundamentals",
    "🧠 Decision Support",
    "📅 Catalysts & News",
    "🎬 Event Trading",
    "📒 Backtest",
    "🔔 Alerts",
    "📡 Execution",
    "📊 Snapshot & Tax",
    "🔥 Short Squeeze",
    "🤖 Kalman",
])


# ============================================================================
# TAB 0 — PORTFOLIO ANALYTICS
# ============================================================================
with tabs[0]:
    if portfolio is None:
        st.title("Portfolio Analytics")
        st.info(
            "👈 Charge un export DEGIRO (CSV ou XLSX) dans la barre latérale. "
            "Le terminal résout chaque ticker via Alpaca → yfinance, "
            "convertit en EUR à la volée, et calcule le moteur de risque."
        )
    else:
        st.title("Portfolio Analytics")
        render_kpi_strip(
            portfolio,
            metrics,
            latest_pnl_eur=float(pnl_eur.iloc[-1]) if not pnl_eur.empty else 0.0,
        )
        st.divider()
        section = st.tabs(
            ["Overview", "Risk engine", "Greeks", "Factors & correlations", "Scenarios", "Position explorer"]
        )

        with section[0]:
            render_allocation_panels(portfolio)
            st.subheader("Holdings")
            render_holdings_table(portfolio)
            st.subheader("Equity & drawdown")
            render_pnl_block(pnl_eur, dd)

        with section[1]:
            render_risk_metrics(metrics)
            st.subheader("Limites de risque (config/risk_limits.yaml)")
            render_violations(check_limits(portfolio))

        # --- Greeks (Feature 3) ---------------------------------------------
        with section[2]:
            st.subheader("Portfolio Greeks (stocks + options)")
            try:
                open_options = journal_list_open()
            except Exception:
                open_options = pd.DataFrame()

            # Beta-weighted Δ needs an SPY return series; reuse existing
            # factor pipeline if SPY is in prices_eur.columns, else fetch.
            spy_returns = None
            if not prices_eur.empty and "SPY" in prices_eur.columns:
                spy_returns = prices_eur["SPY"].pct_change().dropna()

            pg = aggregate_greeks(
                portfolio=portfolio,
                open_options_df=open_options if not open_options.empty else None,
                prices_eur=prices_eur,
                benchmark_returns=spy_returns,
            )
            render_greeks_strip(pg)

            st.markdown("##### Per-position breakdown")
            render_greeks_by_ticker(pg.by_ticker)

            if not open_options.empty:
                st.markdown("##### Theta decay forward (30 days)")
                schedule = theta_decay_schedule(open_options, days_ahead=30)
                render_theta_decay_chart(schedule)

                st.markdown("##### Gamma calendar")
                cal = gamma_calendar(open_options)
                render_gamma_calendar(cal)
            else:
                st.caption(
                    "Pas de positions options ouvertes dans le journal. "
                    "Σ Gamma/Vega/Theta = 0. Les Greeks d'actions (Δ pur) sont affichés ci-dessus."
                )

        with section[3]:
            if prices_eur.empty:
                st.info("Pas de prix disponibles.")
            else:
                ret = returns(prices_eur).dropna(how="all")
                st.subheader("Corrélations inter-positions")
                render_corr_heatmap(correlation_matrix(ret))
                st.subheader("Betas multi-facteurs")
                try:
                    factor_prices = fetch_factor_prices(start_dt, end_dt)
                    factor_ret = (
                        factor_prices.pct_change().dropna(how="all")
                        if not factor_prices.empty
                        else pd.DataFrame()
                    )
                    betas = (
                        estimate_betas(port_ret, factor_ret)
                        if not factor_ret.empty
                        else pd.Series(dtype=float)
                    )
                    render_betas(betas)
                except Exception as exc:
                    st.warning(f"Beta estimation indisponible : {exc}")

        with section[4]:
            st.subheader("Stress tests macro")
            render_scenarios(apply_scenarios(portfolio.weights))

        with section[5]:
            choice = st.selectbox("Ticker", portfolio.universe_keys, key="portfolio_explorer_ticker")
            if not prices_eur.empty and choice in prices_eur.columns:
                close = prices_eur[choice].dropna()
                if close.empty:
                    st.info("Pas de série de prix.")
                else:
                    ohlc = pd.DataFrame({
                        "open": close.shift(1).fillna(close),
                        "high": close, "low": close, "close": close,
                    })
                    try:
                        from streamlit_lightweight_charts import renderLightweightCharts
                        renderLightweightCharts([lightweight_candles(ohlc)], key=f"chart_{choice}")
                    except ImportError:
                        from src.viz.plots import line_from_close
                        st.plotly_chart(line_from_close(close, title=choice), use_container_width=True)


# ============================================================================
# TAB 1 — TRADING BENCH (Cluster 5)
# ============================================================================
with tabs[1]:
    st.title("🎯 Trading Bench")
    st.caption(
        "Event-driven directional options : LONG CALL / LONG PUT au pied du gamma (Δ≈0.25), "
        "gates IV-rank/OI/debit, détection MM gamma-negatif."
    )

    trading_universe = sorted({
        "XLE", "URA", "XLF", "QQQ", "ARKX", "QTUM", "SMH", "SOXX", "GDX", "USO", "SPY",
        "ASTS", "RDW", "BKSY", "IONQ", "RKLB", "AAOI", "QS", "ONDS", "CCJ", "GOOG",
    })

    sel_col, _ = st.columns([1, 3])
    ticker = sel_col.selectbox("Underlying", trading_universe, key="trading_underlying")

    @st.cache_data(show_spinner=f"Chargement chaîne {ticker}…", ttl=60 * 5)  # tightened: 5 min for live mode
    def _chain(t: str) -> list:
        try:
            return fetch_chain(t)
        except Exception as exc:
            st.warning(f"Chain fetch failed for {t}: {exc}")
            return []

    contracts = _chain(ticker)

    trading_sub = st.tabs([
        "🎯 Universe Scanner",
        "Chain Explorer",
        "GEX+ (max pain · P/C · skew)",
        "IV Analytics",
        "Trade Ticket",
        "Journal",
        "Squeeze Score",
    ])

    # --- Sub-tab 0 — Universe Scanner ---------------------------------------
    with trading_sub[0]:
        st.markdown("### Best Δ-25 setups across the universe")
        st.caption(
            "Score = (low IV bias) + (negative gamma zone hit) + (extreme P/C ratio). "
            "Refreshed at the cache TTL of the chain (5min)."
        )

        @st.cache_data(show_spinner="Scanning universe…", ttl=60 * 10)
        def _scan(_universe: tuple[str, ...], _spots: dict):
            return scan_universe(list(_universe), fetch_chain_fn=fetch_chain,
                                 spot_lookup=_spots)

        # Universe = sector ETFs + portfolio tickers
        scan_universe_list = list(DEFAULT_UNIVERSE)
        if portfolio is not None:
            scan_universe_list = sorted(set(scan_universe_list + portfolio.universe_keys))
        spot_lookup = {}
        if not prices_eur.empty:
            for col in prices_eur.columns:
                s = prices_eur[col].dropna()
                if not s.empty:
                    spot_lookup[col] = float(s.iloc[-1])

        if st.button("▶ Run scan now", key="scanner_run_btn") or False:
            _scan.clear()  # invalidate cache for manual refresh
        df_scan = _scan(tuple(scan_universe_list), spot_lookup)
        if df_scan.empty:
            st.info("Scan returned nothing — check chain providers and live spot lookups.")
        else:
            st.dataframe(df_scan.head(20), use_container_width=True, hide_index=True)
            st.caption(f"{len(df_scan)} tickers scanned · asof {df_scan['asof'].iloc[0]}")

    # Shared spot resolver across trading sub-tabs: local panel → yfinance fallback.
    def _resolve_spot(t: str) -> float:
        if not prices_eur.empty and t in prices_eur.columns:
            s = prices_eur[t].dropna()
            if not s.empty:
                return float(s.iloc[-1])
        try:
            from src.trading.options_chain import _safe_spot as _ss
            v = _ss(t)
            if v and v > 0:
                return float(v)
        except Exception:
            pass
        return 0.0

    with trading_sub[1]:
        if not contracts:
            st.info("Aucune chaîne d'options disponible (Alpaca + yfinance ont échoué).")
        else:
            spot = _resolve_spot(ticker)
            render_chain_explorer(contracts, underlying=ticker, spot=spot, highlight_delta=0.25)

    # --- Sub-tab 2 — GEX + enrichments --------------------------------------
    with trading_sub[2]:
        if not contracts:
            st.info("Pas de chaîne — GEX indisponible.")
        else:
            spot = _resolve_spot(ticker)
            try:
                gex_df = compute_gex(contracts, spot)
                from src.trading.gex import gamma_flip_strike
                flip = gamma_flip_strike(gex_df)
                render_gex_profile(gex_df, spot=spot, gamma_flip=flip, contracts=contracts)

                # Enrichments row
                st.markdown("##### Setup metrics")
                mp = max_pain(contracts)
                pc = put_call_ratio(contracts)
                sk = skew_25_delta(contracts)
                cols = st.columns(4)
                cols[0].metric("Max pain", f"{mp:.2f}" if mp else "n/a",
                               help="Strike that minimises option-holder payout. Gravitational anchor near expiry.")
                cols[1].metric("P/C ratio (OI)", f"{pc['overall_pc_ratio']:.2f}",
                               help=f"Puts: {pc['total_put']:,} · Calls: {pc['total_call']:,}")
                cols[2].metric("25Δ skew (IV)",
                               f"{sk['skew'] * 100:+.1f} pts" if sk['skew'] is not None else "n/a",
                               help="Positive = put more expensive than call (bearish skew).")
                cols[3].metric("Gamma flip", f"{flip:.2f}" if flip else "n/a")
            except Exception as exc:
                st.warning(f"GEX+ failed: {exc}")

    # --- Sub-tab 3 — IV Analytics (term, smile, RV vs IV) -------------------
    with trading_sub[3]:
        if not contracts:
            st.info("Pas de chaîne — IV analytics indisponibles.")
        else:
            spot = _resolve_spot(ticker)
            iv_sub = st.tabs(["Term structure", "Vol smile", "RV vs IV"])
            with iv_sub[0]:
                term = iv_term_structure(contracts, spot)
                if term.empty:
                    st.info("Pas d'IV exploitables sur la chain.")
                else:
                    import plotly.express as px
                    fig = px.line(term, x="dte_days", y="atm_iv_avg",
                                  markers=True, title=f"ATM IV term structure — {ticker}")
                    fig.update_layout(yaxis_tickformat=".0%",
                                       xaxis_title="DTE (days)",
                                       yaxis_title="ATM IV")
                    st.plotly_chart(fig, use_container_width=True)
                    st.dataframe(term, use_container_width=True, hide_index=True)

            with iv_sub[1]:
                expiries = sorted({c.expiry for c in contracts})
                pick = st.selectbox("Expiry", expiries, key=f"smile_expiry_{ticker}")
                smile = vol_smile(contracts, pick, spot)
                if smile.empty:
                    st.info("Smile indisponible pour cette expiry.")
                else:
                    import plotly.graph_objects as go
                    fig = go.Figure()
                    if "call_iv" in smile.columns:
                        fig.add_scatter(x=smile["moneyness"], y=smile["call_iv"],
                                        mode="markers+lines", name="Call IV",
                                        line={"color": "#22C55E"})
                    if "put_iv" in smile.columns:
                        fig.add_scatter(x=smile["moneyness"], y=smile["put_iv"],
                                        mode="markers+lines", name="Put IV",
                                        line={"color": "#EF4444"})
                    fig.update_layout(title=f"Vol smile — {ticker} @ {pick.isoformat()}",
                                       xaxis_title="Moneyness (strike/spot - 1)",
                                       yaxis_title="IV",
                                       yaxis_tickformat=".0%")
                    st.plotly_chart(fig, use_container_width=True)

            with iv_sub[2]:
                close = None
                if not prices_eur.empty and ticker in prices_eur.columns:
                    close = prices_eur[ticker].dropna()
                if close is None or close.empty:
                    # yfinance fallback for tickers not in the local panel
                    try:
                        import yfinance as yf
                        cfg = get_config()
                        yf_sym = cfg.yfinance_symbol(ticker) or ticker
                        hist = yf.download(yf_sym, period="120d", progress=False,
                                            auto_adjust=True, threads=False)
                        if hist is not None and not hist.empty:
                            if isinstance(hist.columns, pd.MultiIndex):
                                hist.columns = hist.columns.get_level_values(0)
                            close = hist["Close"].astype(float).dropna()
                    except Exception:
                        close = None
                if close is None or close.empty:
                    st.info("Pas de série de prix pour calculer la RV.")
                else:
                    term = iv_term_structure(contracts, spot)
                    atm_iv = float(term["atm_iv_avg"].dropna().iloc[0]) if (
                        not term.empty and not term["atm_iv_avg"].dropna().empty
                    ) else 0.0
                    rv_iv = realised_vs_implied(close, atm_iv, window=20)
                    cols = st.columns(4)
                    cols[0].metric("RV 20d (annualised)", f"{rv_iv['rv'] * 100:.1f}%")
                    cols[1].metric("ATM IV (now)", f"{rv_iv['iv'] * 100:.1f}%")
                    cols[2].metric("IV − RV", f"{rv_iv['iv_minus_rv'] * 100:+.1f} pts")
                    cols[3].metric(
                        "Premium %",
                        f"{rv_iv['premium_pct'] * 100:+.1f}%",
                        help="Positive = vol expensive vs realised. Negative = cheap.",
                    )

    with trading_sub[4]:
        net_ev = portfolio.total_value_eur + float(getattr(portfolio, "cash_eur", 0.0) or 0.0) if portfolio else 10_000.0
        if portfolio is None:
            st.caption("Pas de DEGIRO chargé — debit cap calculé sur un EV fictif de 10 000 EUR.")
        render_trade_ticket_form(
            ticker=ticker,
            net_ev_eur=net_ev,
            fetch_chain_fn=fetch_chain,
        )

    with trading_sub[5]:
        try:
            journal_df = load_journal()
            open_df = journal_df[journal_df["closed_ts"].isna()] if not journal_df.empty else pd.DataFrame()
            closed_df = journal_df[journal_df["closed_ts"].notna()] if not journal_df.empty else pd.DataFrame()
            render_journal(open_df, closed_df)
        except Exception as exc:
            st.info(f"Journal vide ou erreur de lecture : {exc}")

    with trading_sub[6]:
        # Surface the live Finviz/SEC squeeze scan + the chain-derived score side-by-side
        st.markdown("### Squeeze scanner top candidates (Finviz + SEC SHO)")
        scan_df = squeeze_top_candidates()
        if scan_df is not None and not scan_df.empty:
            st.dataframe(scan_df, use_container_width=True, hide_index=True)
        else:
            st.caption("Aucun scan persistant — lancer un scan depuis l'onglet **🔥 Short Squeeze** d'abord.")

        st.markdown("### Composite gamma-squeeze score")
        st.caption("Net GEX <0 ± 5% + call volume × 2 + OTM call OI Δ +30% sur 5j.")
        # Build a minimal scores_df from the current ticker (real implementation
        # would loop the trading_universe and score each ticker).
        if contracts:
            try:
                from src.trading.squeeze_score import compute_squeeze_score
                spot = _resolve_spot(ticker)
                score = compute_squeeze_score(contracts, spot=spot)
                # Add the ticker as a column so render_squeeze_board can display it
                if score is not None:
                    score = {"ticker": ticker, **score}
                    scores_df = pd.DataFrame([score])
                else:
                    scores_df = None
                render_squeeze_board(scores_df)
            except Exception as exc:
                st.warning(f"Squeeze score failed: {exc}")
        else:
            st.info("Pas de chaîne — score indisponible.")


# ============================================================================
# TAB 2 — WATCHLISTS (Cluster 6)
# ============================================================================
with tabs[2]:
    st.title("🛰️ Watchlists")
    st.caption("Quantum · Photonics · Defense · Pre-IPO — sub-themes avec conviction + catalyseur.")

    @st.cache_data(show_spinner="Chargement watchlists…", ttl=60 * 30)
    def _watchlist_data(start: datetime, end: datetime):
        from src.watchlist.enricher import add_live_prices
        from src.watchlist.loader import load_watchlist
        from src.watchlist.private import load_private_watchlist
        qdf = load_watchlist("quantum")
        pdf = load_watchlist("photonics")
        ddf = load_watchlist("defense")
        pi = load_private_watchlist()
        # Shared price fetch across all public lists
        try:
            shared = fetch_panel_for_lists([qdf, pdf, ddf], start=start, end=end)
        except Exception:
            shared = pd.DataFrame()
        try:
            qdf = add_live_prices(qdf, start=start, end=end, price_panel=shared)
            pdf = add_live_prices(pdf, start=start, end=end, price_panel=shared)
            ddf = add_live_prices(ddf, start=start, end=end, price_panel=shared)
        except Exception:
            pass
        return qdf, pdf, ddf, pi, shared

    try:
        qdf, pdf, ddf, pi, shared = _watchlist_data(start_dt, end_dt)
        render_watchlist_tabbed(
            quantum_df=qdf,
            photonics_df=pdf,
            defense_df=ddf,
            pre_ipo_df=pi,
            sparkline_panel=shared if not shared.empty else None,
        )
    except Exception as exc:
        st.error(f"Watchlists indisponibles : {exc}")


# ============================================================================
# TAB 3 — MACRO & REGIME (Cluster 2)
# ============================================================================
with tabs[3]:
    st.title("🌐 Macro & Regime")
    st.caption("Régime macro 2×2×2 · corrélations roulantes · pair-trade screener · liquidity radar.")

    macro_sub = st.tabs(["Regime", "Correlations", "Pair Screener", "Liquidity"])

    with macro_sub[0]:
        try:
            panel = build_macro_panel()
            snap = classify_regime_from_panel(panel)
            render_regime_board(snap)
            st.subheader("Historique régimes")
            render_regime_history(regime_history(panel))
        except Exception as exc:
            st.warning(f"Macro indisponible : {exc}")

    with macro_sub[1]:
        if prices_eur.empty:
            st.info("Charge un DEGIRO pour activer les corrélations sur portefeuille.")
        else:
            ret = returns(prices_eur).dropna(how="all")
            window = st.slider("Fenêtre roulante (jours)", 20, 250, 60, step=10, key="macro_corr_window")
            try:
                from src.macro.correlations import corr_regime_changes, rolling_corr_matrix
                cm = rolling_corr_matrix(ret, window_days=window).iloc[-1]
                # Pivot last-snapshot to full matrix for the heatmap
                tickers = ret.columns.tolist()
                last_matrix = pd.DataFrame(
                    cm.values.reshape(len(tickers), len(tickers))
                    if hasattr(cm, "values") and cm.values.size == len(tickers) ** 2
                    else ret.corr().values,
                    index=tickers, columns=tickers,
                ) if hasattr(cm, "values") else ret.corr()
                render_corr_heatmap_extended(last_matrix, title=f"Corrélation roulante {window}j")
                st.subheader("Alertes de changement de régime")
                alerts = corr_regime_changes(ret, window=window, threshold=0.3)
                render_corr_alerts(alerts)
            except Exception as exc:
                st.warning(f"Corrélations indisponibles : {exc}")

    with macro_sub[2]:
        if prices_eur.empty:
            st.info("Charge un DEGIRO pour activer le pair screener.")
        else:
            try:
                from src.macro.pair_screener import screen_pairs
                pairs = screen_pairs(prices_eur)
                render_pair_screener_table(pairs)
            except Exception as exc:
                st.warning(f"Pair screener indisponible : {exc}")

    with macro_sub[3]:
        if portfolio is None:
            st.info("Charge un DEGIRO pour activer le liquidity radar.")
        else:
            try:
                from src.liquidity.adv import adv_panel
                from src.liquidity.borrow import borrow_panel
                liq = adv_panel(portfolio.universe_keys, start=start_dt, end=end_dt)
                render_liquidity_table(liq)
                st.subheader("Short interest")
                borrow = borrow_panel(portfolio.universe_keys)
                render_borrow_panel(borrow)
            except Exception as exc:
                st.warning(f"Liquidity radar indisponible : {exc}")


# ============================================================================
# TAB 4 — SMART-MONEY & FUNDAMENTALS (Cluster 1)
# ============================================================================
with tabs[4]:
    st.title("💸 Smart-Money & Fundamentals")
    st.caption("SEC EDGAR — Form 4 · 13F · Dilution · Cash runway · ETF flows · Gov contracts · Hyperscaler capex.")

    sec_sub = st.tabs([
        "🌐 Overview",
        "Insider (Form 4)",
        "Dilution Radar",
        "Cash Runway",
        "ETF Flows",
        "Gov Contracts",
        "Hyperscaler Capex",
    ])

    universe_for_sec = portfolio.universe_keys if portfolio else [
        "ASTS", "RDW", "BKSY", "IONQ", "RKLB", "AAOI", "QS", "ONDS", "CCJ",
        "BWXT", "ALB", "NTR", "GOOG",
    ]

    # --- Sub-tab 0 — Cross-ticker overview ---------------------------------
    with sec_sub[0]:
        st.markdown("### Smart-Money cross-ticker view")
        st.caption("Single pull across the whole universe — no per-ticker selector required.")

        @st.cache_data(show_spinner="Aggregating SEC data across universe…", ttl=60 * 30)
        def _smart_money_overview(_universe: tuple[str, ...]):
            ins = insider_activity_overview(list(_universe), lookback_days=90)
            dil = dilution_overview(list(_universe))
            run = runway_overview(list(_universe))
            kpis = smart_money_kpi_strip(ins, dil, run)
            return ins, dil, run, kpis

        try:
            ins_df, dil_df, run_df, kpis = _smart_money_overview(tuple(universe_for_sec))
            cols = st.columns(4)
            cols[0].metric(
                "Insider net (90d)",
                f"${(kpis.get('insider_buy_usd', 0) + kpis.get('insider_sell_usd', 0)) / 1e6:.1f}M",
            )
            cols[1].metric("Top insider buyer", kpis.get("top_insider_buy_ticker", "—"))
            cols[2].metric(
                "Dilution-risk count",
                f"{kpis.get('n_high_dilution', 0)}",
                help=kpis.get("high_dilution_tickers", ""),
            )
            cols[3].metric(
                "Runway < 2Q",
                f"{kpis.get('n_runway_short', 0)}",
                help=kpis.get("runway_short_tickers", ""),
            )

            st.markdown("##### Top insider transactions (90d)")
            if ins_df is not None and not ins_df.empty:
                show_cols = [c for c in ["ticker", "reporter_name", "reporter_role",
                                          "transaction_date", "code", "shares", "price",
                                          "value_usd"] if c in ins_df.columns]
                st.dataframe(ins_df[show_cols].head(20),
                             use_container_width=True, hide_index=True)
            else:
                st.caption("No insider transactions parsed for this universe.")

            colA, colB = st.columns(2)
            with colA:
                st.markdown("##### Dilution-risk leaderboard")
                if dil_df is not None and not dil_df.empty:
                    st.dataframe(dil_df.head(15),
                                 use_container_width=True, hide_index=True)
                else:
                    st.caption("No dilution data.")
            with colB:
                st.markdown("##### Lowest cash runway")
                if run_df is not None and not run_df.empty:
                    st.dataframe(run_df.head(15),
                                 use_container_width=True, hide_index=True)
                else:
                    st.caption("No runway data.")
        except Exception as exc:
            st.warning(f"Overview failed: {exc}")

    with sec_sub[1]:
        sel = st.selectbox("Ticker", universe_for_sec, key="sec_insider_ticker")
        try:
            f4 = insider_summary(sel, lookback_days=180)
            render_smart_money_panel(f4, pd.DataFrame())
        except Exception as exc:
            st.warning(f"Form 4 indisponible : {exc}")

    with sec_sub[2]:
        rows = []
        for t in universe_for_sec:
            try:
                a = assess_dilution(t)
                rows.append(a.model_dump() if hasattr(a, "model_dump") else a.dict())
            except Exception:
                continue
        render_dilution_panel(pd.DataFrame(rows))

    with sec_sub[3]:
        rows = []
        for t in universe_for_sec:
            try:
                a = assess_runway(t)
                rows.append(a.model_dump() if hasattr(a, "model_dump") else a.dict())
            except Exception:
                continue
        render_runway_panel(pd.DataFrame(rows))

    with sec_sub[4]:
        try:
            flows = thematic_flows_panel(window_days=90)
            render_etf_flows_panel(flows)
        except Exception as exc:
            st.warning(f"ETF flows indisponibles : {exc}")

    with sec_sub[5]:
        st.subheader("DoD program allocations (PB-26)")
        try:
            try:
                awards = awards_dataframe(list(universe_for_sec), lookback_days=180)
            except Exception:
                awards = pd.DataFrame()
            render_gov_capex_panel(awards, budget_allocations(), capex_panel())
        except Exception as exc:
            st.warning(f"Gov/Capex panels indisponibles : {exc}")

    with sec_sub[6]:
        st.subheader("Hyperscaler quarterly capex (USD bn)")
        try:
            cdf = capex_panel()
            st.dataframe(cdf, use_container_width=True, hide_index=True)
            if not cdf.empty and "total" in cdf.columns:
                import plotly.express as px
                fig = px.bar(cdf, x="quarter", y="total", title="Total hyperscaler capex")
                fig.update_layout(template="plotly_dark")
                st.plotly_chart(fig, use_container_width=True)
        except Exception as exc:
            st.warning(f"Capex panel indisponible : {exc}")


# ============================================================================
# TAB 5 — DECISION SUPPORT (Cluster 3, Wave 2)
# ============================================================================
with tabs[5]:
    st.title("🧠 Decision Support")
    st.caption("Conviction matrix · VaR-contribution sizing · Risk-parity preview · Thesis journal · Hedge cost.")

    dec_sub = st.tabs(["Conviction & Sizing", "Thesis Journal", "Hedge Cost"])

    with dec_sub[0]:
        if portfolio is None or prices_eur.empty:
            st.info("Charge un DEGIRO pour activer la matrice de conviction.")
        else:
            try:
                # Pull dilution + runway from cluster 1 (best-effort, may be slow on first call)
                dilutions = {}
                runways = {}
                with st.spinner("Pulling dilution + runway snapshots…"):
                    for t in portfolio.universe_keys[:20]:  # cap to avoid heavy SEC fetches in UI
                        try:
                            dilutions[t] = assess_dilution(t)
                        except Exception:
                            pass
                        try:
                            runways[t] = assess_runway(t)
                        except Exception:
                            pass
                scores_df = score_portfolio(
                    portfolio,
                    dilutions=dilutions,
                    runways=runways,
                )
                if not scores_df.empty:
                    # Attach current weights for the matrix view
                    cur = portfolio.weights.to_dict()
                    scores_df["current_weight"] = scores_df["ticker"].map(cur).fillna(0.0)
                    render_conviction_matrix(scores_df)

                # VaR-contribution sizing
                st.markdown("### VaR-contribution sizing")
                themes = sorted(portfolio.holdings["theme"].unique().tolist())
                theme_choice = st.selectbox("Theme à dégrader", themes, key="decision_var_theme")
                target_pct = st.slider("Cible contribution VaR du thème", 0.05, 0.95, 0.30, 0.05,
                                       key="decision_var_target")
                per_pos_ret = returns(prices_eur).dropna(how="all")
                suggestion_df = var_contribution_sizing(
                    portfolio, per_pos_ret, target_theme_pct=target_pct, theme=theme_choice,
                )
                render_var_sizing(suggestion_df)

                # Risk-parity preview
                st.markdown("### Risk-parity preview")
                parity_w = risk_parity_weights(per_pos_ret, vol_target=0.01)
                render_risk_parity_preview(portfolio.weights, parity_w)
            except Exception as exc:
                st.warning(f"Conviction matrix indisponible : {exc}")

    with dec_sub[1]:
        st.markdown("### Thesis journal")
        try:
            render_journal_summary(list_journals())
        except Exception as exc:
            st.info(f"Aucun journal pour l'instant : {exc}")

        universe_for_journal = (
            portfolio.universe_keys if portfolio is not None else ["ASTS", "RDW", "IONQ"]
        )
        ticker_j = st.selectbox("Edit / create thesis for", universe_for_journal,
                                key="decision_journal_picker")
        render_journal_editor(read_journal(ticker_j), ticker_j)

        # Re-rating dashboard
        if portfolio is not None and not prices_eur.empty:
            rows = []
            for t in portfolio.universe_keys:
                je = read_journal(t)
                if je is None:
                    continue
                if t not in prices_eur.columns:
                    continue
                spot = float(prices_eur[t].dropna().iloc[-1])
                try:
                    r = compute_rerating_score(je, current_price_eur=spot)
                    rows.append(r.model_dump() if hasattr(r, "model_dump") else r.dict())
                except Exception:
                    continue
            if rows:
                st.markdown("### Re-rating dashboard")
                render_rerating_dashboard(pd.DataFrame(rows))

    with dec_sub[2]:
        st.markdown("### Hedge cost calculator (collar)")
        universe_for_hedge = (
            portfolio.universe_keys if portfolio is not None else ["ASTS", "RDW"]
        )
        ticker_h = st.selectbox("Hedge ticker", universe_for_hedge, key="decision_hedge_picker")
        if portfolio is not None:
            try:
                position_eur = float(
                    portfolio.holdings.set_index("universe_key").loc[ticker_h, "value_eur"]
                )
            except Exception:
                position_eur = 1_000.0
        else:
            position_eur = 1_000.0
        cols_h = st.columns(3)
        dte_h = cols_h[0].slider("DTE", 30, 180, 90, 30, key="decision_hedge_dte")
        call_pct = cols_h[1].slider("Call OTM %", 0.05, 0.30, 0.15, 0.01, key="decision_hedge_call")
        put_pct  = cols_h[2].slider("Put OTM %",  0.05, 0.30, 0.10, 0.01, key="decision_hedge_put")
        try:
            quote = compute_collar(
                ticker_h, position_eur,
                dte_days=int(dte_h), call_otm_pct=float(call_pct), put_otm_pct=float(put_pct),
            )
            alts = linear_futures_alternatives(ticker_h)
            render_hedge_cost(quote, alts)
        except Exception as exc:
            st.warning(f"Hedge cost indisponible : {exc}")


# ============================================================================
# TAB 6 — CATALYSTS & NEWS (Cluster 4, Wave 2)
# ============================================================================
with tabs[6]:
    st.title("📅 Catalysts & News")
    st.caption("Earnings · FOMC/ECB/OPEC · NRC · Launches · Implied moves · News flow + sentiment.")

    cal_sub = st.tabs([
        "Catalyst Calendar", "Earnings", "Macro Board",
        "Launches", "News Flow", "💬 Stocktwits cashtag",
        "🤖 Transcript LLM", "📡 Live news",
    ])

    universe_for_cal = (
        portfolio.universe_keys if portfolio is not None
        else ["ASTS", "RDW", "BKSY", "IONQ", "RKLB", "AAOI", "CCJ", "GOOG"]
    )

    @st.cache_data(show_spinner="Loading 2026 macro calendar…", ttl=60 * 60 * 6)
    def _macro_events():
        try:
            return load_2026()
        except Exception:
            return []

    @st.cache_data(show_spinner="Loading earnings…", ttl=60 * 30)
    def _earnings(tickers: tuple[str, ...]):
        try:
            return fetch_earnings(list(tickers))
        except Exception:
            return []

    @st.cache_data(show_spinner="Loading launches…", ttl=60 * 60 * 6)
    def _launches():
        try:
            return load_launches()
        except Exception:
            return []

    macro_evs = _macro_events()
    earn_evs = _earnings(tuple(universe_for_cal))
    launch_evs = _launches()

    with cal_sub[0]:
        all_events = list(macro_evs) + list(earn_evs) + list(launch_evs)
        render_catalyst_calendar(all_events, window_days=30)

    with cal_sub[1]:
        try:
            implied = implied_move_summary(universe_for_cal[:8], dte_days=30) if earn_evs else {}
        except Exception:
            implied = {}
        render_earnings_board(earn_evs, implied if isinstance(implied, dict) else {})

    with cal_sub[2]:
        render_macro_board(macro_evs)

    with cal_sub[3]:
        render_launch_board(launch_evs)

    with cal_sub[4]:
        st.markdown("### News flow per ticker")
        cols_n = st.columns([1, 3])
        lookback = cols_n[0].slider("Lookback (jours)", 1, 30, 7, 1, key="news_lookback")
        try:
            news_df = fetch_news_multi(universe_for_cal[:12], lookback_days=int(lookback))
        except Exception as exc:
            st.warning(f"News fetch failed: {exc}")
            news_df = pd.DataFrame()
        if not news_df.empty:
            try:
                agg = aggregate_news(news_df)
                render_news_heatmap(agg)
            except Exception as exc:
                st.warning(f"News aggregation failed: {exc}")
            render_news_feed(news_df)
        else:
            st.info("Aucun article retourné par Google News (rate limit ou ticker rare).")

    # --- Sub-tab 5 — Stocktwits cashtag monitor ----------------------------
    with cal_sub[5]:
        st.markdown("### Cashtag posts (Stocktwits free API)")
        st.caption(
            "Free alternative to paid Twitter/X API. Rate-limited ~200 req / 30 min — "
            "results cached 5 minutes."
        )
        twit_universe = universe_for_cal[:8]
        col_t1, col_t2 = st.columns([1, 3])
        focus_ticker = col_t1.selectbox("Focus ticker", twit_universe, key="stwits_focus")
        try:
            agg = aggregate_cashtag(list(twit_universe), lookback_hours=24)
        except Exception as exc:
            st.warning(f"Stocktwits aggregate failed: {exc}")
            agg = pd.DataFrame()
        if not agg.empty:
            st.markdown("##### 24h sentiment per ticker")
            st.dataframe(agg, use_container_width=True, hide_index=True)
        try:
            feed = fetch_cashtag(focus_ticker, limit=30)
        except Exception as exc:
            st.warning(f"Stocktwits feed failed: {exc}")
            feed = pd.DataFrame()
        if not feed.empty:
            st.markdown(f"##### Latest posts — ${focus_ticker}")
            display_cols = [c for c in ["ts", "user", "user_followers", "body",
                                          "sentiment_bull", "sentiment_bear", "likes"]
                            if c in feed.columns]
            st.dataframe(feed[display_cols].head(20), use_container_width=True, hide_index=True)
        else:
            st.info(f"Aucun post Stocktwits récent pour ${focus_ticker}.")

    # --- Sub-tab 6 — LLM transcript summariser (Feature #14) ---------------
    with cal_sub[6]:
        st.markdown("### Earnings transcript summariser (Claude)")
        st.caption(
            "Paste a raw earnings call transcript — the LLM extracts beats, misses, "
            "guidance direction, sentiment and 3 key management quotes. "
            "Requires `ANTHROPIC_API_KEY` in `.env`. Results cached 24h per ticker+transcript."
        )
        col_l1, col_l2 = st.columns([1, 3])
        llm_ticker = col_l1.selectbox(
            "Ticker", universe_for_cal, key="llm_transcript_ticker",
        )
        col_l1.caption("Model: ANTHROPIC_MODEL env (default claude-sonnet-4-5)")
        transcript_text = col_l2.text_area(
            "Paste transcript", height=240,
            placeholder="Paste the full earnings call transcript here (min 100 chars).",
            key="llm_transcript_text",
        )
        if st.button("▶ Summarise", key="llm_transcript_btn"):
            if not transcript_text or len(transcript_text.strip()) < 100:
                st.warning("Transcript too short (need ≥100 chars).")
            else:
                try:
                    with st.spinner("Calling Claude…"):
                        out = llm_summarise_transcript(transcript_text, llm_ticker)
                    st.success("Done.")
                    cols = st.columns(3)
                    cols[0].metric("Sentiment",
                                    f"{float(out.get('sentiment', 0.0)):+.2f}")
                    cols[1].metric("Guidance", str(out.get("guidance", "—"))[:40])
                    cols[2].metric("Beats / Misses",
                                    f"{len(out.get('beats', []))} / {len(out.get('misses', []))}")
                    st.markdown("##### Bottom line")
                    st.write(out.get("summary", ""))
                    if out.get("beats"):
                        st.markdown("##### Beats")
                        for b in out["beats"]:
                            st.markdown(f"- ✅ {b}")
                    if out.get("misses"):
                        st.markdown("##### Misses")
                        for m in out["misses"]:
                            st.markdown(f"- ⚠️ {m}")
                    if out.get("key_quotes"):
                        st.markdown("##### Key quotes")
                        for q in out["key_quotes"]:
                            st.markdown(f"> {q}")
                except Exception as exc:
                    st.warning(f"LLM summariser failed: {exc}")

    # --- Sub-tab 7 — Real-time news (Feature #15) --------------------------
    with cal_sub[7]:
        st.markdown("### Real-time news ingest + alert push")
        st.caption(
            "Polls Google News RSS per ticker (lookback ≤24h), scores sentiment, and "
            "fires an Alert when the cohort net sentiment crosses thresholds "
            "(default bearish ≤ -0.4, bullish ≥ +0.5). Already-seen headlines are "
            "remembered between refreshes (state in `data/alerts/news_realtime_seen.json`)."
        )
        col_r1, col_r2, col_r3 = st.columns([1, 1, 2])
        rt_lookback = col_r1.slider("Lookback (heures)", 1, 24, 6, 1,
                                      key="rt_news_lookback")
        rt_bear = col_r2.slider("Bearish threshold", -1.0, 0.0, -0.4, 0.05,
                                  key="rt_news_bear")
        rt_bull = col_r3.slider("Bullish threshold", 0.0, 1.0, 0.5, 0.05,
                                  key="rt_news_bull")
        if st.button("▶ Refresh now", key="rt_news_btn"):
            try:
                with st.spinner("Polling RSS feeds…"):
                    fresh = refresh_realtime(
                        universe_for_cal,
                        lookback_hours=int(rt_lookback),
                        bearish_threshold=float(rt_bear),
                        bullish_threshold=float(rt_bull),
                        dispatch=True,
                    )
                if fresh.empty:
                    st.info("Aucune nouvelle headline depuis la dernière passe.")
                else:
                    st.success(f"{len(fresh)} fresh headlines · "
                               f"net sentiment = {fresh['sentiment'].mean():+.2f}")
                    show_cols = [c for c in ["ts", "ticker", "title", "sentiment",
                                              "source", "link"] if c in fresh.columns]
                    st.dataframe(fresh[show_cols], use_container_width=True,
                                  hide_index=True)
            except Exception as exc:
                st.warning(f"Real-time news refresh failed: {exc}")


# ============================================================================
# TAB 7 — EVENT TRADING (Feature 6: wizard + earnings simulator)
# ============================================================================
with tabs[7]:
    st.title("🎬 Event Trading")
    st.caption(
        "Pre-event setup wizard (Δ-25 candidates per catalyst) + earnings reaction "
        "simulator (spot/IV shock grid)."
    )

    et_sub = st.tabs(["Pre-event wizard", "Earnings simulator"])

    trading_universe = [
        "ASTS", "RDW", "BKSY", "IONQ", "RKLB", "AAOI", "QS", "ONDS",
        "CCJ", "BWXT", "ALB", "NTR", "GOOG",
    ]
    # Build a lightweight chain fetcher with the cache the Trading tab uses
    @st.cache_data(show_spinner=False, ttl=300)
    def _wizard_chain(t: str):
        try:
            return fetch_chain(t)
        except Exception:
            return []

    spot_lookup = {}
    if not prices_eur.empty:
        for col in prices_eur.columns:
            s = prices_eur[col].dropna()
            if not s.empty:
                spot_lookup[col] = float(s.iloc[-1])

    # Macro+earnings events from Cluster 4 (already loaded for the catalyst board)
    try:
        all_events = list(_macro_events()) + list(_earnings(tuple(universe_for_cal))) + list(_launches())
    except Exception:
        all_events = []
    upcoming = [e for e in all_events
                if e.start.date() >= datetime.utcnow().date()
                and (e.start.date() - datetime.utcnow().date()).days <= 21]

    with et_sub[0]:
        render_pre_event_wizard(
            upcoming, trading_universe,
            spot_lookup=spot_lookup,
            fetch_chain_fn=_wizard_chain,
        )

    with et_sub[1]:
        try:
            open_options = journal_list_open()
        except Exception:
            open_options = pd.DataFrame()
        render_earnings_simulator(
            open_options_df=open_options,
            fetch_chain_fn=_wizard_chain,
            spot_lookup=spot_lookup,
        )


# ============================================================================
# TAB 8 — BACKTEST (Cluster 7)
# ============================================================================
with tabs[8]:
    st.title("📒 Backtest")
    st.caption("Simule l'application de règles (max single, max DD, stop-loss, momentum entry…) sur le portefeuille.")

    if portfolio is None or prices_eur.empty:
        st.info("Charge un DEGIRO + une fenêtre temporelle pour activer le backtest.")
    else:
        rule_specs = render_rule_picker()
        if rule_specs:
            rules = []
            for spec in rule_specs:
                try:
                    rules.append(build_rule(spec))
                except Exception as exc:
                    st.warning(f"Rule {spec} ignored: {exc}")

            initial_weights = portfolio.weights
            initial_eur = portfolio.total_value_eur + float(getattr(portfolio, "cash_eur", 0.0) or 0.0)

            try:
                result = simulate(
                    prices_eur=prices_eur,
                    initial_weights=initial_weights,
                    rules=rules,
                    rebalance_freq="ME",
                    initial_eur=initial_eur,
                )
                cmp = comparison_table(result["baseline_nav"], result["ruled_nav"])
                render_backtest_results(
                    baseline_nav=result["baseline_nav"],
                    ruled_nav=result["ruled_nav"],
                    comparison_table=cmp,
                    trigger_log=result.get("trigger_log", pd.DataFrame()),
                )
            except Exception as exc:
                st.error(f"Simulation failed: {exc}")

            with st.expander("Walk-forward optimiser (param sweep)", expanded=False):
                st.caption("Disponible — implémentation cluster 7 (cf. optimizer.walk_forward).")
        else:
            st.info("Sélectionne ≥ 1 règle pour lancer la simulation.")


# ============================================================================
# TAB 9 — ALERTS (Feature 2)
# ============================================================================
with tabs[9]:
    st.title("🔔 Alerts")
    st.caption(
        "Triggers évalués à chaque refresh (Live mode) — Discord / Email / Telegram / Streamlit. "
        "Édite `config/alerts.yaml` à chaud."
    )

    # Load triggers, build evaluation context from already-fetched data
    triggers = load_triggers()
    ctx = EvaluationContext(
        prices_eur=prices_eur if not prices_eur.empty else None,
        drawdown_series=dd if not dd.empty else None,
    )

    # Dispatcher status from env (no real API call here)
    dispatchers_status = {
        "discord":   bool(_os.getenv("DISCORD_WEBHOOK_URL", "")),
        "email":     bool(_os.getenv("ALERT_SMTP_HOST", "") and _os.getenv("ALERT_SMTP_TO", "")),
        "telegram":  bool(_os.getenv("TELEGRAM_BOT_TOKEN", "") and _os.getenv("TELEGRAM_CHAT_ID", "")),
        "streamlit": True,
    }

    # Evaluate triggers — only dispatch when LIVE mode is on, to avoid alert
    # spam during manual interactions. In idle mode we evaluate + show fired
    # but do NOT push to external channels.
    live_on = _refresh_ms > 0
    try:
        fired_now = evaluate_all(triggers, ctx, dispatch=live_on)
    except Exception as exc:
        st.error(f"Alerts engine error : {exc}")
        fired_now = []

    render_alerts_status(triggers, fired_now, dispatchers_status)
    render_just_fired_toasts(fired_now)

    st.divider()
    st.subheader("Channels")
    render_dispatcher_status(dispatchers_status)

    alerts_sub = st.tabs(["Triggers configurés", "Historique des alertes"])
    with alerts_sub[0]:
        render_triggers_table(triggers)
        st.caption(
            "Pour ajouter / désactiver un trigger : édite `config/alerts.yaml`. "
            "Les changements sont pris en compte au prochain refresh."
        )
    with alerts_sub[1]:
        render_alerts_history(limit=100)


# ============================================================================
# TAB 10 — EXECUTION (Feature 1)
# ============================================================================
with tabs[10]:
    st.title("📡 Execution")
    st.caption(
        "OMS connecté à Alpaca. Paper-mode par défaut, gates pré-trade obligatoires, "
        "audit log persistant."
    )

    exec_mode = resolve_mode()
    render_mode_banner(exec_mode)

    # Lazy broker — only built if Alpaca keys are present.
    broker: AlpacaBroker | None = None
    account = None
    if cfg.secrets.has_alpaca:
        try:
            broker = AlpacaBroker(mode=exec_mode)
            account = broker.get_account()
        except Exception as exc:
            st.error(f"Connexion Alpaca échouée : {exc}")
            broker = None

    st.subheader("Account")
    render_account_summary(account)

    exec_sub = st.tabs(["Submit order", "Open orders", "Positions (reconciliation)",
                         "Audit log"])

    with exec_sub[0]:
        default_ticker = portfolio.universe_keys[0] if (
            portfolio is not None and portfolio.universe_keys
        ) else "ASTS"

        def _handle_submit(payload: dict) -> None:
            if broker is None:
                st.error("Broker non initialisé — vérifier `.env` Alpaca.")
                return
            req = OrderRequest(
                ticker=payload["ticker"],
                qty=payload["qty"],
                side=payload["side"],
                asset_class=payload["asset_class"],
                order_type=payload["order_type"],
                limit_price=payload["limit_price"],
                contract_symbol=payload["contract_symbol"],
                mode=exec_mode,
            )
            last_eur = None
            if not prices_eur.empty and req.ticker in prices_eur.columns:
                try:
                    last_eur = float(prices_eur[req.ticker].dropna().iloc[-1])
                except Exception:
                    last_eur = None
            record = exec_oms.submit(
                req,
                broker=broker,
                account=account,
                last_px_eur=last_eur,
            )
            if record.status == "rejected":
                st.error(f"Ordre refusé : {record.error}")
            else:
                st.success(
                    f"Ordre {record.status} — broker_id={record.broker_order_id} · "
                    f"local={record.order_id[:8]}"
                )

        render_submit_form(default_ticker=default_ticker, on_submit=_handle_submit)

    with exec_sub[1]:
        # Refresh status from broker if available
        if broker is not None:
            try:
                n_updated = exec_oms.refresh_status(broker=broker)
                if n_updated:
                    st.caption(f"{n_updated} ordre(s) mis à jour depuis Alpaca.")
            except Exception as exc:
                st.warning(f"refresh status failed: {exc}")

        open_df = exec_oms.list_open()

        def _handle_cancel(broker_order_id: str) -> bool:
            return exec_oms.cancel(broker_order_id, broker=broker)

        render_open_orders_table(open_df, on_cancel=_handle_cancel)

    with exec_sub[2]:
        if broker is None:
            st.info("Pas de broker connecté — réconciliation indisponible.")
        else:
            try:
                broker_pos = broker_get_positions(broker)
                rec = positions_reconcile(portfolio, broker_pos)
                render_reconciliation(rec)
            except Exception as exc:
                st.warning(f"Réconciliation échouée : {exc}")

    with exec_sub[3]:
        render_audit_log(tail=80)


# ============================================================================
# TAB 11 — SNAPSHOT & TAX (Feature 5)
# ============================================================================
with tabs[11]:
    st.title("📊 Snapshot & Tax")
    st.caption(
        "Snapshots quotidiens du portefeuille + tax lots FIFO (cost basis EUR, "
        "réalisation per-vente, 2074-CMV ready)."
    )

    snaptax_sub = st.tabs(["Snapshot history", "Replay a snapshot", "Tax lots", "Realised PnL", "Import / Manual"])

    with snaptax_sub[0]:
        # Auto-capture once per day when LIVE mode is on
        if _refresh_ms > 0 and portfolio is not None:
            today_iso = date.today()
            if today_iso not in snapshot_list_dates():
                try:
                    bundle = snapshot_capture(portfolio, prices_eur)
                    path = snapshot_save(bundle)
                    st.success(f"Snapshot du jour capturé → {path.name}")
                except Exception as exc:
                    st.warning(f"Auto-capture échoué : {exc}")
        elif portfolio is not None:
            if st.button("📸 Capture snapshot maintenant",
                          key="snap_manual_btn"):
                try:
                    bundle = snapshot_capture(portfolio, prices_eur)
                    path = snapshot_save(bundle)
                    st.success(f"Snapshot capturé → {path.name}")
                except Exception as exc:
                    st.warning(f"Capture échouée : {exc}")
        render_snapshot_history()

    with snaptax_sub[1]:
        render_snapshot_replay()

    with snaptax_sub[2]:
        st.subheader("Lots ouverts (FIFO)")
        render_lots_table()

    with snaptax_sub[3]:
        st.subheader("PnL réalisé par année")
        render_annual_summary()
        st.subheader("Historique des ventes")
        render_realised_table()

    with snaptax_sub[4]:
        render_csv_import()
        st.divider()
        render_lot_manual_form()
        st.divider()
        render_sale_manual_form()


# ============================================================================
# TAB 12 — SHORT SQUEEZE SCANNER (existing)
# ============================================================================
with tabs[12]:
    st.title("🔥 Short Squeeze Scanner")
    st.caption("Combine SEC EDGAR (Form SHO threshold list) + Finviz screener → squeeze score.")

    col_a, col_b = st.columns(2)
    with col_a:
        run_scan = st.button("▶ Lancer un scan", use_container_width=True, key="squeeze_btn_v2")
    with col_b:
        st.metric("SEC_EMAIL", "configuré" if get_config().secrets.sec_email else "manquant")

    if run_scan:
        with st.spinner("Fetching Finviz…"):
            finviz = fetch_finviz_short_interest()
        with st.spinner("Fetching SEC SHO list…"):
            sho = fetch_sec_form_sho()
        if finviz.empty:
            st.warning("Finviz n'a rien retourné — vérifier la connectivité ou bloquage UA.")
        else:
            merged = merge_signals(finviz, sho)
            # Persist so the Trading Bench Squeeze sub-tab + Alerts can read it
            try:
                squeeze_persist_scan(merged)
            except Exception:
                pass
            st.subheader(f"Top candidats ({len(merged)} tickers)")
            st.dataframe(merged.head(50), use_container_width=True, hide_index=True)
            st.caption(
                "✔ Scan persisté — surfaceé automatiquement dans `🎯 Trading Bench › Squeeze Score`."
            )


# ============================================================================
# TAB 13 — KALMAN ELASTIC TRADING (existing)
# ============================================================================
with tabs[13]:
    st.title("🤖 Kalman Elastic Trading")
    st.caption(f"Lecture des artefacts depuis : `{artefacts_dir()}`")

    run = load_run()
    if run.is_empty:
        st.info(
            "Aucun artefact détecté. Le pipeline Kalman doit déposer `equity.csv`, "
            "`trades.csv`, `metrics_phase2.json` et/ou `metrics_phase3.json` "
            "dans le dossier ci-dessus (ou définir `QUANT_TERMINAL_KALMAN_ARTEFACTS`)."
        )
    else:
        cols = st.columns(4)
        cols[0].metric("Trades", run.total_trades)
        cols[1].metric("Win rate", f"{run.win_rate * 100:.1f}%")
        cols[2].metric(
            "Dernière barre equity",
            run.last_equity_date.strftime("%Y-%m-%d") if run.last_equity_date else "n/a",
        )
        cols[3].metric("Phase 3 active", "✓" if run.metrics_phase3 else "—")

        if not run.equity.empty:
            st.subheader("Equity")
            st.line_chart(run.equity.set_index("date")["equity"], use_container_width=True)
        if run.metrics_phase2:
            st.subheader("Métriques Phase 2")
            st.json(run.metrics_phase2)
        if run.metrics_phase3:
            st.subheader("Métriques Phase 3")
            st.json(run.metrics_phase3)
        if not run.trades.empty:
            st.subheader("Trades")
            st.dataframe(run.trades, use_container_width=True, hide_index=True)


# ============================================================================
# Footer
# ============================================================================
st.markdown(
    f"<div style='margin-top:2rem;color:{PALETTE.fg_muted};font-size:0.75rem;text-align:center;'>"
    "Quant Terminal · Alpaca + yfinance · FX EUR · Lightweight-charts · 8 tabs (Wave 2: Decision + Catalysts coming)"
    "</div>",
    unsafe_allow_html=True,
)
