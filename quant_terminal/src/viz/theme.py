"""Centralised design tokens — Quant Terminal v2 institutional palette.

Design language
---------------
Inspired by Bloomberg Terminal, Linear, and Vercel Dashboard. Dense data display
with strong typographic hierarchy, layered surfaces, semantic colour, monospaced
numerics. Every chart and KPI inherits from this module so the look stays
consistent across 15 tabs.

What this module exports
------------------------
* ``PALETTE``                 — the colour tokens (frozen dataclass).
* ``FONT_BODY`` / ``FONT_MONO`` — Inter + JetBrains Mono CSS stacks.
* ``PLOTLY_TEMPLATE``         — Plotly base layout shared by all viz.
* ``inject_streamlit_css()``  — global CSS to inject once at app start.
* HTML builders               — ``hero_header_html``, ``status_pill_html``,
  ``section_header_html``, ``kpi_tile_html``, ``stat_strip_html``,
  ``empty_state_html``, ``section_divider``.
* Formatters                  — ``fmt_eur``, ``fmt_pct``, ``color_pct``,
  ``hex_to_rgba``.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class Palette:
    # --- Surfaces (5-step elevation scale) ----------------------------------
    bg: str = "#06080F"               # page background — pure deep ink
    bg_elev: str = "#0A0E1A"          # one elevation up (hero / sidebar)
    card: str = "#0F1525"             # cards, panels
    card_hover: str = "#161D33"       # hover state on interactive cards
    muted_bg: str = "#1A2237"         # subtle highlighted region (e.g. callout)
    border: str = "#1F2B45"           # default border / divider
    border_strong: str = "#3A4A6B"    # focus rings, active selections

    # --- Text (4-step hierarchy) --------------------------------------------
    fg: str = "#F1F5F9"               # primary text (titles)
    fg_muted: str = "#A0AEC4"         # secondary text (labels, metadata)
    fg_dim: str = "#6B7A99"           # tertiary text (captions, hints)
    fg_disabled: str = "#475569"      # disabled state

    # --- Brand & accents ----------------------------------------------------
    primary: str = "#0F172A"          # legacy compat
    secondary: str = "#1E293B"        # legacy compat
    accent: str = "#10B981"           # mint — main brand accent (P&L positive)
    accent_alt: str = "#22D3EE"       # cyan — secondary accent (info chips)
    accent_violet: str = "#8B5CF6"    # tertiary accent (highlights, premium)
    ring: str = "#10B98155"           # focus ring with transparency

    # --- Semantic (consistent across the app) -------------------------------
    profit: str = "#10B981"           # mint — positive P&L
    loss: str = "#F43F5E"             # rose — negative P&L (warmer than red)
    warning: str = "#F59E0B"          # amber — caution
    info: str = "#3B82F6"             # blue — info / neutral signal
    neutral: str = "#94A3B8"          # cool gray — neutral data

    # --- Trading candles (TradingView convention) ---------------------------
    bull_body: str = "#26A69A"
    bear_body: str = "#EF5350"
    volume_up: str = "rgba(38, 166, 154, 0.4)"
    volume_down: str = "rgba(239, 83, 80, 0.4)"


PALETTE = Palette()

FONT_BODY = "Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, sans-serif"
FONT_MONO = "'JetBrains Mono', ui-monospace, 'SF Mono', SFMono-Regular, 'Cascadia Code', monospace"
FONT_DISPLAY = "Inter, ui-sans-serif, system-ui, sans-serif"

# ---------------------------------------------------------------------------
# Plotly base template — applied via update_layout(template=PLOTLY_TEMPLATE)
# ---------------------------------------------------------------------------
PLOTLY_TEMPLATE = {
    "layout": {
        "paper_bgcolor": PALETTE.bg,
        "plot_bgcolor": PALETTE.bg,
        "font": {"color": PALETTE.fg, "family": FONT_BODY, "size": 12},
        "colorway": [
            PALETTE.accent, PALETTE.accent_alt, PALETTE.accent_violet,
            PALETTE.warning, PALETTE.info, "#EC4899", "#F97316", PALETTE.bull_body,
        ],
        "xaxis": {
            "gridcolor": PALETTE.border,
            "zerolinecolor": PALETTE.border,
            "color": PALETTE.fg_muted,
            "linecolor": PALETTE.border_strong,
            "tickfont": {"family": FONT_MONO, "size": 11, "color": PALETTE.fg_muted},
        },
        "yaxis": {
            "gridcolor": PALETTE.border,
            "zerolinecolor": PALETTE.border,
            "color": PALETTE.fg_muted,
            "linecolor": PALETTE.border_strong,
            "tickfont": {"family": FONT_MONO, "size": 11, "color": PALETTE.fg_muted},
        },
        "legend": {
            "bgcolor": "rgba(0,0,0,0)",
            "font": {"color": PALETTE.fg, "family": FONT_BODY, "size": 12},
            "orientation": "h",
            "y": -0.18,
        },
        "margin": {"l": 48, "r": 16, "t": 40, "b": 40},
        "hoverlabel": {
            "bgcolor": PALETTE.card,
            "bordercolor": PALETTE.border_strong,
            "font": {"family": FONT_MONO, "size": 12, "color": PALETTE.fg},
        },
    }
}


# ---------------------------------------------------------------------------
# CSS — comprehensive Streamlit dark + components
# ---------------------------------------------------------------------------
def inject_streamlit_css() -> str:
    """Return a single CSS block to be dropped into ``st.markdown(..., unsafe_allow_html=True)``."""
    p = PALETTE
    return f"""
    <style>
      /* === Fonts ============================================================ */
      @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;500;600;700&display=swap');

      :root {{
        --qt-bg: {p.bg};
        --qt-bg-elev: {p.bg_elev};
        --qt-card: {p.card};
        --qt-card-hover: {p.card_hover};
        --qt-border: {p.border};
        --qt-border-strong: {p.border_strong};
        --qt-fg: {p.fg};
        --qt-fg-muted: {p.fg_muted};
        --qt-fg-dim: {p.fg_dim};
        --qt-accent: {p.accent};
        --qt-accent-alt: {p.accent_alt};
        --qt-profit: {p.profit};
        --qt-loss: {p.loss};
        --qt-warning: {p.warning};
        --qt-info: {p.info};
        --qt-font-body: {FONT_BODY};
        --qt-font-mono: {FONT_MONO};
      }}

      html, body, [class*="st-"] {{
        font-family: {FONT_BODY};
        font-feature-settings: 'cv11', 'ss01', 'ss03';
      }}

      .stApp {{
        background:
          radial-gradient(1200px 600px at 100% -10%, {p.accent}08 0%, transparent 55%),
          radial-gradient(1000px 500px at -10% 110%, {p.accent_alt}08 0%, transparent 60%),
          linear-gradient(180deg, {p.bg_elev} 0%, {p.bg} 100%);
        color: {p.fg};
        background-attachment: fixed;
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
        max-width: 1520px;
      }}

      /* === Typography ====================================================== */
      h1, h2, h3, h4, h5, h6 {{
        color: {p.fg};
        letter-spacing: -0.02em;
        font-feature-settings: 'cv11', 'ss01';
      }}
      h1 {{ font-weight: 700; font-size: 1.8rem; line-height: 1.2; }}
      h2 {{ font-weight: 600; font-size: 1.35rem; line-height: 1.3; }}
      h3 {{ font-weight: 600; font-size: 1.1rem; line-height: 1.35; }}
      h4 {{ font-weight: 600; font-size: 0.95rem; line-height: 1.4; }}
      h5, h6 {{ font-weight: 500; }}

      /* === Sidebar ========================================================= */
      section[data-testid="stSidebar"] > div {{
        background: linear-gradient(180deg, {p.bg_elev} 0%, {p.bg} 100%);
        border-right: 1px solid {p.border};
      }}
      section[data-testid="stSidebar"] h1 {{
        font-size: 1.05rem;
        font-weight: 700;
        color: {p.fg};
        margin-bottom: 0;
        letter-spacing: -0.01em;
      }}
      section[data-testid="stSidebar"] [data-testid="stCaptionContainer"] {{
        color: {p.fg_dim};
        font-size: 0.74rem;
      }}
      section[data-testid="stSidebar"] hr {{
        border-color: {p.border};
        opacity: 0.5;
        margin: 0.9rem 0;
      }}
      section[data-testid="stSidebar"] .stSubheader,
      section[data-testid="stSidebar"] h3 {{
        font-size: 0.7rem;
        font-weight: 700;
        color: {p.fg_dim};
        text-transform: uppercase;
        letter-spacing: 0.12em;
        margin-bottom: 0.6rem;
        margin-top: 0.4rem;
      }}

      /* === Hero header (.qt-hero) ========================================== */
      .qt-hero {{
        position: relative;
        display: flex;
        align-items: center;
        gap: 20px;
        margin-bottom: 22px;
        padding: 22px 26px;
        background:
          linear-gradient(135deg, {p.card} 0%, {p.bg_elev} 100%),
          radial-gradient(800px 200px at 0% 0%, {p.accent}15 0%, transparent 60%);
        background-blend-mode: normal;
        border: 1px solid {p.border};
        border-radius: 16px;
        box-shadow:
          0 1px 0 rgba(255,255,255,0.04) inset,
          0 24px 60px -30px {p.accent}25;
        overflow: hidden;
      }}
      .qt-hero::before {{
        content: "";
        position: absolute;
        inset: 0;
        background:
          radial-gradient(600px 160px at 100% 100%, {p.accent_alt}10 0%, transparent 70%);
        pointer-events: none;
      }}
      .qt-hero-title {{
        font-size: 1.65rem;
        font-weight: 700;
        letter-spacing: -0.02em;
        color: {p.fg};
        margin: 0;
        background: linear-gradient(90deg, {p.fg} 0%, {p.fg_muted} 130%);
        -webkit-background-clip: text;
        background-clip: text;
        -webkit-text-fill-color: transparent;
      }}
      .qt-hero-subtitle {{
        color: {p.fg_muted};
        font-size: 0.85rem;
        margin-top: 4px;
        font-weight: 400;
      }}
      .qt-hero-accent {{
        width: 4px;
        height: 46px;
        border-radius: 3px;
        background: linear-gradient(180deg, {p.accent} 0%, {p.accent_alt} 50%, {p.accent_violet} 100%);
        box-shadow: 0 0 14px {p.accent}50;
      }}

      /* === Status pills (LIVE / PAPER / etc.) ============================== */
      .qt-pill {{
        display: inline-flex;
        align-items: center;
        gap: 6px;
        padding: 4px 11px;
        border-radius: 999px;
        font-size: 0.7rem;
        font-weight: 600;
        font-family: {FONT_MONO};
        text-transform: uppercase;
        letter-spacing: 0.08em;
        border: 1px solid;
        backdrop-filter: blur(6px);
      }}
      .qt-pill-dot {{
        width: 6px;
        height: 6px;
        border-radius: 50%;
        display: inline-block;
        box-shadow: 0 0 6px currentColor;
      }}
      .qt-pill-live    {{ color: {p.profit};  border-color: {p.profit}44;  background: rgba(16,185,129,0.10); }}
      .qt-pill-idle    {{ color: {p.fg_dim};  border-color: {p.border_strong};  background: rgba(0,0,0,0.20); }}
      .qt-pill-warning {{ color: {p.warning}; border-color: {p.warning}44; background: rgba(245,158,11,0.10); }}
      .qt-pill-loss    {{ color: {p.loss};    border-color: {p.loss}44;    background: rgba(244,63,94,0.10); }}
      .qt-pill-info    {{ color: {p.info};    border-color: {p.info}44;    background: rgba(59,130,246,0.10); }}

      /* === Section header (qt-section) ===================================== */
      .qt-section {{
        display: flex;
        align-items: flex-end;
        gap: 12px;
        margin: 1.6rem 0 1rem 0;
        padding-bottom: 0.55rem;
        border-bottom: 1px solid {p.border};
      }}
      .qt-section-icon {{
        font-size: 1.2rem;
        line-height: 1;
        flex-shrink: 0;
        opacity: 0.85;
      }}
      .qt-section-title {{
        font-size: 1rem;
        font-weight: 600;
        color: {p.fg};
        letter-spacing: -0.01em;
        margin: 0;
      }}
      .qt-section-subtitle {{
        font-size: 0.78rem;
        color: {p.fg_dim};
        font-weight: 400;
        margin-top: 1px;
      }}
      .qt-section-meta {{
        margin-left: auto;
        font-family: {FONT_MONO};
        font-size: 0.72rem;
        color: {p.fg_dim};
      }}

      /* === KPI tile (custom card, denser than st.metric) =================== */
      .qt-tile {{
        background: linear-gradient(180deg, {p.card} 0%, {p.bg_elev} 100%);
        border: 1px solid {p.border};
        border-radius: 12px;
        padding: 14px 16px;
        position: relative;
        overflow: hidden;
        transition: border-color 150ms ease, transform 150ms ease;
      }}
      .qt-tile:hover {{ border-color: {p.border_strong}; }}
      .qt-tile-accent-mint   {{ box-shadow: inset 0 0 0 1px {p.accent}25, 0 0 24px -16px {p.accent}; }}
      .qt-tile-accent-cyan   {{ box-shadow: inset 0 0 0 1px {p.accent_alt}25, 0 0 24px -16px {p.accent_alt}; }}
      .qt-tile-accent-amber  {{ box-shadow: inset 0 0 0 1px {p.warning}25, 0 0 24px -16px {p.warning}; }}
      .qt-tile-accent-rose   {{ box-shadow: inset 0 0 0 1px {p.loss}25, 0 0 24px -16px {p.loss}; }}
      .qt-tile-label {{
        color: {p.fg_muted};
        text-transform: uppercase;
        letter-spacing: 0.08em;
        font-size: 0.68rem;
        font-weight: 600;
        line-height: 1;
        margin-bottom: 8px;
      }}
      .qt-tile-value {{
        font-family: {FONT_MONO};
        font-weight: 600;
        font-size: 1.55rem;
        color: {p.fg};
        line-height: 1.1;
        letter-spacing: -0.01em;
      }}
      .qt-tile-delta {{
        margin-top: 6px;
        font-family: {FONT_MONO};
        font-size: 0.78rem;
        font-weight: 500;
      }}
      .qt-tile-delta-pos {{ color: {p.profit}; }}
      .qt-tile-delta-neg {{ color: {p.loss}; }}
      .qt-tile-delta-neutral {{ color: {p.fg_muted}; }}
      .qt-tile-hint {{
        margin-top: 4px;
        font-size: 0.7rem;
        color: {p.fg_dim};
      }}

      /* === Native st.metric also gets the upgrade ========================== */
      div[data-testid="stMetric"] {{
        background: linear-gradient(180deg, {p.card} 0%, {p.bg_elev} 100%);
        border: 1px solid {p.border};
        border-radius: 12px;
        padding: 16px 18px;
        position: relative;
        overflow: hidden;
        transition: border-color 150ms ease;
      }}
      div[data-testid="stMetric"]:hover {{ border-color: {p.border_strong}; }}
      div[data-testid="stMetric"]::before {{
        content: "";
        position: absolute;
        left: 0; top: 0; bottom: 0;
        width: 3px;
        background: linear-gradient(180deg, {p.accent} 0%, {p.accent_alt} 100%);
        opacity: 0.7;
      }}
      div[data-testid="stMetricValue"] {{
        font-family: {FONT_MONO};
        font-weight: 600;
        font-size: 1.55rem;
        color: {p.fg};
        letter-spacing: -0.01em;
      }}
      div[data-testid="stMetricLabel"] {{
        color: {p.fg_muted};
        text-transform: uppercase;
        letter-spacing: 0.08em;
        font-size: 0.68rem;
        font-weight: 600;
      }}
      div[data-testid="stMetricDelta"] {{
        font-family: {FONT_MONO};
        font-size: 0.8rem;
        font-weight: 500;
      }}

      /* === Top-level tabs ================================================== */
      div[data-baseweb="tab-list"] {{
        gap: 2px;
        background: transparent;
        border-bottom: 1px solid {p.border};
        margin-bottom: 1.1rem;
        flex-wrap: wrap;
        padding-bottom: 0;
      }}
      button[data-baseweb="tab"] {{
        background: transparent;
        border-radius: 10px 10px 0 0;
        color: {p.fg_dim};
        border-bottom: 2px solid transparent;
        padding: 10px 16px;
        font-weight: 500;
        font-size: 0.9rem;
        transition: color 120ms, background 120ms, border-color 120ms;
        letter-spacing: -0.005em;
      }}
      button[data-baseweb="tab"]:hover {{
        color: {p.fg};
        background: {p.card};
      }}
      button[data-baseweb="tab"][aria-selected="true"] {{
        color: {p.fg};
        background: linear-gradient(180deg, {p.card} 0%, {p.bg_elev} 100%);
        border-bottom: 2px solid {p.accent};
        font-weight: 600;
        box-shadow: 0 -1px 0 {p.border} inset;
      }}

      /* === DataFrames ====================================================== */
      div[data-testid="stDataFrame"] {{
        background: {p.card};
        border: 1px solid {p.border};
        border-radius: 12px;
        overflow: hidden;
      }}
      div[data-testid="stDataFrame"] [role="row"]:hover {{
        background: {p.card_hover} !important;
      }}
      div[data-testid="stDataFrame"] [role="columnheader"] {{
        background: {p.bg_elev} !important;
        font-weight: 600 !important;
        font-size: 0.72rem !important;
        text-transform: uppercase !important;
        letter-spacing: 0.06em !important;
        color: {p.fg_muted} !important;
      }}

      /* === Buttons ========================================================= */
      .stButton > button {{
        border-radius: 8px;
        border: 1px solid {p.border};
        background: {p.card};
        color: {p.fg};
        font-weight: 500;
        padding: 0.45rem 1.05rem;
        font-size: 0.88rem;
        transition: background 120ms, border-color 120ms, transform 80ms;
      }}
      .stButton > button:hover {{
        background: {p.card_hover};
        border-color: {p.border_strong};
      }}
      .stButton > button:active {{ transform: translateY(1px); }}
      .stButton > button[kind="primary"] {{
        background: linear-gradient(135deg, {p.accent} 0%, #059669 100%);
        color: #042F1A;
        border-color: {p.accent};
        font-weight: 600;
        box-shadow: 0 4px 14px -4px {p.accent}66;
      }}
      .stButton > button[kind="primary"]:hover {{
        filter: brightness(1.08);
        box-shadow: 0 6px 18px -4px {p.accent}88;
      }}

      /* === Selectbox / inputs ============================================== */
      div[data-baseweb="select"] > div, .stTextInput input, .stNumberInput input,
      .stTextArea textarea {{
        background: {p.card} !important;
        border: 1px solid {p.border} !important;
        color: {p.fg} !important;
        font-family: {FONT_BODY};
        font-size: 0.88rem;
      }}
      div[data-baseweb="select"] > div:hover {{
        border-color: {p.border_strong} !important;
      }}
      div[data-baseweb="select"] > div:focus-within {{
        border-color: {p.accent} !important;
        box-shadow: 0 0 0 3px {p.accent}25 !important;
      }}

      /* === Sliders ========================================================= */
      .stSlider [role="slider"] {{
        background: {p.accent} !important;
        border: 2px solid {p.fg} !important;
        box-shadow: 0 0 8px {p.accent}66 !important;
      }}

      /* === Alerts ========================================================== */
      div[data-testid="stAlert"] {{
        border-radius: 10px;
        border: 1px solid {p.border};
        backdrop-filter: blur(6px);
      }}

      /* === Code blocks ===================================================== */
      code, pre, kbd, samp {{
        font-family: {FONT_MONO};
        font-size: 0.84em;
      }}
      div[data-testid="stCodeBlock"] {{
        border: 1px solid {p.border};
        border-radius: 8px;
      }}

      /* === Plotly chart container =========================================== */
      .stPlotlyChart {{
        background: {p.card};
        border: 1px solid {p.border};
        border-radius: 12px;
        padding: 8px;
      }}

      /* === Caption polish ================================================== */
      [data-testid="stCaptionContainer"] {{
        color: {p.fg_dim};
        font-size: 0.78rem;
        line-height: 1.45;
      }}

      /* === Empty state ===================================================== */
      .qt-empty {{
        text-align: center;
        padding: 36px 20px;
        background: {p.card};
        border: 1px dashed {p.border_strong};
        border-radius: 12px;
        color: {p.fg_muted};
      }}
      .qt-empty-icon {{
        font-size: 2rem;
        opacity: 0.5;
        margin-bottom: 10px;
      }}
      .qt-empty-title {{
        font-weight: 600;
        font-size: 1rem;
        color: {p.fg};
        margin-bottom: 4px;
      }}
      .qt-empty-text {{
        font-size: 0.82rem;
        color: {p.fg_dim};
      }}

      /* === Utility classes ================================================= */
      .qt-section-divider {{
        height: 1px;
        background: linear-gradient(90deg, transparent, {p.border} 50%, transparent);
        margin: 1.5rem 0 1rem 0;
      }}
      .pnl-positive {{ color: {p.profit}; font-family: {FONT_MONO}; font-weight: 600; }}
      .pnl-negative {{ color: {p.loss};   font-family: {FONT_MONO}; font-weight: 600; }}
      .pnl-neutral  {{ color: {p.fg_muted}; font-family: {FONT_MONO}; }}

      /* === Scrollbars (subtle) ============================================= */
      ::-webkit-scrollbar {{ width: 10px; height: 10px; }}
      ::-webkit-scrollbar-track {{ background: {p.bg}; }}
      ::-webkit-scrollbar-thumb {{
        background: {p.border_strong};
        border-radius: 5px;
        border: 2px solid {p.bg};
      }}
      ::-webkit-scrollbar-thumb:hover {{ background: {p.fg_dim}; }}
    </style>
    """


# ---------------------------------------------------------------------------
# Reusable HTML builders — return strings, caller wraps in st.markdown(..., unsafe_allow_html=True)
# ---------------------------------------------------------------------------
def hero_header_html(
    title: str,
    subtitle: str,
    pills: Iterable[tuple[str, str]] = (),
) -> str:
    """Page hero: title + subtitle + optional row of status pills."""
    pill_html = "".join(
        f'<span class="qt-pill qt-pill-{variant}">'
        f'<span class="qt-pill-dot" style="background:currentColor"></span>'
        f"{label}</span>"
        for label, variant in pills
    )
    return f"""
    <div class="qt-hero">
      <div class="qt-hero-accent"></div>
      <div style="flex:1;min-width:0">
        <div class="qt-hero-title">{title}</div>
        <div class="qt-hero-subtitle">{subtitle}</div>
      </div>
      <div style="display:flex;gap:8px;flex-wrap:wrap;justify-content:flex-end">
        {pill_html}
      </div>
    </div>
    """


def status_pill_html(label: str, variant: str = "info") -> str:
    """A single status pill — use in sidebar / banners."""
    return (
        f'<span class="qt-pill qt-pill-{variant}">'
        f'<span class="qt-pill-dot" style="background:currentColor"></span>'
        f"{label}</span>"
    )


def section_header_html(
    title: str, *, icon: str = "", subtitle: str = "", meta: str = "",
) -> str:
    """Section heading with icon, title, optional subtitle, and right-aligned meta."""
    icon_html = f'<div class="qt-section-icon">{icon}</div>' if icon else ""
    sub_html = f'<div class="qt-section-subtitle">{subtitle}</div>' if subtitle else ""
    meta_html = f'<div class="qt-section-meta">{meta}</div>' if meta else ""
    return f"""
    <div class="qt-section">
      {icon_html}
      <div style="flex:1;min-width:0">
        <div class="qt-section-title">{title}</div>
        {sub_html}
      </div>
      {meta_html}
    </div>
    """


def kpi_tile_html(
    label: str,
    value: str,
    *,
    delta: str = "",
    delta_dir: str = "neutral",
    hint: str = "",
    accent: str = "",
) -> str:
    """Compact KPI tile — denser than st.metric, more visual.

    ``delta_dir`` ∈ {pos, neg, neutral}.
    ``accent``    ∈ {"", mint, cyan, amber, rose}.
    """
    accent_cls = f" qt-tile-accent-{accent}" if accent else ""
    delta_html = (
        f'<div class="qt-tile-delta qt-tile-delta-{delta_dir}">{delta}</div>'
        if delta else ""
    )
    hint_html = f'<div class="qt-tile-hint">{hint}</div>' if hint else ""
    return f"""
    <div class="qt-tile{accent_cls}">
      <div class="qt-tile-label">{label}</div>
      <div class="qt-tile-value">{value}</div>
      {delta_html}
      {hint_html}
    </div>
    """


def stat_strip_html(items: list[dict]) -> str:
    """Horizontal strip of KPI tiles. Each item: ``{label, value, delta?, delta_dir?, accent?, hint?}``."""
    cards = "".join(
        kpi_tile_html(
            label=it.get("label", ""),
            value=it.get("value", ""),
            delta=it.get("delta", ""),
            delta_dir=it.get("delta_dir", "neutral"),
            hint=it.get("hint", ""),
            accent=it.get("accent", ""),
        )
        for it in items
    )
    cols = max(1, len(items))
    return f"""
    <div style="display:grid;grid-template-columns:repeat({cols}, minmax(0,1fr));
                gap:12px;margin-bottom:12px;">
      {cards}
    </div>
    """


def empty_state_html(
    title: str = "No data",
    text: str = "",
    icon: str = "📭",
) -> str:
    """Decorated empty-state placeholder."""
    text_html = f'<div class="qt-empty-text">{text}</div>' if text else ""
    return f"""
    <div class="qt-empty">
      <div class="qt-empty-icon">{icon}</div>
      <div class="qt-empty-title">{title}</div>
      {text_html}
    </div>
    """


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
