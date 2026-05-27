"""TradingView Advanced Chart embed — reusable candlestick component.

CDC §1 deliverable: a single import the whole dashboard can use to drop a
clickable TradingView chart next to any ticker.

Three usage patterns
--------------------
1. **Inline**: just render the widget in the current container.
       render_tv_chart("ES")          # candlestick, daily, default 480px

2. **Modal/expander on click** (the CDC-preferred pattern):
       render_tv_chart_expander("ES", label="📈 Chart ES")

3. **Clickable table** (one row → one expander, reusable for matrices):
       render_clickable_ticker_table(df, ticker_col="logical")

The widget is the free TradingView iframe — no API key, works on Streamlit
Cloud out of the box. We resolve `logical → tradingview symbol` via
`src.universe.cross_asset.resolve_symbol`. Fallback chain when no TV symbol
is mapped: we try `EXCHANGE:TICKER` heuristics, then raw ticker.
"""
from __future__ import annotations

import html
import uuid
from typing import Iterable, Literal

import pandas as pd
import streamlit as st

try:
    from src.universe.cross_asset import get_universe, resolve_symbol
except Exception:  # circular / import-time safety
    get_universe = None        # type: ignore[assignment]
    resolve_symbol = None      # type: ignore[assignment]


Interval = Literal["1", "5", "15", "60", "240", "D", "W", "M"]

# ---------------------------------------------------------------------------
# Symbol heuristics for tickers not in the YAML
# ---------------------------------------------------------------------------
_TV_HEURISTICS: dict[str, str] = {
    # yfinance suffix → TV prefix
    ".PA": "EURONEXT:",
    ".DE": "XETR:",
    ".L": "LSE:",
    ".MI": "MIL:",
    ".SW": "SIX:",
    ".HK": "HKEX:",
    ".TO": "TSX:",
    ".V": "TSXV:",
    ".AS": "AMS:",
}

_YF_FUTURES_TO_TV: dict[str, str] = {
    "ES=F": "CME_MINI:ES1!",  "NQ=F": "CME_MINI:NQ1!",  "YM=F": "CBOT_MINI:YM1!",
    "RTY=F": "CME_MINI:RTY1!","MES=F": "CME_MINI:MES1!","MNQ=F": "CME_MINI:MNQ1!",
    "MYM=F": "CBOT_MINI:MYM1!","M2K=F": "CME_MINI:M2K1!",
    "VX=F": "CBOE:VX1!",
    "CL=F": "NYMEX:CL1!", "BZ=F": "ICEEUR:B1!", "NG=F": "NYMEX:NG1!",
    "QM=F": "NYMEX:QM1!", "MCL=F": "NYMEX:MCL1!","MNG=F": "NYMEX:MNG1!",
    "HO=F": "NYMEX:HO1!", "RB=F": "NYMEX:RB1!",
    "GC=F": "COMEX:GC1!", "SI=F": "COMEX:SI1!", "HG=F": "COMEX:HG1!",
    "MGC=F": "COMEX_MINI:MGC1!","SIL=F": "COMEX_MINI:SIL1!","MHG=F": "COMEX_MINI:MHG1!",
    "PL=F": "NYMEX:PL1!", "PA=F": "NYMEX:PA1!",
    "BTC=F": "CME:BTC1!", "ETH=F": "CME:ETH1!",
    "ZN=F": "CBOT:ZN1!", "ZB=F": "CBOT:ZB1!", "ZF=F": "CBOT:ZF1!", "ZT=F": "CBOT:ZT1!",
    "DX=F": "TVC:DXY",
    "FDAX=F": "EUREX:FDAX1!", "FESX=F": "EUREX:FESX1!", "FCE=F": "MATIF:FCE1!",
    "Z=F": "ICEEUR:Z1!", "FSMI=F": "EUREX:FSMI1!",
    "^VIX": "CBOE:VIX", "^GSPC": "SP:SPX", "^NDX": "NASDAQ:NDX", "^DJI": "DJ:DJI",
    "^RUT": "CBOE:RUT", "^FCHI": "EURONEXT:PX1", "^GDAXI": "XETR:DAX",
    "^STOXX50E": "INDEX:SX5E", "^FTSE": "FTSE:UKX", "^TNX": "TVC:US10Y",
    "^FVX": "TVC:US05Y", "^IRX": "TVC:US02Y", "^VVIX": "CBOE:VVIX",
}


