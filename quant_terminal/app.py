"""Quant Terminal — Streamlit entry-point (8 top-level tabs).

Existing  : 📈 Portfolio Analytics · 🔥 Short Squeeze · 🤖 Kalman
Phase 1   : 🎯 Trading Bench · 🛰️ Watchlists · 🌐 Macro & Regime ·
            💸 Smart-Money & Fundamentals · 📒 Backtest
Phase 2   : 🎯 Conviction & Sizing · 📅 Catalysts & News (Wave 2 — coming)
"""
from __future__ import annotations

from datetime import datetime

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
from src.viz.theme import PALETTE, inject_streamlit_css

# --- new wave-1 cluster imports ---------------------------------------------
# Trading (cluster 5)
from src.trading.dashboards import (
    render_chain_explorer,
    render_gex_profile,
    render_iv_rank_pill,
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

# Backtest (cluster 7)
from src.backtest.dashboards import (
    render_backtest_results,
    render_rule_picker,
    render_walk_forward,
)
from src.backtest.engine import simulate
from src.backtest.metrics_diff import comparison_table
from src.backtest.rules import build_rule

# Decision Support (cluster 3, wave 2)
from src.decision.conviction import score_portfolio, suggested_weight
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
                f"<span style='color:{PALETTE.profit};font-weight:600'>● LIVE</span>"
                f" · refresh every {refresh_choice}",
                unsafe_allow_html=True,
            )
        except ImportError:
            st.warning("`streamlit-autorefresh` non installé — `pip install streamlit-autorefresh`.")
    else:
        st.caption(f"● <span style='color:{PALETTE.fg_muted}'>idle</span>", unsafe_allow_html=True)


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
# Page header
# ============================================================================
st.markdown(
    f"<div style='display:flex;align-items:baseline;gap:16px;margin-bottom:8px'>"
    f"<h2 style='margin:0;color:{PALETTE.fg};font-weight:600'>Quant Terminal</h2>"
    f"<span style='color:{PALETTE.fg_muted};font-size:0.85rem'>"
    f"Portfolio · Trading · Watchlists · Macro · Smart-Money · Backtest · Squeeze · Kalman</span></div>",
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
    "📒 Backtest",
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

    trading_sub = st.tabs(
        ["Chain Explorer", "GEX Profile", "Trade Ticket", "Journal", "Squeeze Score"]
    )

    with trading_sub[0]:
        if not contracts:
            st.info("Aucune chaîne d'options disponible (Alpaca + yfinance ont échoué).")
        else:
            # Spot from the latest price in price panel (fallback to mid of ATM)
            spot = float(prices_eur[ticker].dropna().iloc[-1]) if (
                not prices_eur.empty and ticker in prices_eur.columns
            ) else 0.0
            render_chain_explorer(contracts, underlying=ticker, spot=spot, highlight_delta=0.25)

    with trading_sub[1]:
        if not contracts:
            st.info("Pas de chaîne — GEX indisponible.")
        else:
            spot = float(prices_eur[ticker].dropna().iloc[-1]) if (
                not prices_eur.empty and ticker in prices_eur.columns
            ) else 0.0
            try:
                gex_df = compute_gex(contracts, spot)
                # gamma flip = closest strike where cumulative GEX crosses zero
                flip = None
                if not gex_df.empty:
                    cum = gex_df.sort_values("strike")["net_gex_usd"].cumsum()
                    sign = (cum >= 0).astype(int)
                    flips = sign.diff().abs().fillna(0).astype(bool)
                    if flips.any():
                        flip = float(gex_df.sort_values("strike").iloc[flips.values.argmax()]["strike"])
                render_gex_profile(gex_df, spot=spot, gamma_flip=flip)
            except Exception as exc:
                st.warning(f"GEX failed: {exc}")

    with trading_sub[2]:
        net_ev = portfolio.total_value_eur + float(getattr(portfolio, "cash_eur", 0.0) or 0.0) if portfolio else 10_000.0
        if portfolio is None:
            st.caption("Pas de DEGIRO chargé — debit cap calculé sur un EV fictif de 10 000 EUR.")
        render_trade_ticket_form(
            ticker=ticker,
            net_ev_eur=net_ev,
            fetch_chain_fn=fetch_chain,
        )

    with trading_sub[3]:
        try:
            journal_df = load_journal()
            open_df = journal_df[journal_df["closed_ts"].isna()] if not journal_df.empty else pd.DataFrame()
            closed_df = journal_df[journal_df["closed_ts"].notna()] if not journal_df.empty else pd.DataFrame()
            render_journal(open_df, closed_df)
        except Exception as exc:
            st.info(f"Journal vide ou erreur de lecture : {exc}")

    with trading_sub[4]:
        st.markdown("### Composite gamma-squeeze score")
        st.caption("Net GEX <0 ± 5% + call volume × 2 + OTM call OI Δ +30% sur 5j.")
        # Build a minimal scores_df from the current ticker (real implementation
        # would loop the trading_universe and score each ticker).
        if contracts:
            try:
                from src.trading.squeeze_score import compute_squeeze_score
                spot = float(prices_eur[ticker].dropna().iloc[-1]) if (
                    not prices_eur.empty and ticker in prices_eur.columns
                ) else 0.0
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

    with sec_sub[0]:
        sel = st.selectbox("Ticker", universe_for_sec, key="sec_insider_ticker")
        try:
            f4 = insider_summary(sel, lookback_days=180)
            render_smart_money_panel(f4, pd.DataFrame())
        except Exception as exc:
            st.warning(f"Form 4 indisponible : {exc}")

    with sec_sub[1]:
        rows = []
        for t in universe_for_sec:
            try:
                a = assess_dilution(t)
                rows.append(a.model_dump() if hasattr(a, "model_dump") else a.dict())
            except Exception:
                continue
        render_dilution_panel(pd.DataFrame(rows))

    with sec_sub[2]:
        rows = []
        for t in universe_for_sec:
            try:
                a = assess_runway(t)
                rows.append(a.model_dump() if hasattr(a, "model_dump") else a.dict())
            except Exception:
                continue
        render_runway_panel(pd.DataFrame(rows))

    with sec_sub[3]:
        try:
            flows = thematic_flows_panel(window_days=90)
            render_etf_flows_panel(flows)
        except Exception as exc:
            st.warning(f"ETF flows indisponibles : {exc}")

    with sec_sub[4]:
        st.subheader("DoD program allocations (PB-26)")
        try:
            render_gov_capex_panel(budget_allocations(), capex_panel())
        except Exception as exc:
            st.warning(f"Gov/Capex panels indisponibles : {exc}")

    with sec_sub[5]:
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

    cal_sub = st.tabs(["Catalyst Calendar", "Earnings", "Macro Board", "Launches", "News Flow"])

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


# ============================================================================
# TAB 7 — BACKTEST (Cluster 7)
# ============================================================================
with tabs[7]:
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
# TAB 8 — SHORT SQUEEZE SCANNER (existing)
# ============================================================================
with tabs[8]:
    st.title("🔥 Short Squeeze Scanner")
    st.caption("Combine SEC EDGAR (Form SHO threshold list) + Finviz screener → squeeze score.")

    col_a, col_b = st.columns(2)
    with col_a:
        run_scan = st.button("▶ Lancer un scan", use_container_width=True, key="squeeze_btn")
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
            st.subheader(f"Top candidats ({len(merged)} tickers)")
            st.dataframe(merged.head(50), use_container_width=True, hide_index=True)


# ============================================================================
# TAB 9 — KALMAN ELASTIC TRADING (existing)
# ============================================================================
with tabs[9]:
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
