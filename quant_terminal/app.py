"""Quant Terminal — Streamlit entry-point.

Three tabs:
  1. Portfolio Analytics  — DEGIRO ingest -> Alpaca/yfinance prices -> EUR
                            normalisation -> risk engine + factor analytics.
  2. Short Squeeze Scanner — template, branch SEC EDGAR + Finviz here.
  3. Kalman Elastic Trading — Phase 2/3 monitoring from artefacts dir.
"""
from __future__ import annotations

from datetime import datetime

import pandas as pd
import streamlit as st

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
from src.portfolio.holdings import from_degiro
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


# ----------------------------------------------------------------------------
# Page boilerplate
# ----------------------------------------------------------------------------
st.set_page_config(
    page_title="Quant Terminal",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)
st.markdown(inject_streamlit_css(), unsafe_allow_html=True)


# ----------------------------------------------------------------------------
# Sidebar — global inputs
# ----------------------------------------------------------------------------
with st.sidebar:
    st.title("Quant Terminal")
    st.caption("Institutional-grade portfolio analytics")

    cfg = get_config()
    if not cfg.secrets.has_alpaca:
        st.warning("Alpaca keys absent — yfinance fallback only.")
    if not cfg.secrets.sec_email:
        st.info("`SEC_EMAIL` non défini — le scanner squeeze utilisera un UA générique.")

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


# ----------------------------------------------------------------------------
# Page header (visible above the tabs so they're never clipped)
# ----------------------------------------------------------------------------
st.markdown(
    f"<div style='display:flex;align-items:baseline;gap:16px;margin-bottom:8px'>"
    f"<h2 style='margin:0;color:{PALETTE.fg};font-weight:600'>Quant Terminal</h2>"
    f"<span style='color:{PALETTE.fg_muted};font-size:0.85rem'>"
    f"Portfolio · Short Squeeze · Kalman</span></div>",
    unsafe_allow_html=True,
)


# ----------------------------------------------------------------------------
# Tabs
# ----------------------------------------------------------------------------
tab_portfolio, tab_squeeze, tab_kalman = st.tabs([
    "📈 Portfolio Analytics",
    "🔥 Short Squeeze Scanner",
    "🤖 Kalman Elastic Trading",
])


