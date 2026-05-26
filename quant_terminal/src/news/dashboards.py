"""Streamlit render functions for the "News Flow" tab.

All renderers accept already-fetched data (no I/O), use ``PLOTLY_TEMPLATE``
for charts, and namespace widget keys with ``news_*``.

Public render functions
-----------------------
* `render_news_heatmap(agg_df)`  — ticker × day matrix coloured by sentiment.
* `render_news_feed(news_df)`    — chronological article feed with sentiment.
"""
from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from src.news.aggregator import aggregate_to_matrix
from src.news.sentiment import score_headline
from src.viz.theme import PALETTE, PLOTLY_TEMPLATE


def _apply_template(fig: go.Figure) -> go.Figure:
    fig.update_layout(**PLOTLY_TEMPLATE["layout"])
    return fig


def _sentiment_badge(value: float) -> str:
    """Coloured monospace pill (HTML) for sentiment values in [-1, 1]."""
    if value is None or pd.isna(value):
        return f"<span style='color:{PALETTE.fg_muted}'>n/a</span>"
    if value > 0.15:
        col = PALETTE.profit
        glyph = "+"
    elif value < -0.15:
        col = PALETTE.loss
        glyph = ""
    else:
        col = PALETTE.fg_muted
        glyph = ""
    return (
        f"<span style='color:{col}; font-family: monospace;'>"
        f"{glyph}{value:.2f}</span>"
    )


# ---------------------------------------------------------------------------
# 1. Heatmap
# ---------------------------------------------------------------------------
def render_news_heatmap(agg_df: pd.DataFrame | None) -> None:
    """Heatmap ticker × day with article counts as text and sentiment as colour."""
    st.markdown("#### News heatmap — articles & sentiment")
    st.caption("Sentiment is heuristic — treat as indicative, not predictive.")
    if agg_df is None or agg_df.empty:
        st.info("No news headlines aggregated yet.")
        return
    counts, senti = aggregate_to_matrix(agg_df)
    if counts.empty:
        st.info("Heatmap matrix is empty.")
        return

    # ensure same axis order
    senti = senti.reindex_like(counts)
    x_labels = [str(d) for d in counts.columns]
    z = senti.values
    text = counts.astype(str).values

    fig = go.Figure(go.Heatmap(
        z=z,
        x=x_labels,
        y=counts.index.tolist(),
        text=text,
        texttemplate="%{text}",
        colorscale=[
            [0.0, PALETTE.loss],
            [0.5, PALETTE.fg_muted],
            [1.0, PALETTE.profit],
        ],
        zmin=-1.0, zmax=1.0,
        colorbar=dict(title="sentiment", thickness=12),
        hovertemplate=(
            "Ticker: %{y}<br>Day: %{x}<br>"
            "Articles: %{text}<br>Sentiment: %{z:.2f}<extra></extra>"
        ),
    ))
    _apply_template(fig)
    fig.update_layout(
        title="Daily news volume + sentiment",
        height=max(300, 28 * max(len(counts.index), 4)),
        xaxis=dict(side="top"),
    )
    st.plotly_chart(fig, use_container_width=True, key="news_heatmap")


# ---------------------------------------------------------------------------
# 2. Feed
# ---------------------------------------------------------------------------
def render_news_feed(news_df: pd.DataFrame | None, max_rows: int = 50) -> None:
    """Reverse-chronological article list with sentiment badges."""
    st.markdown("#### News feed")
    if news_df is None or news_df.empty:
        st.info("No headlines fetched.")
        return

    df = news_df.copy()
    if "sentiment" not in df.columns and "title" in df.columns:
        df["sentiment"] = df["title"].astype(str).map(score_headline)
    if "ts" in df.columns:
        df["ts"] = pd.to_datetime(df["ts"], errors="coerce")
        df = df.sort_values("ts", ascending=False)
    df = df.head(max_rows).reset_index(drop=True)
    n = len(df)

    def _col(name: str, default):
        if name in df.columns:
            return df[name]
        return pd.Series([default] * n)

    # Render as a dataframe with a link column + a styled sentiment column.
    if "ts" in df.columns:
        when = pd.to_datetime(df["ts"], errors="coerce").dt.strftime("%Y-%m-%d %H:%M")
    else:
        when = pd.Series(["—"] * n)
    show = pd.DataFrame({
        "When": when,
        "Ticker": _col("ticker", "—"),
        "Title": _col("title", ""),
        "Source": _col("source", ""),
        "Sentiment": pd.to_numeric(_col("sentiment", 0.0), errors="coerce").round(2),
        "Link": _col("link", ""),
    })
    st.dataframe(
        show,
        hide_index=True,
        use_container_width=True,
        column_config={
            "Link": st.column_config.LinkColumn("Link", display_text="open"),
            "Sentiment": st.column_config.NumberColumn(
                "Sent.", format="%.2f", min_value=-1.0, max_value=1.0,
            ),
        },
        key="news_feed_table",
    )
