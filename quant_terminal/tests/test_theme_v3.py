"""Design v3 — Wall Street Brutalist visual language tests.

Pure HTML/CSS output tests (no Streamlit runtime).
"""
from __future__ import annotations


# ---------------------------------------------------------------------------
# Task 1 — Palette tokens
# ---------------------------------------------------------------------------
def test_palette_v3_uses_wall_street_brutalist_palette():
    """Verify v3 palette tokens — deep ink + bone + sharp accents."""
    from src.viz.theme import PALETTE
    assert PALETTE.bg == "#0A0A0F"
    assert PALETTE.bg_elev == "#14141C"
    assert PALETTE.card == "#1A1A24"
    assert PALETTE.card_hover == "#242430"
    assert PALETTE.border == "#2A2A38"
    assert PALETTE.border_strong == "#4A4A60"
    # Bone white (warm)
    assert PALETTE.fg == "#FAF7F2"
    # Sharp single accent for losses — mercury red
    assert PALETTE.accent_neg == "#FF3838"
    # Gold for rule lines / decorative numbers
    assert PALETTE.accent_serif == "#D4AF37"


def test_palette_v3_keeps_legacy_fields_for_back_compat():
    """The 25 files importing PALETTE.profit/loss/warning/info must keep working."""
    from src.viz.theme import PALETTE
    for attr in ("profit", "loss", "warning", "info", "neutral",
                 "ring", "bull_body", "bear_body",
                 "primary", "secondary", "accent", "accent_alt", "accent_violet"):
        assert hasattr(PALETTE, attr), f"PALETTE missing legacy field {attr}"


def test_palette_v3_exposes_plotly_colorway_v3():
    """7-hue colorway used by the Plotly template."""
    from src.viz.theme import PALETTE
    assert hasattr(PALETTE, "plotly_colorway_v3")
    colorway = PALETTE.plotly_colorway_v3
    assert len(colorway) == 7
    assert "#FAF7F2" in colorway  # bone
    assert "#FF3838" in colorway  # mercury
    assert "#D4AF37" in colorway  # gold


# ---------------------------------------------------------------------------
# Task 2 — Typography
# ---------------------------------------------------------------------------
def test_font_stack_v3_uses_fraunces_and_jetbrains():
    from src.viz.theme import FONT_BODY, FONT_DISPLAY, FONT_MONO
    assert "Fraunces" in FONT_DISPLAY
    assert "JetBrains Mono" in FONT_BODY  # mono-everywhere doctrine
    assert "JetBrains Mono" in FONT_MONO
    # BANNED fonts per frontend-design skill
    for banned in ("Inter", "Roboto", "Arial", "Helvetica", "system-ui"):
        assert banned not in FONT_DISPLAY, f"{banned} is banned"
        assert banned not in FONT_BODY, f"{banned} is banned"


# ---------------------------------------------------------------------------
# Task 3 — CSS injection
# ---------------------------------------------------------------------------
def test_css_v3_loads_google_fonts():
    from src.viz.theme import inject_streamlit_css_html
    html = inject_streamlit_css_html()
    assert "fonts.googleapis.com" in html
    assert "Fraunces" in html
    assert "JetBrains+Mono" in html


def test_css_v3_has_noise_overlay_and_gold_rules():
    from src.viz.theme import inject_streamlit_css_html
    html = inject_streamlit_css_html()
    # Subtle SVG noise overlay (signature atmosphere)
    assert "noise" in html.lower() or "fractalnoise" in html.lower()
    # Gold rule for editorial dividers
    assert "#D4AF37" in html
    # No bullshit large radii (brutalist hard angles)
    assert "border-radius: 16px" not in html
    assert "border-radius: 20px" not in html


def test_css_v3_uses_display_font_on_h1():
    from src.viz.theme import inject_streamlit_css_html
    html = inject_streamlit_css_html()
    assert "Fraunces" in html
    assert "h1" in html.lower()


# ---------------------------------------------------------------------------
# Task 4 — Hero header
# ---------------------------------------------------------------------------
def test_hero_v3_includes_section_number_and_uses_display_font():
    from src.viz.theme import hero_header_html
    html = hero_header_html(
        title="Quant Terminal",
        subtitle="Institutional cross-asset cockpit",
        section_number="00",
    )
    assert "qt-hero-number" in html or "qt-section-number" in html
    assert "00" in html
    assert "Quant Terminal" in html
    assert "Institutional cross-asset cockpit" in html


def test_hero_v3_works_without_section_number():
    """Backward-compatible — existing callers pass only title."""
    from src.viz.theme import hero_header_html
    html = hero_header_html("Some Title")
    assert "Some Title" in html


# ---------------------------------------------------------------------------
# Task 5 — Section header
# ---------------------------------------------------------------------------
def test_section_header_v3_renders_with_serif_dropcap_and_rule():
    from src.viz.theme import section_header_html
    html = section_header_html(
        "Portfolio",
        icon="📈",
        subtitle="60+ analytics",
        meta="NAV €10 000",
    )
    assert "qt-section-header" in html
    assert "qt-section-title" in html
    assert "Portfolio" in html
    assert "60+ analytics" in html
    assert "NAV €10 000" in html


# ---------------------------------------------------------------------------
# Task 6 — KPI tile
# ---------------------------------------------------------------------------
def test_kpi_tile_v3_uses_left_accent_and_mono_label():
    from src.viz.theme import kpi_tile_html
    html = kpi_tile_html(
        label="NAV",
        value="€10 432",
        delta="+1.42%",
        delta_dir="pos",
        hint="vs yesterday",
    )
    assert "qt-tile" in html
    assert "qt-tile-label" in html
    assert "qt-tile-value" in html
    assert "qt-tile-delta-pos" in html
    assert "vs yesterday" in html
    assert "qt-tile-hint" in html
    assert "linear-gradient" not in html


# ---------------------------------------------------------------------------
# Task 7 — Empty state
# ---------------------------------------------------------------------------
def test_empty_state_v3_outputs_brutalist_classes():
    from src.viz.theme import empty_state_html
    html = empty_state_html(title="No data", text="Upload a CSV.", icon="📥")
    assert "qt-empty" in html
    assert "qt-empty-title" in html
    assert "qt-empty-text" in html
    assert "qt-empty-icon" in html
    assert "No data" in html
    assert "Upload a CSV." in html


# ---------------------------------------------------------------------------
# Task 8 — Stat strip
# ---------------------------------------------------------------------------
def test_stat_strip_v3_renders_grid_with_tiles():
    from src.viz.theme import stat_strip_html
    html = stat_strip_html([
        {"label": "VaR 95%", "value": "€421"},
        {"label": "Sharpe", "value": "1.42"},
        {"label": "Beta", "value": "0.87"},
    ])
    assert html.count("qt-tile-label") == 3
    assert html.count("qt-tile-value") == 3
    assert "grid-template-columns" in html


# ---------------------------------------------------------------------------
# Task 9 — Plotly template v3
# ---------------------------------------------------------------------------
def test_plotly_template_v3_uses_v3_palette():
    from src.viz.theme import PALETTE, PLOTLY_TEMPLATE
    tpl = PLOTLY_TEMPLATE
    assert tpl["layout"]["paper_bgcolor"] == PALETTE.bg
    assert tpl["layout"]["plot_bgcolor"] == PALETTE.bg
    assert "JetBrains Mono" in tpl["layout"]["font"]["family"]
    assert tpl["layout"]["xaxis"]["gridcolor"] == PALETTE.border
    assert tpl["layout"]["colorway"][0] == "#FAF7F2"
    assert "#FF3838" in tpl["layout"]["colorway"]