# ============================================================================
# TAB 1 — PORTFOLIO ANALYTICS
# ============================================================================
with tab_portfolio:
    if uploaded is None:
        st.title("Portfolio Analytics")
        st.info(
            "👈 Charge un export DEGIRO (CSV ou XLSX) dans la barre latérale. "
            "Le terminal résout chaque ticker via Alpaca → yfinance, "
            "convertit en EUR à la volée, et calcule le moteur de risque."
        )
        st.stop()

    try:
        positions = parse_degiro(uploaded)
    except Exception as exc:
        st.error(f"Parsing DEGIRO échoué : {exc}")
        st.stop()

    portfolio = from_degiro(positions)

    @st.cache_data(show_spinner="Chargement des prix EUR…", ttl=60 * 60)
    def _prices(keys: tuple[str, ...], start: datetime, end: datetime) -> pd.DataFrame:
        from src.portfolio.holdings import Portfolio
        # Recompose a tiny holdings stub so fetch_prices_eur can pull the universe keys.
        stub = pd.DataFrame({
            "symbol": list(keys),
            "name": list(keys),
            "quantity": [1.0] * len(keys),
            "value_eur": [1.0] * len(keys),
            "currency": ["EUR"] * len(keys),
        })
        return fetch_prices_eur(Portfolio(holdings=stub), start=start, end=end)

    prices_eur = _prices(tuple(portfolio.universe_keys), start_dt, end_dt)
    port_ret = portfolio_returns(portfolio, prices_eur) if not prices_eur.empty else pd.Series(dtype=float)
    pnl_eur = cumulative_pnl(port_ret, portfolio.total_value_eur) if not port_ret.empty else pd.Series(dtype=float)
    dd = drawdown(port_ret) if not port_ret.empty else pd.Series(dtype=float)
    metrics = risk_metrics(port_ret).as_dict() if not port_ret.empty else {}

    st.title("Portfolio Analytics")
    render_kpi_strip(portfolio, metrics, latest_pnl_eur=float(pnl_eur.iloc[-1]) if not pnl_eur.empty else 0.0)

    st.divider()
    section = st.tabs(["Overview", "Risk engine", "Factors & correlations", "Scenarios", "Position explorer"])

    # --- Overview ----------------------------------------------------------
    with section[0]:
        render_allocation_panels(portfolio)
        st.subheader("Holdings")
        render_holdings_table(portfolio)
        st.subheader("Equity & drawdown")
        render_pnl_block(pnl_eur, dd)

    # --- Risk engine -------------------------------------------------------
    with section[1]:
        render_risk_metrics(metrics)
        st.subheader("Limites de risque (config/risk_limits.yaml)")
        render_violations(check_limits(portfolio))

    # --- Factors & correlations -------------------------------------------
    with section[2]:
        if prices_eur.empty:
            st.info("Pas de prix disponibles.")
        else:
            ret = returns(prices_eur).dropna(how="all")
            st.subheader("Corrélations inter-positions")
            render_corr_heatmap(correlation_matrix(ret))
            st.subheader("Betas multi-facteurs")
            try:
                factor_prices = fetch_factor_prices(start_dt, end_dt)
                factor_ret = factor_prices.pct_change().dropna(how="all") if not factor_prices.empty else pd.DataFrame()
                betas = estimate_betas(port_ret, factor_ret) if not factor_ret.empty else pd.Series(dtype=float)
                render_betas(betas)
            except Exception as exc:
                st.warning(f"Beta estimation indisponible : {exc}")

    # --- Scenarios ---------------------------------------------------------
    with section[3]:
        st.subheader("Stress tests macro")
        scenario_df = apply_scenarios(portfolio.weights)
        render_scenarios(scenario_df)

    # --- Position explorer -------------------------------------------------
    with section[4]:
        if not portfolio.universe_keys:
            st.info("Aucune position détectée.")
        else:
            choice = st.selectbox("Ticker", portfolio.universe_keys)
            if not prices_eur.empty and choice in prices_eur.columns:
                close = prices_eur[choice].dropna()
                if close.empty:
                    st.info("Pas de série de prix.")
                else:
                    # Build a poor-man's OHLC from daily close (close=open=high=low) for lightweight-charts.
                    ohlc = pd.DataFrame({
                        "open": close.shift(1).fillna(close),
                        "high": close,
                        "low": close,
                        "close": close,
                    })
                    payload = lightweight_candles(ohlc)
                    try:
                        from streamlit_lightweight_charts import renderLightweightCharts
                        renderLightweightCharts([payload], key=f"chart_{choice}")
                    except ImportError:
                        from src.viz.plots import line_from_close
                        st.plotly_chart(line_from_close(close, title=choice), use_container_width=True)


# ============================================================================
# TAB 2 — SHORT SQUEEZE SCANNER (template)
# ============================================================================
with tab_squeeze:
    st.title("Short Squeeze Scanner")
    st.caption("Combine SEC EDGAR (Form SHO threshold list) + Finviz screener → squeeze score.")

    col_a, col_b = st.columns(2)
    with col_a:
        run_scan = st.button("▶ Lancer un scan", use_container_width=True)
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
# TAB 3 — KALMAN ELASTIC TRADING (Phase 2/3 monitoring)
# ============================================================================
with tab_kalman:
    st.title("Kalman Elastic Trading")
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
        cols[2].metric("Dernière barre equity",
                       run.last_equity_date.strftime("%Y-%m-%d") if run.last_equity_date else "n/a")
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


# ----------------------------------------------------------------------------
# Footer
# ----------------------------------------------------------------------------
st.markdown(
    f"<div style='margin-top:2rem;color:{PALETTE.fg_muted};font-size:0.75rem;text-align:center;'>"
    "Quant Terminal · prix Alpaca + yfinance fallback · FX normalisée EUR · Lightweight-charts"
    "</div>",
    unsafe_allow_html=True,
)