def _heuristic_tv_symbol(ticker: str) -> str:
    """Best-effort mapping when no explicit YAML entry exists."""
    t = ticker.strip()
    if not t:
        return ""
    # Crypto pairs
    if "-" in t and t.upper().endswith(("-USD", "-EUR")):
        base, quote = t.upper().split("-", 1)
        return f"COINBASE:{base}{quote}"
    # Futures via yfinance suffix
    if t in _YF_FUTURES_TO_TV:
        return _YF_FUTURES_TO_TV[t]
    # European listings
    for suffix, prefix in _TV_HEURISTICS.items():
        if t.endswith(suffix):
            return prefix + t.split(".", 1)[0]
    # Plain US equity / ETF — TradingView accepts bare ticker.
    return t


def tv_symbol_for(ticker: str) -> str:
    """Public helper: logical → TV symbol with full fallback chain."""
    if not ticker:
        return ""
    if resolve_symbol is not None:
        try:
            mapped = resolve_symbol(ticker, "tradingview")
            if mapped and mapped != ticker:
                return mapped
        except Exception:
            pass
    return _heuristic_tv_symbol(ticker)


# ---------------------------------------------------------------------------
# Core widget renderer
# ---------------------------------------------------------------------------
_TV_WIDGET_HTML = """
<div class="tradingview-widget-container" style="height:{height}px; width:100%;">
  <div id="{container_id}" style="height:100%; width:100%;"></div>
  <script type="text/javascript" src="https://s3.tradingview.com/tv.js"></script>
  <script type="text/javascript">
    new TradingView.widget({{
      "autosize": true,
      "symbol": "{symbol}",
      "interval": "{interval}",
      "timezone": "Etc/UTC",
      "theme": "dark",
      "style": "1",
      "locale": "en",
      "enable_publishing": false,
      "withdateranges": true,
      "hide_side_toolbar": false,
      "allow_symbol_change": true,
      "container_id": "{container_id}",
      "studies": {studies_json},
      "save_image": false,
      "details": {details_lower},
      "hotlist": false,
      "calendar": false,
      "show_popup_button": true,
      "popup_width": "1000",
      "popup_height": "650",
      "toolbar_bg": "#0F1525",
      "backgroundColor": "#0A0E1A",
      "gridColor": "#1F2B45"
    }});
  </script>
</div>
"""

_DEFAULT_STUDIES = [
    "STD;VWAP",
    "STD;EMA",
    "STD;RSI",
]


def render_tv_chart(
    ticker: str,
    *,
    interval: Interval = "D",
    height: int = 480,
    studies: list[str] | None = None,
    show_details: bool = True,
    key: str | None = None,
) -> None:
    """Render the TradingView candlestick widget inline.

    Parameters
    ----------
    ticker : logical ticker as found in the YAML (e.g. "ES", "ASTS")
             or a raw symbol (e.g. "AAPL", "BTC-USD").
    interval : "1", "5", "15", "60", "240", "D", "W", "M"
    height : pixel height. 480 default fits a Streamlit row.
    studies : list of TV study IDs. Defaults: VWAP, EMA, RSI.
    show_details : show the side panel with bid/ask/etc.
    key : optional Streamlit key (unused — widget is HTML — but accepted for API symmetry).
    """
    _ = key  # noqa: ARG001
    symbol = tv_symbol_for(ticker) or ticker.upper()
    container_id = f"tv_{uuid.uuid4().hex[:8]}"
    studies_list = studies if studies is not None else _DEFAULT_STUDIES
    studies_json = "[" + ",".join(f'"{s}"' for s in studies_list) + "]"
    html_block = _TV_WIDGET_HTML.format(
        height=int(height),
        container_id=container_id,
        symbol=html.escape(symbol, quote=True),
        interval=html.escape(str(interval), quote=True),
        studies_json=studies_json,
        details_lower=str(bool(show_details)).lower(),
    )
    # streamlit.components is the only way to ship arbitrary <script>.
    st.components.v1.html(html_block, height=int(height) + 12, scrolling=False)


