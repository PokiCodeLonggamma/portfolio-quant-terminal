"""Quant Terminal — Design v3 "Wall Street Brutalist" design tokens.

Design language
---------------
Direction BOLD éditoriale-mono. Fraunces (variable serif) en display, JetBrains
Mono partout ailleurs (UI, numerics, body) — pour le vrai feel terminal
Bloomberg/Reuters. Palette : deep ink + bone white + mercury red + caution
amber + sharp mint + gold rule lines. Hard right angles (border-radius: 0).
SVG fractal noise 5% + radial corner gradient gold 8% = atmosphère
papier-imprimé du Wall Street Journal. § numbering éditorial.

Banned (par la doctrine frontend-design)
----------------------------------------
- Inter, Roboto, Arial, Helvetica, system-ui
- Border-radius > 4px sur les cards
- Mint+cyan combo du theme v2
- Drop shadows, glassmorphism, gradients dégradés
- Surface flat sans atmosphere

Exports preserved (back-compat)
-------------------------------
PALETTE, PLOTLY_TEMPLATE, FONT_BODY, FONT_MONO, FONT_DISPLAY,
inject_streamlit_css, hero_header_html, status_pill_html,
section_header_html, kpi_tile_html, stat_strip_html, empty_state_html,
section_divider, fmt_eur, fmt_pct, color_pct, hex_to_rgba.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


# ============================================================================
# 1. PALETTE — Wall Street Brutalist
# ============================================================================
@dataclass(frozen=True)
class Palette:
    # --- Surfaces (5-step elevation, warmer ink) ----------------------------
    bg: str = "#0A0A0F"               # deep oil ink (page background)
    bg_elev: str = "#14141C"          # one elevation up (sidebar, hero)
    card: str = "#1A1A24"             # cards, panels
    card_hover: str = "#242430"       # hover state
    muted_bg: str = "#1F1F2A"         # subtle highlighted region
    border: str = "#2A2A38"           # default border / divider
    border_strong: str = "#4A4A60"    # active selections, focus rings
    rule: str = "#D4AF37"             # gold rule lines (editorial dividers)

    # --- Text (bone white system, 4-step) -----------------------------------
    fg: str = "#FAF7F2"               # bone — print paper feel
    fg_muted: str = "#B8B5AC"         # secondary (labels, captions)
    fg_dim: str = "#6B6960"           # tertiary (hints, footnotes)
    fg_disabled: str = "#3F3D38"      # disabled

    # --- Brand & accents (sharp, single-purpose) ----------------------------
    primary: str = "#0A0A0F"          # legacy compat (= bg)
    secondary: str = "#14141C"        # legacy compat (= bg_elev)
    accent: str = "#2EE89E"           # sharp mint — main accent (P&L positive)
    accent_pos: str = "#2EE89E"       # explicit positive
    accent_neg: str = "#FF3838"       # mercury red — losses, warnings
    accent_warn: str = "#FFB800"      # caution amber — used SPARINGLY
    accent_alt: str = "#22D3EE"       # cyan — info chips (back-compat)
    accent_violet: str = "#8B5CF6"    # premium highlights
    accent_serif: str = "#D4AF37"     # gold — rules, § numbers, decorative
    ring: str = "#2EE89E55"           # focus ring (mint with transparency)

    # --- Semantic (consistent across the app — backward compat) -------------
    profit: str = "#2EE89E"           # positive P&L (= accent_pos)
    loss: str = "#FF3838"             # negative P&L (= accent_neg)
    warning: str = "#FFB800"          # caution (= accent_warn)
    info: str = "#22D3EE"             # info / neutral signal
    neutral: str = "#B8B5AC"          # neutral data (= fg_muted)

    # --- Trading candles (TradingView convention) ---------------------------
    bull_body: str = "#2EE89E"
    bear_body: str = "#FF3838"
    volume_up: str = "rgba(46, 232, 158, 0.4)"
    volume_down: str = "rgba(255, 56, 56, 0.4)"

    # --- Plotly v3 colorway (sharp, distinct hues) --------------------------
    plotly_colorway_v3: tuple = (
        "#FAF7F2",  # bone
        "#FF3838",  # mercury
        "#FFB800",  # amber
        "#2EE89E",  # mint
        "#22D3EE",  # cyan
        "#D4AF37",  # gold
        "#8B5CF6",  # violet
    )


PALETTE = Palette()


# ============================================================================
# 2. TYPOGRAPHY — Fraunces (display) + JetBrains Mono (body/UI/numerics)
# ============================================================================
FONT_DISPLAY = '"Fraunces", "Newsreader", Georgia, serif'
FONT_BODY = '"JetBrains Mono", "IBM Plex Mono", ui-monospace, Menlo, monospace'
FONT_MONO = '"JetBrains Mono", "IBM Plex Mono", ui-monospace, Menlo, monospace'

GOOGLE_FONTS_URL = (
    "https://fonts.googleapis.com/css2"
    "?family=Fraunces:opsz,wght@9..144,300;9..144,400;9..144,700;9..144,900"
    "&family=JetBrains+Mono:wght@300;400;500;700&display=swap"
)


# ============================================================================
# 3. PLOTLY TEMPLATE — overridden at end of file by plotly_template_v3 import
# ============================================================================
PLOTLY_TEMPLATE: dict = {
    "layout": {
        "paper_bgcolor": PALETTE.bg,
        "plot_bgcolor": PALETTE.bg,
        "font": {"color": PALETTE.fg, "family": FONT_MONO, "size": 12},
        "colorway": list(PALETTE.plotly_colorway_v3),
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
            "font": {"color": PALETTE.fg, "family": FONT_MONO, "size": 12},
            "orientation": "h",
            "y": -0.18,
        },
        "margin": {"l": 48, "r": 16, "t": 40, "b": 40},
        "hoverlabel": {
            "bgcolor": PALETTE.card,
            "bordercolor": PALETTE.rule,
            "font": {"family": FONT_MONO, "size": 12, "color": PALETTE.fg},
        },
    }
}


# ============================================================================
# 4. CSS INJECTION — single block to drop into st.markdown(unsafe_allow_html)
# ============================================================================
def inject_streamlit_css() -> str:
    """Return a single CSS block — caller wraps in ``st.markdown``."""
    p = PALETTE
    return f"""
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="{GOOGLE_FONTS_URL}" rel="stylesheet">

