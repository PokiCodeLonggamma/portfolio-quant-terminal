"""Zoom-in view for a single ticker — used by both Short Squeeze tabs.

Combines:
  * TradingView Advanced Chart embed (free, iframe-based, no API key)
  * Live GEX profile (pulled via fetch_chain + compute_gex)
  * Headline KPIs (current squeeze score, short float, DTC, RSI, ATR)
  * Latest news headlines + sentiment

The component is **read-only** — it just visualises whatever `details` /
`gex_df` / `news_df` you pass it. Heavy data fetching lives outside.
"""
from __future__ import annotations

from typing import Any

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from src.viz.theme import PALETTE, hex_to_rgba


# ---------------------------------------------------------------------------
# TradingView Advanced Chart — free embed, no key needed
# ---------------------------------------------------------------------------
def tradingview_advanced_chart(
    symbol: str, *, height: int = 460, theme: str = "dark",
    interval: str = "D", studies: list[str] | None = None,
) -> None:
    """Embed the official TradingView Advanced Chart widget via iframe.

    `symbol` should be a TradingView-recognised identifier, typically
    ``"NASDAQ:AAPL"`` or just ``"AAPL"`` (TV auto-resolves the exchange).
    Defaults to daily timeframe + 3 popular studies (RSI, MACD, BB).
    """
    studies = studies or ["RSI@tv-basicstudies", "MACD@tv-basicstudies",
                            "BB@tv-basicstudies"]
    studies_js = ",".join(f'"{s}"' for s in studies)
    html = f"""
    <div id="tradingview_chart_{symbol.replace(':', '_').replace('=', '_').replace('^', '_')}"
         style="height:{height}px;border-radius:8px;overflow:hidden;"></div>
    <script src="https://s3.tradingview.com/tv.js"></script>
    <script>
      new TradingView.widget({{
        "container_id": "tradingview_chart_{symbol.replace(':', '_').replace('=', '_').replace('^', '_')}",
        "symbol": "{symbol}",
        "interval": "{interval}",
        "timezone": "Etc/UTC",
        "theme": "{theme}",
        "style": "1",
        "locale": "en",
        "toolbar_bg": "#0B0F14",
        "enable_publishing": false,
        "hide_side_toolbar": false,
        "allow_symbol_change": true,
        "studies": [{studies_js}],
        "height": "100%",
        "width": "100%",
      }});
    </script>
    """
    st.components.v1.html(html, height=height + 20, scrolling=False)


# ---------------------------------------------------------------------------
# Mini GEX chart — re-used inside the zoom card
# ---------------------------------------------------------------------------
def mini_gex_chart(gex_df: pd.DataFrame, spot: float | None = None,
                    flip: float | None = None, ticker: str = "?") -> None:
    if gex_df is None or gex_df.empty:
        st.info("No GEX data — chain missing greeks or OI.")
        return
    colours = [
        PALETTE.profit if v >= 0 else PALETTE.loss
        for v in gex_df["net_gex_usd"]
    ]
    fig = go.Figure(go.Bar(
        x=gex_df["strike"], y=gex_df["net_gex_usd"],
        marker_color=colours,
        name="Net GEX ($)",
    ))
    if spot is not None and spot > 0:
        fig.add_vline(x=spot, line_dash="dot", line_color=PALETTE.fg,
                      annotation_text=f"Spot {spot:.2f}", annotation_position="top")
    if flip is not None:
        fig.add_vline(x=flip, line_dash="dash", line_color=PALETTE.warning,
                      annotation_text=f"γ-flip {flip:.2f}",
                      annotation_position="bottom")
    fig.update_layout(
        template="plotly_dark",
        title=f"Net GEX per strike — {ticker}",
        xaxis_title="Strike",
        yaxis_title="Net GEX (USD)",
        height=320,
        margin=dict(l=40, r=20, t=50, b=40),
        plot_bgcolor=PALETTE.bg_elev,
        paper_bgcolor=PALETTE.bg,
        font_color=PALETTE.fg,
        showlegend=False,
    )
    st.plotly_chart(fig, use_container_width=True, key=f"zoom_gex_{ticker}")


# ---------------------------------------------------------------------------
# KPI strip
# ---------------------------------------------------------------------------
def kpi_strip(details: dict[str, Any]) -> None:
    """Headline metrics for the zoomed-in ticker."""
    cols = st.columns(6)
    score = details.get("score_total") or details.get("score") or 0.0
    signal = details.get("signal", "—")
    sf = details.get("short_float", details.get("ShortFloat", 0)) or 0
    dtc = details.get("days_to_cover", details.get("DaysToCover", 0)) or 0
    inst = details.get("inst_trans", details.get("inst_trans_pct", 0)) or 0
    price = details.get("price", 0) or 0

    sf_pct = sf * 100 if sf < 1 else sf
    inst_pct = inst * 100 if abs(inst) < 1 else inst

    cols[0].metric("Signal", signal)
    cols[1].metric("Score", f"{float(score):.1f} / 10")
    cols[2].metric("Short Float", f"{sf_pct:.1f}%")
    cols[3].metric("Days to Cover", f"{float(dtc):.1f}")
    cols[4].metric("Inst. Δ (90d)", f"{inst_pct:+.1f}%")
    cols[5].metric("Last", f"{price:.2f}" if price else "—")


# ---------------------------------------------------------------------------
# Composite zoom view
# ---------------------------------------------------------------------------
def render_squeeze_zoom(
    ticker: str,
    details: dict[str, Any],
    *,
    gex_df: pd.DataFrame | None = None,
    spot: float | None = None,
    gamma_flip: float | None = None,
    pillar_details: dict[str, dict] | None = None,
) -> None:
    """Full-page drill-down on a single squeeze candidate."""
    accent = (
        PALETTE.loss if (details.get("score_total") or 0) >= 7
        else PALETTE.warning if (details.get("score_total") or 0) >= 5
        else PALETTE.fg_muted
    )
    st.markdown(
        f"""
        <div style='padding:14px 18px;border-radius:12px;border-left:6px solid {accent};
                    background:{hex_to_rgba(accent, 0.08)};margin-bottom:12px;'>
            <div style='font-size:12px;color:{PALETTE.fg_muted};letter-spacing:0.08em;
                        text-transform:uppercase;'>Drill-down</div>
            <div style='font-size:28px;font-weight:700;color:{accent};margin-top:2px;
                        font-family:monospace;'>{ticker}</div>
            <div style='font-size:13px;color:{PALETTE.fg};margin-top:2px;'>
                {details.get('sector', '')} ·
                {details.get('signal', '')} ·
                Sect cap {(details.get('market_cap', 0) or 0) / 1e9:.1f}B$
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    kpi_strip(details)

    st.markdown("##### 📊 Price + technicals (TradingView)")
    tradingview_advanced_chart(ticker, height=480, theme="dark")

    if gex_df is not None and not gex_df.empty:
        st.markdown("##### ⚙️ Net Gamma Exposure profile")
        mini_gex_chart(gex_df, spot=spot, flip=gamma_flip, ticker=ticker)

    if pillar_details:
        st.markdown("##### 🏛️ Pillar drill-down")
        pcols = st.columns(2)
        for i, (name, d) in enumerate(pillar_details.items()):
            with pcols[i % 2]:
                st.markdown(f"**{name}**")
                if not d:
                    st.caption("—")
                    continue
                for k, v in d.items():
                    st.markdown(f"- `{k}` — {v}")