def render_tv_chart_expander(
    ticker: str,
    *,
    label: str | None = None,
    interval: Interval = "D",
    height: int = 460,
    expanded: bool = False,
    studies: list[str] | None = None,
) -> None:
    """The CDC-preferred drilldown pattern: an expander you wrap around the chart.

    Usage::

        render_tv_chart_expander("ES", label="📈 Chart ES (CME E-mini)")
    """
    label = label or f"📈 Chart {ticker}"
    with st.expander(label, expanded=expanded):
        render_tv_chart(ticker, interval=interval, height=height, studies=studies)


# ---------------------------------------------------------------------------
# Clickable matrix helper — drops the drilldown into any tidy DataFrame
# ---------------------------------------------------------------------------
def render_clickable_ticker_table(
    df: pd.DataFrame,
    *,
    ticker_col: str = "logical",
    show_cols: Iterable[str] | None = None,
    interval: Interval = "D",
    height: int = 420,
    key_prefix: str = "tv",
) -> None:
    """Render `df` as a Streamlit dataframe + per-row "📈" expander button.

    The dataframe shows `show_cols` (defaults to all numeric + string cols),
    and below it a radio selector lets the user pick the ticker whose chart
    to open in an expander. Keeps the page clean — no auto-loading 30 iframes.
    """
    if df is None or df.empty:
        st.info("No rows to display.")
        return
    cols = list(show_cols) if show_cols else list(df.columns)
    st.dataframe(df[cols], use_container_width=True, hide_index=True)
    pool = [str(t) for t in df[ticker_col].dropna().unique().tolist()]
    if not pool:
        return
    sel = st.selectbox(
        "🔍 Open TradingView chart for…",
        options=["—"] + pool,
        key=f"{key_prefix}_pick",
    )
    if sel and sel != "—":
        render_tv_chart_expander(
            sel,
            label=f"📈 Chart — {sel}",
            interval=interval,
            height=height,
            expanded=True,
        )


# ---------------------------------------------------------------------------
# Compact preview (mini-chart in tooltips, cards, etc.)
# ---------------------------------------------------------------------------
_TV_MINI_HTML = """
<div class="tradingview-widget-container" style="height:{height}px;">
  <div class="tradingview-widget-container__widget"></div>
  <script type="text/javascript"
    src="https://s3.tradingview.com/external-embedding/embed-widget-mini-symbol-overview.js"
    async>
  {{
    "symbol": "{symbol}",
    "width": "100%",
    "height": {height},
    "locale": "en",
    "dateRange": "{date_range}",
    "colorTheme": "dark",
    "trendLineColor": "rgba(34, 211, 238, 1)",
    "underLineColor": "rgba(34, 211, 238, 0.15)",
    "isTransparent": true,
    "autosize": false,
    "largeChartUrl": ""
  }}
  </script>
</div>
"""


def render_tv_mini(
    ticker: str,
    *,
    height: int = 220,
    date_range: Literal["1D", "1M", "3M", "12M", "60M", "ALL"] = "3M",
) -> None:
    """Tiny line-chart preview — useful next to KPIs without full candlestick weight."""
    symbol = tv_symbol_for(ticker) or ticker.upper()
    block = _TV_MINI_HTML.format(
        symbol=html.escape(symbol, quote=True),
        height=int(height),
        date_range=date_range,
    )
    st.components.v1.html(block, height=int(height) + 8, scrolling=False)
