"""Streamlit renderers for the snapshot & replay UI."""
from __future__ import annotations

from datetime import date

import pandas as pd
import plotly.express as px
import streamlit as st

from src.snapshot.store import history_table, load
from src.viz.theme import PLOTLY_TEMPLATE, fmt_eur


def render_snapshot_history() -> None:
    df = history_table()
    if df.empty:
        st.info("Aucun snapshot encore capturé. Active Live mode pour en générer un par jour.")
        return
    df = df.sort_values("asof")
    st.dataframe(df, use_container_width=True, hide_index=True)

    fig = px.line(df, x="asof", y="net_eur", title="NAV portfolio (EUR)")
    fig.update_layout(**PLOTLY_TEMPLATE["layout"])
    st.plotly_chart(fig, use_container_width=True)


def render_snapshot_replay() -> None:
    df = history_table()
    if df.empty:
        st.info("Pas de snapshot disponible.")
        return
    available = df["asof"].tolist()
    pick = st.selectbox("Date à rejouer", available[::-1], key="snapshot_replay_pick")
    bundle = load(date.fromisoformat(pick))
    if bundle is None:
        st.warning("Snapshot illisible.")
        return
    meta = bundle["meta"]
    cols = st.columns(4)
    cols[0].metric("Net value", fmt_eur(meta.net_value_eur))
    cols[1].metric("Gross long", fmt_eur(meta.gross_long_eur))
    cols[2].metric("Cash", fmt_eur(meta.cash_eur))
    cols[3].metric("Positions", f"{meta.n_positions}")
    if bundle["positions"] is not None and not bundle["positions"].empty:
        st.subheader("Holdings ce jour-là")
        st.dataframe(bundle["positions"], use_container_width=True, hide_index=True)
    if bundle["options"] is not None and not bundle["options"].empty:
        st.subheader("Options ouvertes ce jour-là")
        st.dataframe(bundle["options"], use_container_width=True, hide_index=True)
