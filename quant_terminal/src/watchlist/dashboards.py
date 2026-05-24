"""Streamlit render blocks for the Watchlists tab.

Public API (all `render_*` functions are pure UI — fetches happen in
`app.py` and the resulting DataFrames are passed in):

    render_watchlist_tabbed(quantum_df, photonics_df, defense_df, pre_ipo_df)
    render_ticker_mini_card(payload)
    render_private_table(pre_ipo_df)

All Streamlit widget keys are namespaced `watchlist_{list_name}_{ticker}`
to keep them stable across reruns and avoid clashes with other clusters.
"""
from __future__ import annotations

from typing import Any

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from src.viz.theme import PALETTE, PLOTLY_TEMPLATE, color_pct, fmt_eur, fmt_pct

CONVICTION_BADGE_COLOURS: dict[str, str] = {
    "core": PALETTE.profit,
    "high": PALETTE.bull_body,
    "medium": PALETTE.warning,
    "speculative": "#8B5CF6",
    "private": PALETTE.fg_muted,
}


# ----------------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------------
def _badge(text: str, colour: str) -> str:
    return (
        f"<span style='background:{colour}22;color:{colour};"
        "padding:2px 8px;border-radius:6px;font-size:0.72rem;"
        "letter-spacing:0.04em;text-transform:uppercase;font-weight:600;'>"
        f"{text}</span>"
    )


def _pct_html(value: float | None) -> str:
    if value is None or pd.isna(value):
        return "<span style='color:#94A3B8'>n/a</span>"
    colour = color_pct(float(value))
    return f"<span style='color:{colour};font-family:Fira Code,monospace;font-weight:600;'>{fmt_pct(float(value))}</span>"


def _spark_figure(index: list[str], values: list[float]) -> go.Figure | None:
    if not values or not index or len(values) < 2:
        return None
    colour = PALETTE.profit if values[-1] >= values[0] else PALETTE.loss
    fig = go.Figure(
        go.Scatter(
            x=index,
            y=values,
            mode="lines",
            line={"color": colour, "width": 1.5},
            hoverinfo="skip",
            fill="tozeroy",
            fillcolor=f"{colour}22",
        )
    )
    fig.update_layout(**PLOTLY_TEMPLATE["layout"])
    fig.update_layout(
        height=80,
        margin={"l": 0, "r": 0, "t": 4, "b": 4},
        xaxis={"visible": False, "showgrid": False},
        yaxis={"visible": False, "showgrid": False},
        showlegend=False,
    )
    return fig


# ----------------------------------------------------------------------------
# Mini card
# ----------------------------------------------------------------------------
def render_ticker_mini_card(payload: dict[str, Any]) -> None:
    """Render one ticker tile from a `mini_card_payload(...)` dict."""
    sym = payload.get("symbol", "?")
    list_name = payload.get("list_name", "unknown")
    key_base = f"watchlist_{list_name}_{sym}"

    with st.container(border=True):
        # --- Header row: symbol + conviction badge + sub-theme -------------
        head_cols = st.columns([3, 2])
        with head_cols[0]:
            st.markdown(
                f"<div style='font-size:1.15rem;font-weight:700;font-family:Fira Code,monospace;'>"
                f"{sym}</div>"
                f"<div style='color:#94A3B8;font-size:0.78rem'>{payload.get('sub_theme', '')}</div>",
                unsafe_allow_html=True,
            )
        with head_cols[1]:
            conv = str(payload.get("conviction", "medium")).lower()
            badge_html = _badge(conv, CONVICTION_BADGE_COLOURS.get(conv, PALETTE.fg_muted))
            st.markdown(
                f"<div style='text-align:right'>{badge_html}</div>",
                unsafe_allow_html=True,
            )

        # --- Price + sparkline --------------------------------------------
        spark = payload.get("sparkline") or {}
        body_cols = st.columns([2, 3])
        with body_cols[0]:
            last_eur = payload.get("last_close_eur")
            price_str = fmt_eur(float(last_eur), decimals=2) if last_eur is not None else "n/a"
            st.markdown(
                f"<div style='font-family:Fira Code,monospace;font-size:1.1rem;font-weight:600'>"
                f"{price_str}</div>"
                f"<div style='color:#94A3B8;font-size:0.7rem'>last close (EUR)</div>",
                unsafe_allow_html=True,
            )
        with body_cols[1]:
            fig = _spark_figure(spark.get("index", []), spark.get("values", []))
            if fig is not None:
                st.plotly_chart(
                    fig,
                    use_container_width=True,
                    config={"displayModeBar": False},
                    key=f"{key_base}_spark",
                )

        # --- Returns grid (1D/1W/1M/3M/YTD) -------------------------------
        ret_cols = st.columns(5)
        for col, label, field in zip(
            ret_cols,
            ["1D", "1W", "1M", "3M", "YTD"],
            ["ret_1d", "ret_1w", "ret_1m", "ret_3m", "ret_ytd"],
        ):
            with col:
                st.markdown(
                    f"<div style='color:#94A3B8;font-size:0.65rem;text-transform:uppercase'>{label}</div>"
                    f"{_pct_html(payload.get(field))}",
                    unsafe_allow_html=True,
                )

        # --- Catalyst + peers --------------------------------------------
        catalyst = payload.get("catalyst")
        if catalyst:
            st.markdown(
                f"<div style='margin-top:6px;font-size:0.78rem;color:#CBD5E1'>"
                f"<span style='color:#94A3B8'>Catalyst:</span> {catalyst}</div>",
                unsafe_allow_html=True,
            )
        peers = payload.get("peers") or []
        if peers:
            st.markdown(
                f"<div style='margin-top:2px;font-size:0.72rem;color:#94A3B8'>"
                f"Peers: {', '.join(peers)}</div>",
                unsafe_allow_html=True,
            )


