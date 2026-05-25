"""Streamlit render blocks for the Smart-Money & Filings tab.

All `render_*` helpers accept already-fetched data (no side effects). The
fetching contract belongs to `app.py`.
"""
from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from src.common.schemas import FilingEvent
from src.viz.theme import PLOTLY_TEMPLATE, fmt_eur


# ---------------------------------------------------------------------------
# Smart money (Form 4 + 13F)
# ---------------------------------------------------------------------------
def render_smart_money_panel(df_form4: pd.DataFrame, df_13f: pd.DataFrame) -> None:
    """Side-by-side: insider Form-4 summary (left) and 13F tape (right)."""
    st.subheader("Smart money tape")
    col_left, col_right = st.columns([1, 1])

    with col_left:
        st.caption("Insider transactions — Form 4")
        if df_form4 is None or df_form4.empty:
            st.info("No Form 4 activity in the selected lookback window.")
        else:
            show = df_form4.copy()
            for c in ("net_shares", "net_usd"):
                if c in show.columns:
                    show[c] = pd.to_numeric(show[c], errors="coerce").round(0)
            st.dataframe(show, use_container_width=True, hide_index=True)

    with col_right:
        st.caption("Institutional positioning — 13F-HR (45d lag)")
        if df_13f is None or df_13f.empty:
            st.info("No 13F holdings to display.")
        else:
            show = df_13f.copy()
            if "sum_value_usd" in show.columns:
                show["sum_value_usd"] = pd.to_numeric(show["sum_value_usd"], errors="coerce").round(0)
            st.dataframe(show, use_container_width=True, hide_index=True)


# ---------------------------------------------------------------------------
# Filings table
# ---------------------------------------------------------------------------
def render_filings_table(filings: list[FilingEvent]) -> None:
    st.subheader("Recent filings")
    if not filings:
        st.info("No filings.")
        return
    rows = [{
        "filed": f.filed,
        "form": f.form,
        "ticker": f.ticker or "",
        "cik": f.cik,
        "accession": f.accession,
        "url": f.url,
    } for f in filings]
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)


# ---------------------------------------------------------------------------
# Dilution
# ---------------------------------------------------------------------------
def render_dilution_panel(df: pd.DataFrame) -> None:
    st.subheader("Dilution risk")
    if df is None or df.empty:
        st.info("No dilution data — try widening your watchlist or check SEC_EMAIL.")
        return
    show = df.copy()
    if "convertibles_outstanding_usd" in show.columns:
        show["convertibles_outstanding_usd"] = pd.to_numeric(
            show["convertibles_outstanding_usd"], errors="coerce"
        ).round(0)

    def _flag(score: int) -> str:
        try:
            n = int(score)
        except Exception:
            return ""
        return "[red]" * 1 if n >= 4 else ("[amber]" if n == 3 else "[green]")

    if "dilution_score" in show.columns:
        show["flag"] = show["dilution_score"].apply(_flag)

    st.dataframe(show, use_container_width=True, hide_index=True)


# ---------------------------------------------------------------------------
# Runway
# ---------------------------------------------------------------------------
def render_runway_panel(df: pd.DataFrame) -> None:
    st.subheader("Cash runway (quarters)")
    if df is None or df.empty:
        st.info("No XBRL runway data.")
        return
    show = df.copy()
    if "runway_quarters" in show.columns:
        show["runway_quarters"] = pd.to_numeric(show["runway_quarters"], errors="coerce").round(1)
    if "cash_eur" in show.columns:
        show["cash_eur"] = show["cash_eur"].apply(lambda v: fmt_eur(float(v) if pd.notna(v) else 0.0))
    if "quarterly_burn_eur" in show.columns:
        show["quarterly_burn_eur"] = show["quarterly_burn_eur"].apply(
            lambda v: fmt_eur(float(v) if pd.notna(v) else 0.0)
        )
    st.dataframe(show, use_container_width=True, hide_index=True)


# ---------------------------------------------------------------------------
# ETF flows
# ---------------------------------------------------------------------------
def render_etf_flows_panel(panel: pd.DataFrame) -> None:
    st.subheader("Thematic ETF flows (proxy)")
    if panel is None or panel.empty:
        st.info("No ETF flow data.")
        return
    fig = go.Figure()
    for col in panel.columns:
        fig.add_trace(go.Bar(x=panel.index, y=panel[col], name=col))
    fig.update_layout(
        template=PLOTLY_TEMPLATE,
        barmode="relative",
        height=320,
        legend=dict(orientation="h", y=-0.18),
        margin=dict(l=40, r=16, t=20, b=40),
    )
    st.plotly_chart(fig, use_container_width=True)


# ---------------------------------------------------------------------------
# Government / capex
# ---------------------------------------------------------------------------
def render_gov_capex_panel(
    awards: pd.DataFrame,
    dod: pd.DataFrame,
    capex: pd.DataFrame,
) -> None:
    st.subheader("Government spend & hyperscaler capex")
    a, b, c = st.tabs(["DoD programs", "Hyperscaler capex", "SAM.gov awards"])

    with a:
        if dod is None or dod.empty:
            st.info("No DoD program data.")
        else:
            show = dod.copy()
            if "fy_usd_billion" in show.columns:
                show["fy_usd_billion"] = show["fy_usd_billion"].round(2)
            st.dataframe(show, use_container_width=True, hide_index=True)

    with b:
        if capex is None or capex.empty:
            st.info("No hyperscaler capex data.")
        else:
            fig = go.Figure()
            for col in [c for c in capex.columns if c not in ("quarter", "total")]:
                fig.add_trace(go.Bar(x=capex["quarter"], y=capex[col], name=col.upper()))
            fig.update_layout(
                template=PLOTLY_TEMPLATE,
                barmode="stack",
                height=320,
                yaxis_title="USD bn",
                legend=dict(orientation="h", y=-0.18),
                margin=dict(l=40, r=16, t=20, b=40),
            )
            st.plotly_chart(fig, use_container_width=True)
            st.caption(f"Total capex tracked: ${capex['total'].sum():.0f}B over {len(capex)} quarters")

    with c:
        if awards is None or awards.empty:
            st.info("No SAM.gov awards (set SAM_API_KEY).")
        else:
            show = awards.copy()
            if "amount_usd" in show.columns:
                show["amount_usd"] = pd.to_numeric(show["amount_usd"], errors="coerce").round(0)
            st.dataframe(show, use_container_width=True, hide_index=True)
