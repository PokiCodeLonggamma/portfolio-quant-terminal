"""Modern, decision-oriented rendering for the trading watchlist.

Replaces the bare DataFrame with KPI cards: signed change badge, RSI gauge,
range-position bar, 30-bar sparkline and ATR pill — all colour-coded.
"""
from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from src.viz.theme import PALETTE, hex_to_rgba


def _change_badge_html(chg_pct: float | None) -> str:
    if chg_pct is None:
        return f"<span style='color:{PALETTE.fg_muted}'>—</span>"
    color = PALETTE.profit if chg_pct >= 0 else PALETTE.loss
    arrow = "▲" if chg_pct >= 0 else "▼"
    return (
        f"<span style='display:inline-block;padding:2px 8px;border-radius:6px;"
        f"background:{hex_to_rgba(color, 0.16)};color:{color};font-weight:600;"
        f"font-family:monospace;font-size:13px;'>{arrow} {chg_pct * 100:+.2f}%</span>"
    )


def _rsi_gauge_html(rsi: float | None) -> str:
    if rsi is None:
        return ""
    # Color zones: <30 oversold (green), 30-70 neutral, >70 overbought (red)
    if rsi < 30:
        color = PALETTE.profit
        tag = "OVERSOLD"
    elif rsi > 70:
        color = PALETTE.loss
        tag = "OVERBOUGHT"
    else:
        color = PALETTE.fg_muted
        tag = "NEUTRAL"
    pct = max(0.0, min(100.0, rsi))
    return (
        f"<div style='margin-top:4px;font-size:11px;color:{PALETTE.fg_muted}'>RSI 14</div>"
        f"<div style='position:relative;height:6px;width:100%;background:{PALETTE.bg_elev};"
        f"border-radius:3px;overflow:hidden;'>"
        f"<div style='position:absolute;left:0;top:0;bottom:0;width:{pct}%;"
        f"background:{color};'></div></div>"
        f"<div style='font-size:11px;color:{color};font-family:monospace;margin-top:2px;'>"
        f"{rsi:.0f} · {tag}</div>"
    )


def _range_bar_html(pos: float | None) -> str:
    if pos is None:
        return ""
    pct = max(0.0, min(1.0, pos)) * 100
    color = (
        PALETTE.loss if pct > 80 else
        PALETTE.profit if pct < 20 else
        PALETTE.warning if 40 <= pct <= 60 else PALETTE.fg_muted
    )
    return (
        f"<div style='margin-top:4px;font-size:11px;color:{PALETTE.fg_muted}'>20d range pos</div>"
        f"<div style='position:relative;height:6px;width:100%;background:{PALETTE.bg_elev};"
        f"border-radius:3px;overflow:hidden;'>"
        f"<div style='position:absolute;left:0;top:0;bottom:0;width:{pct}%;"
        f"background:{color};'></div></div>"
        f"<div style='font-size:11px;color:{color};font-family:monospace;margin-top:2px;'>"
        f"{pct:.0f}%</div>"
    )


def _sparkline_fig(spark: list[float], chg_pct: float) -> go.Figure:
    color = PALETTE.profit if (chg_pct or 0) >= 0 else PALETTE.loss
    fig = go.Figure(go.Scatter(
        y=spark,
        mode="lines",
        line=dict(color=color, width=1.6),
        fill="tozeroy",
        fillcolor=hex_to_rgba(color, 0.12),
        hoverinfo="skip",
    ))
    fig.update_layout(
        margin=dict(l=0, r=0, t=0, b=0),
        height=44,
        xaxis=dict(visible=False),
        yaxis=dict(visible=False, range=[min(spark) * 0.995, max(spark) * 1.005]),
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        showlegend=False,
    )
    return fig


def _atr_pill_html(atr_pct: float | None) -> str:
    if atr_pct is None:
        return ""
    pct = atr_pct * 100
    if pct > 4:
        color = PALETTE.loss
        tag = "HIGH VOL"
    elif pct > 2:
        color = PALETTE.warning
        tag = "MED VOL"
    else:
        color = PALETTE.profit
        tag = "LOW VOL"
    return (
        f"<span style='display:inline-block;padding:1px 6px;border-radius:4px;"
        f"background:{hex_to_rgba(color, 0.12)};color:{color};"
        f"font-family:monospace;font-size:10px;font-weight:600;margin-top:4px;'>"
        f"ATR {pct:.1f}% · {tag}</span>"
    )


