"""Streamlit renderers for the portfolio Greeks aggregator."""
from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from src.portfolio.greeks import PortfolioGreeks
from src.viz.theme import PALETTE, PLOTLY_TEMPLATE, fmt_eur


def render_greeks_strip(pg: PortfolioGreeks) -> None:
    """5 KPI cards summarising the book Greeks (all in EUR)."""
    cols = st.columns(5)
    cols[0].metric(
        "Σ Delta (EUR)",
        fmt_eur(pg.total_delta_eur),
        help="Net directional exposure in EUR. Stock = market value; option = Δ × spot × qty × 100.",
    )
    cols[1].metric(
        "Σ Gamma — 1% move (EUR)",
        fmt_eur(pg.total_gamma_eur),
        help="Expected delta change for a 1% spot move. Γ × spot² × qty × 100 × 0.01.",
    )
    cols[2].metric(
        "Σ Vega — 1 vol pt (EUR)",
        fmt_eur(pg.total_vega_eur),
        help="P&L for +1 vol-point shift in IV. Vega × qty × 100.",
    )
    cols[3].metric(
        "Σ Theta / day (EUR)",
        fmt_eur(pg.total_theta_eur),
        help="Expected daily decay (negative when long premium).",
    )
    cols[4].metric(
        "β-weighted Δ (EUR)",
        fmt_eur(pg.beta_weighted_delta_eur),
        help="Delta weighted by each ticker's beta to SPY → market-equivalent exposure.",
    )


def render_greeks_by_ticker(by_ticker: pd.DataFrame) -> None:
    if by_ticker is None or by_ticker.empty:
        st.info("Pas de positions à grecquer.")
        return
    show = by_ticker.copy()
    for c in ["delta_eur", "gamma_eur", "vega_eur", "theta_eur"]:
        if c in show.columns:
            show[c] = show[c].round(0)
    if "beta" in show.columns:
        show["beta"] = show["beta"].round(2)
    if "qty" in show.columns:
        show["qty"] = show["qty"].round(2)
    st.dataframe(
        show.sort_values("delta_eur", ascending=False, key=lambda s: s.abs()),
        use_container_width=True,
        hide_index=True,
    )


def render_theta_decay_chart(schedule: pd.DataFrame) -> None:
    if schedule is None or schedule.empty:
        st.info("Pas d'options ouvertes — theta decay = 0.")
        return
    fig = go.Figure(go.Scatter(
        x=schedule["day_offset"],
        y=schedule["cum_theta_eur"],
        mode="lines",
        line={"color": PALETTE.loss, "width": 2},
        fill="tozeroy",
        fillcolor="rgba(239,68,68,0.15)",
        name="Cumulative theta (EUR)",
    ))
    fig.update_layout(
        title="Theta decay forward (EUR cumulé)",
        xaxis_title="Jour (J+N)",
        yaxis_title="EUR",
        **PLOTLY_TEMPLATE["layout"],
    )
    st.plotly_chart(fig, use_container_width=True)
    daily = float(schedule["theta_eur"].iloc[0]) if len(schedule) else 0.0
    st.caption(
        f"Theta journalier total : **{fmt_eur(daily, 2)}** "
        f"(≈ {fmt_eur(daily * 7, 0)} / sem · {fmt_eur(daily * 30, 0)} / mois)."
    )


def render_gamma_calendar(calendar: pd.DataFrame) -> None:
    if calendar is None or calendar.empty:
        st.info("Pas d'options ouvertes — gamma calendar vide.")
        return
    show = calendar.copy()
    for c in ["gamma_now", "gamma_in_7d", "gamma_in_14d"]:
        if c in show.columns:
            show[c] = show[c].round(4)
    if "strike" in show.columns:
        show["strike"] = show["strike"].round(2)
    st.dataframe(show, use_container_width=True, hide_index=True)
    # Highlight positions losing > 50% gamma within 14 days
    high_decay = calendar[calendar["days_to_half_gamma"] <= 14] if "days_to_half_gamma" in calendar.columns else pd.DataFrame()
    if not high_decay.empty:
        st.warning(
            f"⚠️ {len(high_decay)} position(s) perdront 50% de leur gamma dans ≤ 14 jours. "
            "Considérer un roll ou close."
        )
