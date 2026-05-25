"""Centralised design tokens.

Palette: "Financial Dashboard Dark" (from UI/UX Pro Max skill).
Typography: "Dashboard Data" pairing — Fira Sans (body) + Fira Code (numbers).
Charts: TradingView-grade colours for candles + Plotly continuous scales.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class Palette:
    # Surfaces
    bg: str = "#020617"
    bg_elev: str = "#0B1020"          # one step above bg, for hero
    card: str = "#0E1223"
    card_hover: str = "#141A2E"
    muted_bg: str = "#1A1E2F"
    border: str = "#1F2937"            # finer grid lines (vs 334155 before)
    border_strong: str = "#334155"     # active selections, focus rings

    # Text
    fg: str = "#F8FAFC"
    fg_muted: str = "#94A3B8"
    fg_dim: str = "#64748B"            # tertiary labels, captions

    # Brand
    primary: str = "#0F172A"
    secondary: str = "#1E293B"
    accent: str = "#22C55E"            # profit + main accent
    accent_alt: str = "#06B6D4"        # secondary accent (cyan)
    ring: str = "#0F172A"

    # Semantic
    profit: str = "#22C55E"
    loss: str = "#EF4444"
    warning: str = "#F59E0B"
    info: str = "#3B82F6"
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
            PALETTE.accent_alt, "#F97316", "#EC4899", "#10B981",
        ],
        "xaxis": {
            "gridcolor": PALETTE.border,
            "zerolinecolor": PALETTE.border,
            "color": PALETTE.fg_muted,
            "linecolor": PALETTE.border_strong,
        },
        "yaxis": {
            "gridcolor": PALETTE.border,
            "zerolinecolor": PALETTE.border,
            "color": PALETTE.fg_muted,
            "linecolor": PALETTE.border_strong,
        },
        "legend": {"bgcolor": "rgba(0,0,0,0)", "font": {"color": PALETTE.fg}},
        "margin": {"l": 40, "r": 16, "t": 36, "b": 32},
    }
}


# ---------------------------------------------------------------------------
# CSS — comprehensive Streamlit dark + KPI + tabs + cards + tables
# ---------------------------------------------------------------------------
def inject_streamlit_css() -> str:
    """Return a single CSS block to be dropped into `st.markdown(..., unsafe_allow_html=True)`."""
    p = PALETTE
    return f"""
    <style>
      @import url('https://fonts.googleapis.com/css2?family=Fira+Sans:wght@300;400;500;600;700&family=Fira+Code:wght@400;500;600;700&display=swap');

      :root {{
        --qt-bg: {p.bg};
        --qt-card: {p.card};
        --qt-border: {p.border};
        --qt-fg: {p.fg};
        --qt-fg-muted: {p.fg_muted};
        --qt-accent: {p.accent};
        --qt-profit: {p.profit};
        --qt-loss: {p.loss};
      }}

      html, body, [class*="st-"] {{
        font-family: {FONT_BODY};
      }}
      .stApp {{
        background: radial-gradient(circle at 0% 0%, {p.bg_elev} 0%, {p.bg} 60%);
        color: {p.fg};
      }}

      /* Flatten Streamlit's default header so it doesn't eat the tabs */
      header[data-testid="stHeader"] {{
        background: transparent;
        height: 0;
      }}
      header[data-testid="stHeader"]::before {{ display: none; }}
      div[data-testid="stToolbar"] {{
        z-index: 999;
        background: transparent;
      }}

      .block-container {{
        padding-top: 4.5rem;
        padding-bottom: 4rem;
        max-width: 1480px;
      }}

      h1, h2, h3, h4 {{
        color: {p.fg};
        letter-spacing: -0.01em;
      }}
      h1 {{ font-weight: 600; }}
      h2 {{ font-weight: 600; font-size: 1.45rem; }}
      h3 {{ font-weight: 500; font-size: 1.15rem; }}

      /* ============ Sidebar ============ */
      section[data-testid="stSidebar"] > div {{
        background: {p.bg_elev};
        border-right: 1px solid {p.border};
      }}
      section[data-testid="stSidebar"] h1 {{
        font-size: 1.15rem;
        font-weight: 700;
        color: {p.fg};
        margin-bottom: 0;
      }}
      section[data-testid="stSidebar"] .stCaption,
      section[data-testid="stSidebar"] [data-testid="stCaptionContainer"] {{
        color: {p.fg_dim};
      }}
      section[data-testid="stSidebar"] hr {{
        border-color: {p.border};
        opacity: 0.6;
      }}

      /* ============ Hero header (.qt-hero) ============ */
      .qt-hero {{
        display: flex;
        align-items: center;
        gap: 18px;
        margin-bottom: 16px;
        padding: 18px 22px;
        background: linear-gradient(135deg,
          {p.card} 0%, {p.bg_elev} 100%);
        border: 1px solid {p.border};
        border-radius: 14px;
        box-shadow: 0 1px 0 rgba(255,255,255,0.03) inset;
      }}
      .qt-hero-title {{
        font-size: 1.35rem;
        font-weight: 700;
        letter-spacing: -0.01em;
        color: {p.fg};
        margin: 0;
      }}
      .qt-hero-subtitle {{
        color: {p.fg_muted};
        font-size: 0.85rem;
        margin-top: 2px;
      }}
      .qt-hero-accent {{
        width: 4px;
        height: 38px;
        border-radius: 2px;
        background: linear-gradient(180deg, {p.accent} 0%, {p.accent_alt} 100%);
      }}

      /* ============ Status pills (LIVE / PAPER / etc.) ============ */
      .qt-pill {{
        display: inline-flex;
        align-items: center;
        gap: 6px;
        padding: 4px 10px;
        border-radius: 999px;
        font-size: 0.72rem;
        font-weight: 600;
        font-family: {FONT_MONO};
        text-transform: uppercase;
        letter-spacing: 0.06em;
        border: 1px solid;
      }}
      .qt-pill-dot {{
        width: 7px;
        height: 7px;
        border-radius: 50%;
        display: inline-block;
      }}
      .qt-pill-live    {{ color: {p.profit};  border-color: {p.profit}33;  background: rgba(34,197,94,0.10); }}
      .qt-pill-idle    {{ color: {p.fg_dim};  border-color: {p.border};    background: rgba(0,0,0,0.20); }}
      .qt-pill-warning {{ color: {p.warning}; border-color: {p.warning}33; background: rgba(245,158,11,0.10); }}
      .qt-pill-loss    {{ color: {p.loss};    border-color: {p.loss}33;    background: rgba(239,68,68,0.10); }}
      .qt-pill-info    {{ color: {p.info};    border-color: {p.info}33;    background: rgba(59,130,246,0.10); }}

      /* ============ KPI / metric cards ============ */
      div[data-testid="stMetric"] {{
        background: {p.card};
        border: 1px solid {p.border};
        border-radius: 12px;
        padding: 16px 18px;
        position: relative;
        overflow: hidden;
        transition: border-color 150ms ease, transform 150ms ease;
      }}
      div[data-testid="stMetric"]:hover {{
        border-color: {p.border_strong};
      }}
      div[data-testid="stMetric"]::before {{
        content: "";
        position: absolute;
        left: 0; top: 0; bottom: 0;
        width: 3px;
        background: linear-gradient(180deg, {p.accent} 0%, transparent 100%);
        opacity: 0.55;
      }}
      div[data-testid="stMetricValue"] {{
        font-family: {FONT_MONO};
        font-weight: 600;
        font-size: 1.55rem;
        color: {p.fg};
      }}
      div[data-testid="stMetricLabel"] {{
        color: {p.fg_muted};
        text-transform: uppercase;
        letter-spacing: 0.07em;
        font-size: 0.7rem;
        font-weight: 600;
      }}
      div[data-testid="stMetricDelta"] {{
        font-family: {FONT_MONO};
        font-size: 0.8rem;
      }}

      /* ============ Top-level tabs ============ */
      div[data-baseweb="tab-list"] {{
        gap: 2px;
        background: transparent;
        border-bottom: 1px solid {p.border};
        margin-bottom: 1.1rem;
        flex-wrap: wrap;
      }}
      button[data-baseweb="tab"] {{
        background: transparent;
        border-radius: 8px 8px 0 0;
        color: {p.fg_dim};
        border-bottom: 2px solid transparent;
        padding: 9px 16px;
        font-weight: 500;
        font-size: 0.92rem;
        transition: color 120ms, background 120ms, border-color 120ms;
      }}
      button[data-baseweb="tab"]:hover {{
        color: {p.fg};
        background: {p.card};
      }}
      button[data-baseweb="tab"][aria-selected="true"] {{
        color: {p.fg};
        background: {p.card};
        border-bottom: 2px solid {p.accent};
        font-weight: 600;
      }}

      /* ============ Sub-tabs (nested st.tabs) ============ */
      div[data-baseweb="tab-list"] button[data-baseweb="tab"][aria-selected="true"]::after {{
        display: none;
      }}

      /* ============ DataFrames ============ */
      div[data-testid="stDataFrame"] {{
        background: {p.card};
        border: 1px solid {p.border};
        border-radius: 10px;
        overflow: hidden;
      }}
      div[data-testid="stDataFrame"] [role="row"]:hover {{
        background: {p.card_hover} !important;
      }}

      /* ============ Buttons ============ */
      .stButton > button {{
        border-radius: 8px;
        border: 1px solid {p.border};
        background: {p.card};
        color: {p.fg};
        font-weight: 500;
        padding: 0.4rem 1rem;
        transition: background 120ms, border-color 120ms;
      }}
      .stButton > button:hover {{
        background: {p.card_hover};
        border-color: {p.border_strong};
      }}
      .stButton > button[kind="primary"] {{
        background: linear-gradient(135deg, {p.accent} 0%, #16A34A 100%);
        color: #052E0D;
        border-color: {p.accent};
      }}
      .stButton > button[kind="primary"]:hover {{
        filter: brightness(1.08);
      }}

      /* ============ Selectbox / inputs ============ */
      div[data-baseweb="select"] > div, .stTextInput input, .stNumberInput input {{
        background: {p.card} !important;
        border: 1px solid {p.border} !important;
        color: {p.fg} !important;
      }}
      div[data-baseweb="select"] > div:hover {{
        border-color: {p.border_strong} !important;
      }}

      /* ============ Info / Warning / Success / Error blocks ============ */
      div[data-testid="stAlert"] {{
        border-radius: 10px;
        border: 1px solid {p.border};
      }}

      /* ============ Code blocks ============ */
      code, pre, kbd, samp {{
        font-family: {FONT_MONO};
      }}
      div[data-testid="stCodeBlock"] {{
        border: 1px solid {p.border};
        border-radius: 8px;
      }}

      /* ============ Plotly chart background = container colour ============ */
      .stPlotlyChart {{
        background: {p.card};
        border: 1px solid {p.border};
        border-radius: 10px;
        padding: 4px;
      }}

      /* ============ Caption polish ============ */
      [data-testid="stCaptionContainer"] {{
        color: {p.fg_dim};
        font-size: 0.78rem;
      }}

      /* ============ Utility classes ============ */
      .qt-section-divider {{
        height: 1px;
        background: linear-gradient(90deg, transparent, {p.border} 50%, transparent);
        margin: 1.5rem 0 1rem 0;
      }}
      .pnl-positive {{ color: {p.profit}; font-family: {FONT_MONO}; font-weight: 600; }}
      .pnl-negative {{ color: {p.loss};   font-family: {FONT_MONO}; font-weight: 600; }}
      .pnl-neutral  {{ color: {p.fg_muted}; font-family: {FONT_MONO}; }}
    </style>
    """


# ---------------------------------------------------------------------------
# Reusable UI builders (return HTML strings — caller wraps in st.markdown)
# ---------------------------------------------------------------------------
def hero_header_html(
    title: str,
    subtitle: str,
    pills: Iterable[tuple[str, str]] = (),
) -> str:
    """Render the page hero with title + subtitle + a row of status pills.

    `pills` is a list of (label, variant) where variant ∈
    {live, idle, warning, loss, info}.
    """
    pill_html = "".join(
        f'<span class="qt-pill qt-pill-{variant}">'
        f'<span class="qt-pill-dot" style="background:currentColor"></span>'
        f'{label}</span>'
        for label, variant in pills
    )
    return f"""
    <div class="qt-hero">
      <div class="qt-hero-accent"></div>
      <div style="flex:1">
        <div class="qt-hero-title">{title}</div>
        <div class="qt-hero-subtitle">{subtitle}</div>
      </div>
      <div style="display:flex;gap:8px;flex-wrap:wrap;justify-content:flex-end">
        {pill_html}
      </div>
    </div>
    """


def status_pill_html(label: str, variant: str = "info") -> str:
    """A single status pill — can be used standalone in sidebar / banners."""
    return (
        f'<span class="qt-pill qt-pill-{variant}">'
        f'<span class="qt-pill-dot" style="background:currentColor"></span>'
        f'{label}</span>'
    )


def section_divider() -> str:
    return '<div class="qt-section-divider"></div>'


# ---------------------------------------------------------------------------
# Formatters
# ---------------------------------------------------------------------------
def fmt_eur(value: float, decimals: int = 0) -> str:
    sign = "-" if value < 0 else ""
    return f"{sign}€{abs(value):,.{decimals}f}".replace(",", " ").replace(" ", " ")


def fmt_pct(value: float, decimals: int = 2) -> str:
    return f"{value * 100:+.{decimals}f}%"


def color_pct(value: float) -> str:
    if value > 0:
        return PALETTE.profit
    if value < 0:
        return PALETTE.loss
    return PALETTE.fg_muted


def hex_to_rgba(hex_str: str, alpha: float = 0.13) -> str:
    """Convert '#RRGGBB' → 'rgba(R,G,B,alpha)'. Plotly doesn't accept #RRGGBBAA."""
    h = hex_str.lstrip("#")
    if len(h) == 8:  # accept incoming #RRGGBBAA by ignoring AA
        h = h[:6]
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f"rgba({r},{g},{b},{alpha:.2f})"