<style>
  /* === CSS variables ============================================== */
  :root {{
    --qt-bg: {p.bg};
    --qt-bg-elev: {p.bg_elev};
    --qt-card: {p.card};
    --qt-card-hover: {p.card_hover};
    --qt-muted-bg: {p.muted_bg};
    --qt-border: {p.border};
    --qt-border-strong: {p.border_strong};
    --qt-rule: {p.rule};
    --qt-fg: {p.fg};
    --qt-fg-muted: {p.fg_muted};
    --qt-fg-dim: {p.fg_dim};
    --qt-accent-pos: {p.accent_pos};
    --qt-accent-neg: {p.accent_neg};
    --qt-accent-warn: {p.accent_warn};
    --qt-accent: {p.accent};
    --qt-accent-alt: {p.accent_alt};
    --qt-accent-serif: {p.accent_serif};
    --qt-font-display: {FONT_DISPLAY};
    --qt-font-body: {FONT_BODY};
    --qt-font-mono: {FONT_MONO};
  }}

  /* === Page atmosphere: deep ink + SVG noise + corner gold mesh === */
  .stApp, [data-testid="stAppViewContainer"] {{
    background-color: var(--qt-bg) !important;
    background-image:
      radial-gradient(circle at 100% 0%, rgba(212,175,55,0.08) 0%, transparent 600px),
      radial-gradient(circle at 0% 100%, rgba(46,232,158,0.04) 0%, transparent 500px),
      url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='200' height='200'><filter id='n'><feTurbulence type='fractalNoise' baseFrequency='0.85' numOctaves='2' stitchTiles='stitch'/></filter><rect width='100%25' height='100%25' filter='url(%23n)' opacity='0.05'/></svg>");
    background-attachment: fixed;
    color: var(--qt-fg);
    font-family: var(--qt-font-body);
    font-variant-numeric: tabular-nums;
    letter-spacing: 0;
  }}

  html, body, [class*="st-"] {{
    font-family: var(--qt-font-body);
    color: var(--qt-fg);
  }}

  /* === Display (serif editorial) — h1/h2/h3 ======================== */
  h1, h2, h3, .qt-display {{
    font-family: var(--qt-font-display) !important;
    font-weight: 700;
    letter-spacing: -0.02em;
    color: var(--qt-fg);
  }}
  h1 {{ font-size: 2.6rem; font-variation-settings: "opsz" 96; line-height: 1.05; }}
  h2 {{ font-size: 1.85rem; font-variation-settings: "opsz" 32; }}
  h3 {{ font-size: 1.25rem; font-variation-settings: "opsz" 14; }}

  /* Headings inside Streamlit blocks */
  [data-testid="stMarkdownContainer"] h1,
  [data-testid="stMarkdownContainer"] h2,
  [data-testid="stMarkdownContainer"] h3 {{
    font-family: var(--qt-font-display) !important;
  }}

  /* === Sidebar ===================================================== */
  [data-testid="stSidebar"] {{
    background-color: var(--qt-bg-elev) !important;
    border-right: 1px solid var(--qt-border);
  }}
  [data-testid="stSidebar"] .stMarkdown, [data-testid="stSidebar"] label {{
    font-family: var(--qt-font-mono);
    color: var(--qt-fg-muted);
  }}

  /* === Tabs (uppercase, letter-spaced, gold underline on active) === */
  .stTabs [data-baseweb="tab-list"] {{
    gap: 0;
    border-bottom: 1px solid var(--qt-border);
    background: transparent;
  }}
  .stTabs [data-baseweb="tab"] {{
    border-radius: 0 !important;
    background-color: transparent !important;
    font-family: var(--qt-font-mono) !important;
    font-size: 0.78rem !important;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    border-bottom: 2px solid transparent;
    padding: 12px 14px !important;
    color: var(--qt-fg-muted) !important;
  }}
  .stTabs [aria-selected="true"] {{
    border-bottom-color: var(--qt-rule) !important;
    color: var(--qt-fg) !important;
  }}

  /* === Hero block (editorial) ====================================== */
  .qt-hero {{
    display: flex;
    align-items: baseline;
    gap: 20px;
    padding: 28px 0 20px 0;
    border-bottom: 1px solid var(--qt-rule);
    margin-bottom: 24px;
  }}
  .qt-hero-number {{
    font-family: var(--qt-font-display);
    font-variation-settings: "opsz" 144;
    font-weight: 900;
    font-size: 4rem;
    color: var(--qt-rule);
    line-height: 0.85;
    opacity: 0.95;
    flex-shrink: 0;
  }}
  .qt-hero-accent {{
    width: 3px;
    align-self: stretch;
    background: var(--qt-rule);
    flex-shrink: 0;
  }}
  .qt-hero-body {{ flex: 1; min-width: 0; }}
  .qt-hero-title {{
    font-family: var(--qt-font-display);
    font-weight: 700;
    font-size: 2.5rem;
    line-height: 1.05;
    color: var(--qt-fg);
    letter-spacing: -0.02em;
  }}
  .qt-hero-subtitle {{
    font-family: var(--qt-font-mono);
    font-size: 0.9rem;
    color: var(--qt-fg-muted);
    margin-top: 6px;
    line-height: 1.5;
  }}
  .qt-hero-meta {{
    font-family: var(--qt-font-mono);
    font-size: 0.75rem;
    color: var(--qt-fg-dim);
    text-transform: uppercase;
    letter-spacing: 0.08em;
  }}

  /* === Section header ============================================== */
  .qt-section {{
    display: flex;
    align-items: baseline;
    gap: 14px;
    padding: 18px 0 14px 0;
    border-bottom: 1px solid var(--qt-rule);
    margin-bottom: 18px;
  }}
  .qt-section-header {{
    display: flex;
    align-items: baseline;
    gap: 14px;
    padding: 18px 0 14px 0;
    border-bottom: 1px solid var(--qt-rule);
    margin-bottom: 18px;
  }}
  .qt-section-icon {{
    font-size: 1.6rem;
    flex-shrink: 0;
  }}
  .qt-section-title {{
    font-family: var(--qt-font-display);
    font-weight: 700;
    font-size: 1.75rem;
    color: var(--qt-fg);
    letter-spacing: -0.01em;
    line-height: 1.1;
  }}
  .qt-section-subtitle {{
    font-family: var(--qt-font-mono);
    font-size: 0.85rem;
    color: var(--qt-fg-muted);
    margin-top: 4px;
    line-height: 1.5;
  }}
  .qt-section-meta {{
    margin-left: auto;
    font-family: var(--qt-font-mono);
    font-size: 0.75rem;
    color: var(--qt-fg-dim);
    text-transform: uppercase;
    letter-spacing: 0.08em;
  }}
  .qt-section-number {{
    font-family: var(--qt-font-display);
    font-variation-settings: "opsz" 144;
    font-weight: 900;
    font-size: 3.2rem;
    color: var(--qt-rule);
    line-height: 0.9;
    opacity: 0.95;
  }}
  .qt-section-divider {{
    border: 0;
    border-top: 1px solid var(--qt-rule);
    margin: 18px 0;
    opacity: 0.5;
  }}

  /* === KPI tile (monolithic, hard angles, left gold accent) ======== */
  .qt-tile {{
    background: var(--qt-card);
    border: 1px solid var(--qt-border);
    border-left: 3px solid var(--qt-rule);
    border-radius: 0;
    padding: 16px 18px;
    transition: background-color 120ms ease, border-color 120ms ease;
    min-height: 92px;
  }}
  .qt-tile:hover {{
    background: var(--qt-card-hover);
    border-left-color: var(--qt-accent-pos);
  }}
  .qt-tile[data-accent="mint"]   {{ border-left-color: var(--qt-accent-pos); }}
  .qt-tile[data-accent="rose"]   {{ border-left-color: var(--qt-accent-neg); }}
  .qt-tile[data-accent="amber"]  {{ border-left-color: var(--qt-accent-warn); }}
  .qt-tile[data-accent="cyan"]   {{ border-left-color: var(--qt-accent-alt); }}
  .qt-tile-accent-mint {{ border-left-color: var(--qt-accent-pos); }}
  .qt-tile-accent-rose {{ border-left-color: var(--qt-accent-neg); }}
  .qt-tile-accent-amber {{ border-left-color: var(--qt-accent-warn); }}
  .qt-tile-accent-cyan {{ border-left-color: var(--qt-accent-alt); }}
  .qt-tile-label {{
    font-family: var(--qt-font-mono);
    font-size: 0.7rem;
    font-weight: 500;
    text-transform: uppercase;
    letter-spacing: 0.12em;
    color: var(--qt-fg-muted);
    margin-bottom: 6px;
  }}
  .qt-tile-value {{
    font-family: var(--qt-font-display);
    font-weight: 700;
    font-size: 1.65rem;
    color: var(--qt-fg);
    font-variant-numeric: tabular-nums;
    line-height: 1;
    font-variation-settings: "opsz" 32;
  }}
  .qt-tile-delta {{
    font-family: var(--qt-font-mono);
    font-size: 0.8rem;
    margin-top: 4px;
    font-variant-numeric: tabular-nums;
  }}
  .qt-tile-delta-pos {{ color: var(--qt-accent-pos); }}
  .qt-tile-delta-neg {{ color: var(--qt-accent-neg); }}
  .qt-tile-delta-neutral {{ color: var(--qt-fg-dim); }}
  .qt-tile-hint {{
    font-family: var(--qt-font-mono);
    font-size: 0.7rem;
    color: var(--qt-fg-dim);
    margin-top: 6px;
    border-top: 1px solid var(--qt-border);
    padding-top: 6px;
  }}

  /* === Empty state (editorial) ===================================== */
  .qt-empty {{
    background: var(--qt-card);
    border: 1px solid var(--qt-border);
    border-radius: 0;
    padding: 28px;
    text-align: center;
    color: var(--qt-fg-muted);
  }}
  .qt-empty-icon {{
    font-size: 2.2rem;
    opacity: 0.75;
    margin-bottom: 8px;
  }}
  .qt-empty-title {{
    font-family: var(--qt-font-display);
    font-weight: 700;
    font-size: 1.1rem;
    color: var(--qt-fg);
    margin-bottom: 4px;
  }}
  .qt-empty-text {{
    font-family: var(--qt-font-mono);
    font-size: 0.85rem;
    color: var(--qt-fg-muted);
  }}

  /* === Status pills ================================================ */
  .qt-pill {{
    display: inline-flex;
    align-items: center;
    gap: 6px;
    padding: 4px 10px;
    border-radius: 0;
    border: 1px solid var(--qt-border);
    font-family: var(--qt-font-mono);
    font-size: 0.72rem;
    font-weight: 500;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    color: var(--qt-fg-muted);
    background: var(--qt-card);
  }}
  .qt-pill-dot {{
    width: 6px;
    height: 6px;
    border-radius: 50%;
    background: currentColor;
    flex-shrink: 0;
  }}
  .qt-pill-success {{ color: var(--qt-accent-pos); border-color: var(--qt-accent-pos); }}
  .qt-pill-danger  {{ color: var(--qt-accent-neg); border-color: var(--qt-accent-neg); }}
  .qt-pill-warn,
  .qt-pill-warning {{ color: var(--qt-accent-warn); border-color: var(--qt-accent-warn); }}
  .qt-pill-info    {{ color: var(--qt-accent-alt); border-color: var(--qt-accent-alt); }}
  .qt-pill-rule    {{ color: var(--qt-rule); border-color: var(--qt-rule); }}

  /* === Inputs & buttons (sharp) ==================================== */
  .stButton > button {{
    border-radius: 0 !important;
    border: 1px solid var(--qt-border) !important;
    background: var(--qt-card) !important;
    color: var(--qt-fg) !important;
    font-family: var(--qt-font-mono) !important;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    font-size: 0.82rem !important;
    transition: border-color 120ms ease, background-color 120ms ease;
  }}
  .stButton > button:hover {{
    border-color: var(--qt-rule) !important;
    background: var(--qt-card-hover) !important;
  }}
  .stButton > button:focus, .stButton > button:active {{
    border-color: var(--qt-accent-pos) !important;
    box-shadow: 0 0 0 2px var(--qt-ring, rgba(46,232,158,0.33)) !important;
  }}

  /* Selects / inputs */
  [data-baseweb="select"] > div, .stTextInput input, .stNumberInput input,
  .stDateInput input, .stTimeInput input, .stTextArea textarea {{
    border-radius: 0 !important;
    font-family: var(--qt-font-mono) !important;
    background: var(--qt-card) !important;
    color: var(--qt-fg) !important;
    border-color: var(--qt-border) !important;
  }}

  /* === Dataframes (thin rules between rows, mono cells) ============ */
  [data-testid="stDataFrame"] table, [data-testid="stDataFrame"] {{
    font-family: var(--qt-font-mono) !important;
    font-size: 0.82rem !important;
  }}
  [data-testid="stDataFrame"] td,
  [data-testid="stDataFrame"] th {{
    border-bottom: 1px solid var(--qt-border) !important;
  }}
  [data-testid="stDataFrame"] th {{
    background: var(--qt-muted-bg) !important;
    color: var(--qt-fg) !important;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    font-size: 0.7rem !important;
  }}

  /* === Expanders =================================================== */
  [data-testid="stExpander"] {{
    border: 1px solid var(--qt-border) !important;
    border-radius: 0 !important;
    background: var(--qt-card) !important;
  }}
  [data-testid="stExpander"] > details > summary {{
    font-family: var(--qt-font-mono);
    text-transform: uppercase;
    letter-spacing: 0.06em;
    color: var(--qt-fg) !important;
  }}

  /* === Alerts (info / warning / success / error) =================== */
  [data-baseweb="notification"], .stAlert {{
    border-radius: 0 !important;
    border-left: 3px solid var(--qt-rule) !important;
    font-family: var(--qt-font-mono) !important;
  }}

  /* === Animations: staggered fade-up on mount ====================== */
  @keyframes qt-fade-up {{
    from {{ opacity: 0; transform: translateY(6px); }}
    to   {{ opacity: 1; transform: translateY(0); }}
  }}
  .qt-tile, .qt-empty, .qt-hero, .qt-section, .qt-section-header {{
    animation: qt-fade-up 240ms ease-out both;
  }}
  .qt-tile:nth-child(2) {{ animation-delay: 30ms; }}
  .qt-tile:nth-child(3) {{ animation-delay: 60ms; }}
  .qt-tile:nth-child(4) {{ animation-delay: 90ms; }}
  .qt-tile:nth-child(5) {{ animation-delay: 120ms; }}
  .qt-tile:nth-child(6) {{ animation-delay: 150ms; }}

  /* === Scrollbar (subtle, on-brand) ================================= */
  ::-webkit-scrollbar {{ width: 10px; height: 10px; }}
  ::-webkit-scrollbar-track {{ background: var(--qt-bg); }}
  ::-webkit-scrollbar-thumb {{
    background: var(--qt-border);
    border-radius: 0;
  }}
  ::-webkit-scrollbar-thumb:hover {{ background: var(--qt-fg-dim); }}

  /* === Footer / captions ============================================ */
  .qt-footer, .qt-caption {{
    font-family: var(--qt-font-mono);
    font-size: 0.72rem;
    color: var(--qt-fg-dim);
    text-transform: uppercase;
    letter-spacing: 0.08em;
  }}
