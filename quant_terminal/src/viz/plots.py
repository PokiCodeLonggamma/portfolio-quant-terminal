"""Chart helpers — Plotly for analytics, lightweight-charts for price action."""
from __future__ import annotations

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from src.viz.theme import PALETTE, PLOTLY_TEMPLATE


def _apply_template(fig: go.Figure) -> go.Figure:
    fig.update_layout(**PLOTLY_TEMPLATE["layout"])
    return fig


def pie_allocation(series: pd.Series, title: str, hole: float = 0.55) -> go.Figure:
    fig = px.pie(values=series.values, names=series.index, hole=hole, title=title)
    fig.update_traces(textinfo="label+percent", textfont={"size": 11})
    return _apply_template(fig)


def bar_horizontal(series: pd.Series, title: str, colour: str | None = None) -> go.Figure:
    s = series.sort_values()
    colours = [PALETTE.profit if v >= 0 else PALETTE.loss for v in s.values] if colour is None else None
    fig = go.Figure(go.Bar(
        x=s.values, y=s.index, orientation="h",
        marker_color=colours if colours else colour,
    ))
    fig.update_layout(title=title)
    return _apply_template(fig)


def equity_curve(series: pd.Series, title: str = "Cumulative PnL (EUR)") -> go.Figure:
    fig = go.Figure(go.Scatter(
        x=series.index, y=series.values,
        mode="lines", line={"color": PALETTE.accent, "width": 2},
        name="PnL",
    ))
    fig.update_layout(title=title, yaxis_title="EUR")
    return _apply_template(fig)


def drawdown_chart(dd: pd.Series, title: str = "Drawdown") -> go.Figure:
    fig = go.Figure(go.Scatter(
        x=dd.index, y=dd.values * 100,
        mode="lines", fill="tozeroy",
        line={"color": PALETTE.loss, "width": 1},
        fillcolor="rgba(239, 68, 68, 0.25)",
        name="Drawdown %",
    ))
    fig.update_layout(title=title, yaxis_title="%")
    return _apply_template(fig)


def heatmap_correlation(corr: pd.DataFrame, title: str = "Correlations") -> go.Figure:
    fig = go.Figure(go.Heatmap(
        z=corr.values, x=corr.columns, y=corr.index,
        colorscale=[
            [0.0, PALETTE.loss],
            [0.5, PALETTE.bg],
            [1.0, PALETTE.bull_body],
        ],
        zmin=-1, zmax=1,
    ))
    fig.update_layout(title=title)
    return _apply_template(fig)


def scenario_bar(scenario_df: pd.DataFrame) -> go.Figure:
    s = scenario_df.set_index("scenario")["portfolio_pct"].sort_values()
    colours = [PALETTE.profit if v >= 0 else PALETTE.loss for v in s.values]
    fig = go.Figure(go.Bar(
        x=s.values * 100, y=s.index, orientation="h",
        marker_color=colours,
        text=[f"{v*100:+.1f}%" for v in s.values],
        textposition="outside",
    ))
    fig.update_layout(title="Stress scenarios — portfolio impact", xaxis_title="%")
    return _apply_template(fig)


def lightweight_candles(prices: pd.DataFrame, title: str = "") -> dict:
    """Build a lightweight-charts payload (used via streamlit-lightweight-charts).

    `prices` columns expected: open, high, low, close (lower- or upper-case OK).
    Returns a series-config dict consumable by `renderLightweightCharts`.
    """
    cols = {c.lower(): c for c in prices.columns}
    needed = {"open", "high", "low", "close"}
    if not needed.issubset(cols):
        raise ValueError(f"OHLC required; saw {list(prices.columns)}")
    df = prices.copy().rename(columns={cols[k]: k for k in cols})
    df = df.dropna(subset=["open", "high", "low", "close"])
    df.index = pd.to_datetime(df.index).strftime("%Y-%m-%d")

    candles = [
        {"time": t, "open": float(r.open), "high": float(r.high),
         "low": float(r.low), "close": float(r.close)}
        for t, r in df.iterrows()
    ]
    return {
        "chart": {
            "height": 480,
            "layout": {
                "background": {"type": "solid", "color": PALETTE.bg},
                "textColor": PALETTE.fg,
            },
            "grid": {
                "vertLines": {"color": "#1F2937"},
                "horzLines": {"color": "#1F2937"},
            },
            "timeScale": {"timeVisible": True, "secondsVisible": False},
        },
        "series": [
            {
                "type": "Candlestick",
                "data": candles,
                "options": {
                    "upColor": PALETTE.bull_body,
                    "downColor": PALETTE.bear_body,
                    "borderVisible": False,
                    "wickUpColor": PALETTE.bull_body,
                    "wickDownColor": PALETTE.bear_body,
                },
            }
        ],
    }


def line_from_close(close: pd.Series, title: str = "") -> go.Figure:
    fig = go.Figure(go.Scatter(
        x=close.index, y=close.values, mode="lines",
        line={"color": PALETTE.accent, "width": 1.4},
    ))
    fig.update_layout(title=title)
    return _apply_template(fig)