def _trend_pill_html(trend_pct: float | None) -> str:
    if trend_pct is None:
        return ""
    if trend_pct > 0.005:
        color = PALETTE.profit
        tag = f"↑ TREND +{trend_pct * 100:.1f}%"
    elif trend_pct < -0.005:
        color = PALETTE.loss
        tag = f"↓ TREND {trend_pct * 100:+.1f}%"
    else:
        color = PALETTE.fg_muted
        tag = f"~ FLAT {trend_pct * 100:+.1f}%"
    return (
        f"<span style='display:inline-block;padding:1px 6px;border-radius:4px;"
        f"background:{hex_to_rgba(color, 0.12)};color:{color};"
        f"font-family:monospace;font-size:10px;font-weight:600;margin-top:4px;margin-right:4px;'>"
        f"{tag}</span>"
    )


def render_trading_board(df: pd.DataFrame) -> None:
    """Modern card grid grouped by asset class."""
    if df is None or df.empty:
        st.info("No trading watchlist data — yfinance unreachable or YAML empty.")
        return

    for group_label in df["group"].unique():
        sub = df[df["group"] == group_label].copy().reset_index(drop=True)
        st.markdown(
            f"<div style='margin-top:18px;margin-bottom:6px;"
            f"font-size:12px;color:{PALETTE.fg_muted};letter-spacing:0.08em;"
            f"text-transform:uppercase;font-weight:600;'>{group_label}</div>",
            unsafe_allow_html=True,
        )
        # 3 cards per row
        for i in range(0, len(sub), 3):
            cols = st.columns(3, gap="small")
            for j, col in enumerate(cols):
                if i + j >= len(sub):
                    continue
                row = sub.iloc[i + j]
                with col:
                    _render_one_card(row)


def _render_one_card(row: pd.Series) -> None:
    chg = float(row.get("chg_pct") or 0.0)
    accent = PALETTE.profit if chg >= 0 else PALETTE.loss
    sym = str(row.get("symbol", "?"))
    name = str(row.get("name", "")) or sym
    level = row.get("level", 0.0)
    spark = list(row.get("spark") or [])

    # Header — symbol + name + change badge
    st.markdown(
        f"""
        <div style='background:{PALETTE.card};border:1px solid {PALETTE.border};
                    border-left:4px solid {accent};border-radius:10px;padding:10px 12px;
                    margin-bottom:6px;'>
            <div style='display:flex;justify-content:space-between;align-items:flex-start;'>
                <div>
                    <div style='font-weight:700;font-size:16px;color:{PALETTE.fg};
                                font-family:monospace;'>{sym}</div>
                    <div style='font-size:11px;color:{PALETTE.fg_muted};'>{name}</div>
                </div>
                <div style='text-align:right;'>
                    <div style='font-size:18px;font-weight:600;color:{PALETTE.fg};
                                font-family:monospace;'>{level}</div>
                    {_change_badge_html(chg)}
                </div>
            </div>
            <div style='margin-top:6px;'>
                {_trend_pill_html(row.get('trend_pct'))}
                {_atr_pill_html(row.get('atr_pct'))}
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # Sparkline (Plotly mini)
    if spark and len(spark) >= 5:
        st.plotly_chart(
            _sparkline_fig(spark, chg),
            use_container_width=True,
            config={"displayModeBar": False},
            key=f"sparkline_{sym}",
        )

    # RSI gauge + range bar
    st.markdown(
        f"""
        <div style='padding:0 4px 8px 4px;'>
            {_rsi_gauge_html(row.get('rsi14'))}
            {_range_bar_html(row.get('range_pos_20d'))}
            <div style='margin-top:6px;font-size:10px;color:{PALETTE.fg_muted};
                        text-align:right;font-family:monospace;'>asof {row.get('asof', '—')}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