</style>
"""


# Alias for tests / future callers preferring an explicit name
inject_streamlit_css_html = inject_streamlit_css


# ============================================================================
# 5. HTML BUILDERS — return strings, caller wraps in st.markdown(unsafe_allow_html)
# ============================================================================
def hero_header_html(
    title: str,
    subtitle: str = "",
    pills: Iterable[tuple[str, str]] = (),
    *,
    section_number: str = "",
    meta: str = "",
) -> str:
    """Editorial hero block — § number + serif display title + status pills.

    Backward-compatible with v2 callers (``title``, ``subtitle``, ``pills``
    positional or kwargs). New kwargs ``section_number`` (e.g. "00") and
    ``meta`` (right-aligned secondary text) are optional.
    """
    num_html = (
        f'<div class="qt-hero-number">§ {section_number}</div>'
        if section_number
        else '<div class="qt-hero-accent"></div>'
    )
    pill_html = "".join(
        f'<span class="qt-pill qt-pill-{variant}">'
        f'<span class="qt-pill-dot"></span>{label}</span>'
        for label, variant in pills
    )
    pills_block = (
        f'<div style="display:flex;gap:8px;flex-wrap:wrap;justify-content:flex-end;">{pill_html}</div>'
        if pill_html
        else ""
    )
    subtitle_html = (
        f'<div class="qt-hero-subtitle">{subtitle}</div>' if subtitle else ""
    )
    meta_html = f'<div class="qt-hero-meta">{meta}</div>' if meta else ""
    right_block = pills_block or meta_html
    return f"""
    <div class="qt-hero">
      {num_html}
      <div class="qt-hero-body">
        <div class="qt-hero-title">{title}</div>
        {subtitle_html}
      </div>
      {right_block}
    </div>
    """


def status_pill_html(label: str, variant: str = "info") -> str:
    """A single status pill — use in sidebar / banners.

    ``variant`` ∈ {success, danger, warn, warning, info, rule}.
    """
    return (
        f'<span class="qt-pill qt-pill-{variant}">'
        f'<span class="qt-pill-dot"></span>{label}</span>'
    )


def section_header_html(
    title: str,
    *,
    icon: str | None = "",
    subtitle: str = "",
    meta: str = "",
) -> str:
    """Section heading with optional icon, subtitle, and right-aligned meta.

    Wraps content in BOTH ``qt-section`` and ``qt-section-header`` classes
    for forward compatibility (tests / future code may target either).
    """
    icon_html = f'<div class="qt-section-icon">{icon}</div>' if icon else ""
    sub_html = (
        f'<div class="qt-section-subtitle">{subtitle}</div>' if subtitle else ""
    )
    meta_html = f'<div class="qt-section-meta">{meta}</div>' if meta else ""
    return f"""
    <div class="qt-section qt-section-header">
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
    """Compact KPI tile — monolithic, gold-accent on the left, mono uppercase label.

    ``delta_dir`` ∈ {pos, neg, neutral}.
    ``accent``    ∈ {"", mint, cyan, amber, rose}.
    """
    accent_cls = f" qt-tile-accent-{accent}" if accent else ""
    accent_attr = f' data-accent="{accent}"' if accent else ""
    delta_html = (
        f'<div class="qt-tile-delta qt-tile-delta-{delta_dir}">{delta}</div>'
        if delta else ""
    )
    hint_html = f'<div class="qt-tile-hint">{hint}</div>' if hint else ""
    return f"""
    <div class="qt-tile{accent_cls}"{accent_attr}>
      <div class="qt-tile-label">{label}</div>
      <div class="qt-tile-value">{value}</div>
      {delta_html}
      {hint_html}
    </div>
    """


