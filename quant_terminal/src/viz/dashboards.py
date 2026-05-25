"""Re-usable Streamlit blocks for the three tabs of app.py."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from src.portfolio.holdings import Portfolio
from src.viz.plots import (
    bar_horizontal,
    drawdown_chart,
    equity_curve,
    heatmap_correlation,
    pie_allocation,
    scenario_bar,
)
from src.viz.theme import fmt_eur, fmt_pct


# ----------------------------------------------------------------------------
# KPI strip
# ----------------------------------------------------------------------------
def render_kpi_strip(portfolio: Portfolio, metrics: dict | None = None,
                     latest_pnl_eur: float | None = None) -> None:
    """Top metric row."""
    cash = float(getattr(portfolio, "cash_eur", 0.0) or 0.0)
    net_value = portfolio.total_value_eur + cash
    cols = st.columns(6)
    with cols[0]:
        st.metric("Net value", fmt_eur(net_value))
    with cols[1]:
        st.metric("Gross long", fmt_eur(portfolio.total_value_eur))
    with cols[2]:
        st.metric("Cash / margin", fmt_eur(cash))
    with cols[3]:
        st.metric("Positions", f"{len(portfolio.holdings)}")
    with cols[4]:
        sharpe = (metrics or {}).get("sharpe", float("nan"))
        st.metric("Sharpe", f"{sharpe:.2f}" if pd.notna(sharpe) else "n/a")
    with cols[5]:
        dd = (metrics or {}).get("max_drawdown", float("nan"))
        st.metric("Max drawdown", fmt_pct(dd) if pd.notna(dd) else "n/a")


# ----------------------------------------------------------------------------
# Holdings table
# ----------------------------------------------------------------------------
def render_holdings_table(portfolio: Portfolio) -> None:
    df = portfolio.holdings.copy()
    df["weight"] = df["value_eur"] / portfolio.total_value_eur if portfolio.total_value_eur else 0.0
    show = df[[
        "universe_key", "name", "quantity", "currency", "value_eur",
        "weight", "theme", "region", "asset_class",
    ]].rename(columns={
        "universe_key": "ticker",
        "value_eur": "value (EUR)",
        "weight": "weight %",
    })
    show["weight %"] = (show["weight %"] * 100).round(2)
    show["value (EUR)"] = show["value (EUR)"].round(0)
    st.dataframe(
        show.sort_values("value (EUR)", ascending=False),
        use_container_width=True,
        hide_index=True,
    )


# ----------------------------------------------------------------------------
# Allocation pies
# ----------------------------------------------------------------------------
def render_allocation_panels(portfolio: Portfolio) -> None:
    col1, col2 = st.columns(2)
    with col1:
        st.plotly_chart(pie_allocation(portfolio.by_theme(), "Allocation by theme"),
                        use_container_width=True)
    with col2:
        st.plotly_chart(pie_allocation(portfolio.by_region(), "Allocation by region"),
                        use_container_width=True)

    col3, col4 = st.columns(2)
    with col3:
        st.plotly_chart(pie_allocation(portfolio.by_currency(), "Allocation by listing currency"),
                        use_container_width=True)
    with col4:
        st.plotly_chart(pie_allocation(portfolio.by_asset_class(), "Allocation by asset class"),
                        use_container_width=True)


# ----------------------------------------------------------------------------
# Equity + drawdown
# ----------------------------------------------------------------------------
def render_pnl_block(pnl_eur: pd.Series, dd: pd.Series) -> None:
    if pnl_eur.empty:
        st.info("Pas d'historique de prix — connecter Alpaca ou yfinance fonctionnera après chargement des positions.")
        return
    st.plotly_chart(equity_curve(pnl_eur), use_container_width=True)
    st.plotly_chart(drawdown_chart(dd), use_container_width=True)


# ----------------------------------------------------------------------------
# Risk
# ----------------------------------------------------------------------------
def render_risk_metrics(metrics: dict) -> None:
    if not metrics:
        return
    cols = st.columns(4)
    cols[0].metric("Ann. return", fmt_pct(metrics.get("ann_return", 0.0)))
    cols[1].metric("Ann. vol", fmt_pct(metrics.get("ann_vol", 0.0)))
    cols[2].metric("VaR 95% daily", fmt_pct(metrics.get("var_95_daily", 0.0)))
    cols[3].metric("CVaR 95% daily", fmt_pct(metrics.get("cvar_95_daily", 0.0)))


def render_violations(violations: pd.DataFrame) -> None:
    if violations is None or violations.empty:
        st.success("Aucune limite de risque enfreinte.")
        return
    st.warning(f"{len(violations)} limite(s) enfreinte(s) :")
    st.dataframe(violations, use_container_width=True, hide_index=True)


# ----------------------------------------------------------------------------
# Factors / correlations / scenarios
# ----------------------------------------------------------------------------
def render_corr_heatmap(corr: pd.DataFrame) -> None:
    if corr is None or corr.empty:
        st.info("Pas assez de données pour le corrélogramme.")
        return
    st.plotly_chart(heatmap_correlation(corr), use_container_width=True)


def render_scenarios(scenario_df: pd.DataFrame) -> None:
    if scenario_df is None or scenario_df.empty:
        return
    st.plotly_chart(scenario_bar(scenario_df), use_container_width=True)
    st.dataframe(scenario_df, use_container_width=True, hide_index=True)


def render_betas(betas: pd.Series) -> None:
    if betas is None or betas.empty:
        st.info("Beta indisponible (pas assez d'historique).")
        return
    st.plotly_chart(bar_horizontal(betas.drop("const", errors="ignore"), "Multi-factor betas"),
                    use_container_width=True)