# ----------------------------------------------------------------------------
# Grid for a single watchlist
# ----------------------------------------------------------------------------
def _payload_from_row(row: pd.Series) -> dict[str, Any]:
    """Inline payload builder so this dashboard works even without a
    pre-fetched sparkline panel."""
    from src.watchlist.mini_card import mini_card_payload

    return mini_card_payload(row, prices_eur=None)


def render_watchlist_grid(
    list_df: pd.DataFrame,
    *,
    list_name: str,
    cols_per_row: int = 3,
    sparkline_panel: pd.DataFrame | None = None,
) -> None:
    """Render every ticker in a single watchlist as a grid of mini cards."""
    if list_df is None or list_df.empty:
        st.info(f"Watchlist '{list_name}' is empty.")
        return

    df = list_df.copy()
    df["__conv_order"] = df["conviction"].map(
        {"core": 0, "high": 1, "medium": 2, "speculative": 3, "private": 4}
    ).fillna(5)
    df = df.sort_values(["__conv_order", "symbol"]).drop(columns="__conv_order")

    rows = [df.iloc[i : i + cols_per_row] for i in range(0, len(df), cols_per_row)]
    from src.watchlist.mini_card import mini_card_payload

    for chunk in rows:
        cols = st.columns(cols_per_row)
        for slot, (_, row) in zip(cols, chunk.iterrows()):
            with slot:
                spark_series = None
                if (
                    sparkline_panel is not None
                    and not sparkline_panel.empty
                    and str(row["symbol"]) in sparkline_panel.columns
                ):
                    spark_series = sparkline_panel[str(row["symbol"])]
                payload = mini_card_payload(row, prices_eur=spark_series)
                render_ticker_mini_card(payload)


# ----------------------------------------------------------------------------
# Private / Pre-IPO table
# ----------------------------------------------------------------------------
def render_private_table(pre_ipo_df: pd.DataFrame) -> None:
    """Compact valuation table for private / pre-IPO names."""
    if pre_ipo_df is None or pre_ipo_df.empty:
        st.info("No private watchlist entries found.")
        return

    df = pre_ipo_df.copy()
    if "listed_proxies" in df.columns:
        df["listed_proxies"] = df["listed_proxies"].apply(
            lambda x: ", ".join(x) if isinstance(x, (list, tuple)) else (x or "")
        )
    if "latest_valuation_usd_b" in df.columns:
        df["latest_valuation_usd_b"] = df["latest_valuation_usd_b"].apply(
            lambda v: f"${v:.1f}B" if pd.notna(v) else "n/a"
        )

    display_cols = [
        c
        for c in [
            "name",
            "sub_theme",
            "latest_valuation_usd_b",
            "last_round_date",
            "last_round_type",
            "lead_investor",
            "listed_proxies",
        ]
        if c in df.columns
    ]
    st.markdown(
        "<div style='color:#F59E0B;font-size:0.78rem;margin-bottom:8px'>"
        "Valuations approximated — refresh `config/private_watchlist.yaml` manually."
        "</div>",
        unsafe_allow_html=True,
    )
    st.dataframe(df[display_cols], use_container_width=True, hide_index=True)


# ----------------------------------------------------------------------------
# Top-level tabbed entry point
# ----------------------------------------------------------------------------
def render_watchlist_tabbed(
    quantum_df: pd.DataFrame,
    photonics_df: pd.DataFrame,
    defense_df: pd.DataFrame,
    pre_ipo_df: pd.DataFrame,
    *,
    sparkline_panel: pd.DataFrame | None = None,
) -> None:
    """Tabbed renderer for the "Watchlists" top-level tab.

    Parameters
    ----------
    quantum_df / photonics_df / defense_df: outputs of
        `add_live_prices(load_watchlist(<name>), ...)`.
    pre_ipo_df: output of `load_private_watchlist()`.
    sparkline_panel: optional shared price panel (wide DataFrame, EUR or
        listing currency) used to draw mini sparklines without refetching.
    """
    sub_tabs = st.tabs(["Quantum", "Photonics", "Defense", "Pre-IPO"])
    with sub_tabs[0]:
        render_watchlist_grid(
            quantum_df, list_name="quantum", sparkline_panel=sparkline_panel
        )
    with sub_tabs[1]:
        render_watchlist_grid(
            photonics_df, list_name="photonics", sparkline_panel=sparkline_panel
        )
    with sub_tabs[2]:
        render_watchlist_grid(
            defense_df, list_name="defense", sparkline_panel=sparkline_panel
        )
    with sub_tabs[3]:
        render_private_table(pre_ipo_df)
