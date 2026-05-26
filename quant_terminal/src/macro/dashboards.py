"""Streamlit render blocks for the macro / régime tab.

All ``render_*`` helpers accept already-fetched data (no I/O) — the host
``app.py`` is responsible for resolving FRED panels and price frames.
"""
from __future__ import annotations

import pandas as pd
import streamlit as st

from src.common.schemas import RegimeSnapshot
from src.viz.plots import heatmap_correlation
from src.viz.theme import PALETTE, fmt_pct


# ---------------------------------------------------------------------------
# Regime board
# ---------------------------------------------------------------------------
def render_regime_board(snapshot: RegimeSnapshot) -> None:
    """Top section: 2x2x2 regime label + the four axis metrics."""
    st.subheader("Régime macro")
    st.caption(
        f"asof {snapshot.asof.isoformat()} — confidence "
        f"{snapshot.confidence:.0%}"
    )

    badge_color = PALETTE.accent if snapshot.confidence >= 0.6 else PALETTE.warning
    st.markdown(
        f"""
        <div style="
            display:inline-block; padding:10px 16px; border-radius:10px;
            background:{PALETTE.card}; border:1px solid {badge_color};
            color:{PALETTE.fg}; font-weight:600; font-size:1.1rem;
            margin-bottom:12px;
        ">
        {snapshot.label}
        </div>
        """,
        unsafe_allow_html=True,
    )

    cols = st.columns(4)
    with cols[0]:
        st.metric("Inflation", snapshot.inflation.upper(),
                  help=f"CPI YoY threshold: 3%; value={snapshot.metrics.get('cpi_yoy', float('nan')):.2f}")
    with cols[1]:
        st.metric("Growth", snapshot.growth.upper(),
                  help=f"PMI proxy threshold: 50; value={snapshot.metrics.get('pmi_proxy', float('nan')):.1f}")
    with cols[2]:
        st.metric("Policy", snapshot.policy.upper(),
                  help=f"DFF 6m delta: {snapshot.metrics.get('dff_6m_delta', float('nan')):+.2f}")
    with cols[3]:
        t10y2y = snapshot.metrics.get("t10y2y", float("nan"))
        st.metric("10y-2y spread",
                  f"{t10y2y:+.2f}" if pd.notna(t10y2y) else "n/a",
                  help="Negative = inverted yield curve")

    other = {k: v for k, v in snapshot.metrics.items()
             if k not in {"cpi_yoy", "pmi_proxy", "dff_6m_delta", "t10y2y"}}
    if other:
        st.caption("Other signals: " + " | ".join(
            f"{k}={v:.2f}" for k, v in sorted(other.items())
        ))


def render_regime_history(history: pd.DataFrame) -> None:
    """Compact table of recent regime changes (last 30 rows)."""
    if history is None or history.empty:
        st.info("No regime history available (FRED data missing).")
        return
    shown = history.tail(30).copy()
    if "date" in shown.columns:
        shown["date"] = pd.to_datetime(shown["date"]).dt.strftime("%Y-%m-%d")
    if "confidence" in shown.columns:
        shown["confidence"] = (shown["confidence"] * 100).round(0).astype(int).astype(str) + "%"
    st.dataframe(shown, use_container_width=True, hide_index=True)


# ---------------------------------------------------------------------------
# Correlations
# ---------------------------------------------------------------------------
def render_corr_heatmap_extended(corr_matrix: pd.DataFrame, title: str = "Rolling correlations") -> None:
    """Square-correlation heatmap (extended palette)."""
    if corr_matrix is None or corr_matrix.empty:
        st.info("Not enough overlapping return history to compute the correlation matrix.")
        return
    st.subheader(title)
    st.plotly_chart(heatmap_correlation(corr_matrix, title=title), use_container_width=True)


def render_corr_alerts(alerts: pd.DataFrame) -> None:
    """Table of (ticker, benchmark) pairs whose correlation shifted."""
    st.subheader("Correlation regime changes")
    if alerts is None or alerts.empty:
        st.success("No significant correlation shifts detected over the lookback window.")
        return
    shown = alerts.copy()
    for col in ("corr_now", "corr_then", "delta"):
        if col in shown.columns:
            shown[col] = shown[col].astype(float).round(2)
    st.dataframe(shown, use_container_width=True, hide_index=True)


# ---------------------------------------------------------------------------
# Pair screener
# ---------------------------------------------------------------------------
def render_pair_screener_table(pairs_df: pd.DataFrame, title: str = "Pair-trade candidates") -> None:
    """Render the ranked output of ``screen_pairs_df``."""
    st.subheader(title)
    if pairs_df is None or pairs_df.empty:
        st.info("No cointegrated pairs at the requested p-value threshold.")
        return
    shown = pairs_df.copy()
    if "momentum_gap" in shown.columns:
        shown["momentum_gap"] = shown["momentum_gap"].apply(
            lambda v: fmt_pct(v) if pd.notna(v) else "n/a"
        )
    if "coint_pvalue" in shown.columns:
        shown["coint_pvalue"] = shown["coint_pvalue"].round(4)
    if "spread_z" in shown.columns:
        shown["spread_z"] = shown["spread_z"].round(2)
    if "halflife_days" in shown.columns:
        shown["halflife_days"] = shown["halflife_days"].round(1)
    st.dataframe(shown, use_container_width=True, hide_index=True)


def render_pair_candidates(pairs: list) -> None:
    """Render typed list[PairCandidate] (alternate entry point)."""
    if not pairs:
        st.info("No pair candidates available.")
        return
    df = pd.DataFrame([p.model_dump() for p in pairs])
    render_pair_screener_table(df)