def stat_strip_html(items: list[dict]) -> str:
    """Horizontal strip of KPI tiles.

    Each item: ``{label, value, delta?, delta_dir?, accent?, hint?}``.
    """
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
    """Editorial empty-state placeholder (no rounded corners, mono body)."""
    text_html = f'<div class="qt-empty-text">{text}</div>' if text else ""
    return f"""
    <div class="qt-empty">
      <div class="qt-empty-icon">{icon}</div>
      <div class="qt-empty-title">{title}</div>
      {text_html}
    </div>
    """


def section_divider() -> str:
    """Thin gold rule between sections."""
    return '<hr class="qt-section-divider">'


# ============================================================================
# 6. FORMATTERS
# ============================================================================
def fmt_eur(value: float, decimals: int = 0) -> str:
    """Format ``value`` as EUR with thin space thousand separators."""
    sign = "-" if value < 0 else ""
    return f"{sign}€{abs(value):,.{decimals}f}".replace(",", " ")


def fmt_pct(value: float, decimals: int = 2) -> str:
    """``0.0142`` → ``+1.42%``."""
    return f"{value * 100:+.{decimals}f}%"


def color_pct(value: float) -> str:
    """Return the hex color matching the sign of ``value``."""
    if value > 0:
        return PALETTE.profit
    if value < 0:
        return PALETTE.loss
    return PALETTE.fg_muted


def hex_to_rgba(hex_str: str, alpha: float = 0.13) -> str:
    """Convert ``#RRGGBB`` (or ``#RRGGBBAA`` — AA ignored) → ``rgba(...)``."""
    h = hex_str.lstrip("#")
    if len(h) == 8:
        h = h[:6]
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f"rgba({r},{g},{b},{alpha:.2f})"


# ============================================================================
# 7. PLOTLY TEMPLATE — overwrite the placeholder with the v3 module
# ============================================================================
try:
    from src.viz.plotly_template_v3 import PLOTLY_TEMPLATE as _PLOTLY_TEMPLATE_V3
    PLOTLY_TEMPLATE = _PLOTLY_TEMPLATE_V3
except ImportError:
    # plotly_template_v3 not yet created — keep the inline default above.
    pass
