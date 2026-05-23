"""Centralised design tokens.

Palette: "Financial Dashboard Dark" (from UI/UX Pro Max skill).
Typography: "Dashboard Data" pairing — Fira Sans (body) + Fira Code (numbers).
Charts: TradingView-grade colours for candles + Plotly continuous scales.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Palette:
    # Surfaces
    bg: str = "#020617"
    card: str = "#0E1223"
    muted_bg: str = "#1A1E2F"
    border: str = "#334155"

    # Text
    fg: str = "#F8FAFC"
    fg_muted: str = "#94A3B8"

    # Brand
    primary: str = "#0F172A"
    secondary: str = "#1E293B"
    accent: str = "#22C55E"   # also used for profit
    ring: str = "#0F172A"

    # Semantic
    profit: str = "#22C55E"
    loss: str = "#EF4444"
    warning: str = "#F59E0B"
    neutral: str = "#6B7280"

    # Trading candles (TradingView convention)
    bull_body: str = "#26A69A"
    bear_body: str = "#EF5350"
    volume_up: str = "rgba(38, 166, 154, 0.4)"
    volume_down: str = "rgba(239, 83, 80, 0.4)"


PALETTE = Palette()

FONT_BODY = "Fira Sans, ui-sans-serif, system-ui, sans-serif"
FONT_MONO = "Fira Code, ui-monospace, SFMono-Regular, monospace"

# Plotly base template (dark, dense)
PLOTLY_TEMPLATE = {
    "layout": {
        "paper_bgcolor": PALETTE.bg,
        "plot_bgcolor": PALETTE.bg,
        "font": {"color": PALETTE.fg, "family": FONT_BODY, "size": 12},
        "colorway": [
            PALETTE.accent, PALETTE.bull_body, PALETTE.warning, "#8B5CF6",
            "#06B6D4", "#F97316", "#EC4899", "#10B981",
        ],
        "xaxis": {
            "gridcolor": "#1F2937",
            "zerolinecolor": "#1F2937",
            "color": PALETTE.fg_muted,
            "linecolor": PALETTE.border,
        },
        "yaxis": {
            "gridcolor": "#1F2937",
            "zerolinecolor": "#1F2937",
            "color": PALETTE.fg_muted,
            "linecolor": PALETTE.border,
        },
        "legend": {"bgcolor": "rgba(0,0,0,0)", "font": {"color": PALETTE.fg}},
        "margin": {"l": 40, "r": 16, "t": 36, "b": 32},
    }
}


def inject_streamlit_css() -> str:
    """Return a single CSS block to be dropped into `st.markdown(..., unsafe_allow_html=True)`."""
    p = PALETTE
    return f"""
    <style>
      @import url('https://fonts.googleapis.com/css2?family=Fira+Sans:wght@300;400;500;600;700&family=Fira+Code:wght@400;500;600;700&display=swap');

      html, body, [class*="st-"] {{
        font-family: {FONT_BODY};
      }}
      .stApp {{
        background-color: {p.bg};
        color: {p.fg};
      }}
      .block-container {{
        padding-top: 1.2rem;
        padding-bottom: 4rem;
        max-width: 1400px;
      }}
      h1, h2, h3, h4 {{
        color: {p.fg};
        letter-spacing: -0.01em;
      }}
      /* KPI / metric cards */
      div[data-testid="stMetric"] {{
        background: {p.card};
        border: 1px solid {p.border};
        border-radius: 10px;
        padding: 14px 18px;
      }}
      div[data-testid="stMetricValue"] {{
        font-family: {FONT_MONO};
        font-weight: 600;
        font-size: 1.45rem;
      }}
      div[data-testid="stMetricLabel"] {{
        color: {p.fg_muted};
        text-transform: uppercase;
        letter-spacing: 0.05em;
        font-size: 0.72rem;
      }}
      /* Tabs */
      div[data-baseweb="tab-list"] {{
        gap: 4px;
      }}
      button[data-baseweb="tab"] {{
        background: {p.card};
        border-radius: 8px 8px 0 0;
        color: {p.fg_muted};
        border-bottom: 2px solid transparent;
      }}
      button[data-baseweb="tab"][aria-selected="true"] {{
        color: {p.fg};
        border-bottom: 2px solid {p.accent};
      }}
      /* DataFrames */
      div[data-testid="stDataFrame"] {{
        background: {p.card};
        border: 1px solid {p.border};
        border-radius: 8px;
      }}
      /* Code/data text monospace */
      code, pre, kbd, samp {{
        font-family: {FONT_MONO};
      }}
      .pnl-positive {{ color: {p.profit}; font-family: {FONT_MONO}; font-weight: 600; }}
      .pnl-negative {{ color: {p.loss};   font-family: {FONT_MONO}; font-weight: 600; }}
      .pnl-neutral  {{ color: {p.fg_muted}; font-family: {FONT_MONO}; }}
    </style>
    """


def fmt_eur(value: float, decimals: int = 0) -> str:
    sign = "-" if value < 0 else ""
    return f"{sign}€{abs(value):,.{decimals}f}".replace(",", " ").replace(" ", " ")


def fmt_pct(value: float, decimals: int = 2) -> str:
    return f"{value * 100:+.{decimals}f}%"


def color_pct(value: float) -> str:
    if value > 0:
        return PALETTE.profit
    if value < 0:
        return PALETTE.loss
    return PALETTE.fg_muted
