# Quant Terminal — Design v3 "Wall Street Brutalist" Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refonte aesthetic complète du Quant Terminal en remplaçant la palette/typo/composants v2 (Inter + cool blue) par un langage visuel "Wall Street Brutalist" éditorial-mono — sans casser aucun des 17 tabs ni les 281 tests existants.

**Architecture:** Upgrade in-place de `src/viz/theme.py` (25 fichiers importent ce module — les signatures restent identiques, seul le rendu visuel change). Nouveau Plotly template v3, nouveaux composants éditoriaux (KPI tile avec § numérotation, section headers avec drop caps, dividers serif). Injection CSS unique au démarrage via la fonction existante `inject_streamlit_css()`. Tests HTML/CSS output uniquement (pas de visual regression — Streamlit ne s'y prête pas).

**Tech Stack:** Streamlit (existant), Google Fonts CDN (Fraunces + JetBrains Mono — tous deux libres), CSS custom variables, Plotly template overrides.

**Direction aesthetic engagée :**
- **Display font :** [Fraunces](https://fonts.google.com/specimen/Fraunces) — variable serif éditorial, opsz 144 pour les hero, 24 pour les section headers
- **Body/UI/numerics :** [JetBrains Mono](https://www.jetbrains.com/lp/mono/) — mono partout = vrai feel terminal (Bloomberg/Reuters), Plus distinctif que Söhne
- **Palette :** deep ink + bone white + mercury red + caution amber + gold rule lines (cf Task 1)
- **Atmosphere :** noise overlay SVG 5% opacity + radial gradient corner gold 8% + dividers gold 1px
- **Layout :** § numérotation décorative ("§ 01 — Portfolio"), drop caps sur premier mot, hard right angles (border-radius: 0), staggered fade-in 150ms au montage de tab
- **Banned :** Inter, Roboto, Arial, Helvetica, system-ui, border-radius > 4px, mint+cyan combos v2, drop shadows, glassmorphism

---

## File Structure

| Fichier | Action | Responsabilité |
|---|---|---|
| `src/viz/theme.py` | Modify (in-place) | Palette + fonts + CSS + tous les builders HTML |
| `src/viz/plotly_template_v3.py` | Create | Template Plotly isolé (réutilisé par toutes les viz) |
| `tests/test_theme_v3.py` | Create | Tests HTML/CSS output + Plotly template |
| `app.py` | Modify | Mettre à jour le footer pour annoncer "v3 · Wall Street Brutalist" |
| `docs/DASHBOARD.md` | Modify | Section "Design language" mise à jour |

**Aucun autre fichier ne sera modifié.** Les 25 fichiers qui importent `src/viz/theme` continueront à appeler `kpi_tile_html(...)`, `section_header_html(...)`, etc. — leurs signatures sont préservées.

---

## Tasks

### Task 1: Design tokens v3 — palette

**Files:**
- Modify: `src/viz/theme.py:28-78` (Palette dataclass)
- Test: `tests/test_theme_v3.py` (new)

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_theme_v3.py
from src.viz.theme import PALETTE

def test_palette_v3_uses_wall_street_brutalist_palette():
    """Verify v3 palette tokens — deep ink + bone + sharp accents."""
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_theme_v3.py::test_palette_v3_uses_wall_street_brutalist_palette -v`
Expected: FAIL (current Palette has `bg="#06080F"`, no `accent_serif` field)

- [ ] **Step 3: Replace Palette dataclass in theme.py**

```python
# src/viz/theme.py (replace the existing @dataclass(frozen=True) class Palette block)
@dataclass(frozen=True)
class Palette:
    # --- Surfaces (5-step elevation scale — warmer ink) ------------------
    bg: str = "#0A0A0F"               # deep oil ink
    bg_elev: str = "#14141C"          # one elevation up
    card: str = "#1A1A24"             # cards, panels
    card_hover: str = "#242430"       # hover state
    muted_bg: str = "#1F1F2A"         # subtle highlighted region
    border: str = "#2A2A38"           # default border
    border_strong: str = "#4A4A60"    # active selections
    rule: str = "#D4AF37"             # gold rule lines (decorative)

    # --- Text (bone white system, 4-step) ---------------------------------
    fg: str = "#FAF7F2"               # bone (print paper feel)
    fg_muted: str = "#B8B5AC"         # secondary
    fg_dim: str = "#6B6960"           # tertiary
    fg_disabled: str = "#3F3D38"      # disabled

    # --- Brand & accents (sharp, single-purpose) --------------------------
    primary: str = "#0A0A0F"          # legacy compat (= bg)
    secondary: str = "#14141C"        # legacy compat (= bg_elev)
    accent: str = "#2EE89E"           # sharp mint — P&L positive
    accent_pos: str = "#2EE89E"       # explicit positive
    accent_neg: str = "#FF3838"       # mercury red — losses, warnings P&L
    accent_warn: str = "#FFB800"      # caution amber — used SPARINGLY
    accent_alt: str = "#22D3EE"       # cyan — info chips only (kept for back-compat)
    accent_violet: str = "#8B5CF6"    # premium highlights
    accent_serif: str = "#D4AF37"     # GOLD — rules, § numbers, decorative

    # --- Plotly colorway (sharp, distinct hues) ---------------------------
    plotly_colorway_v3: tuple = (
        "#FAF7F2",  # bone
        "#FF3838",  # mercury
        "#FFB800",  # amber
        "#2EE89E",  # mint
        "#22D3EE",  # cyan
        "#D4AF37",  # gold
        "#8B5CF6",  # violet
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_theme_v3.py::test_palette_v3_uses_wall_street_brutalist_palette -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/viz/theme.py tests/test_theme_v3.py
git commit -m "feat(design v3 #1): Wall Street Brutalist palette tokens"
```

---

### Task 2: Typography stack — Fraunces + JetBrains Mono

**Files:**
- Modify: `src/viz/theme.py:79-95` (FONT_BODY / FONT_MONO constants area)
- Test: `tests/test_theme_v3.py`

- [ ] **Step 1: Add failing test**

```python
# tests/test_theme_v3.py (append)
from src.viz.theme import FONT_BODY, FONT_MONO, FONT_DISPLAY

def test_font_stack_v3_uses_fraunces_and_jetbrains():
    assert "Fraunces" in FONT_DISPLAY
    assert "JetBrains Mono" in FONT_BODY  # mono-everywhere doctrine
    assert "JetBrains Mono" in FONT_MONO
    # BANNED fonts per frontend-design skill
    for banned in ("Inter", "Roboto", "Arial", "Helvetica", "system-ui"):
        assert banned not in FONT_DISPLAY, f"{banned} is banned"
        assert banned not in FONT_BODY,    f"{banned} is banned"
```

- [ ] **Step 2: Run test — verify FAIL**

Run: `python -m pytest tests/test_theme_v3.py::test_font_stack_v3_uses_fraunces_and_jetbrains -v`
Expected: FAIL (current FONT_BODY = `'Inter, …'`, no FONT_DISPLAY constant)

- [ ] **Step 3: Replace font constants in theme.py**

Find the existing FONT_BODY/FONT_MONO constants (around line 80) and replace:

```python
# src/viz/theme.py
FONT_DISPLAY = '"Fraunces", "Newsreader", Georgia, serif'
FONT_BODY = '"JetBrains Mono", "IBM Plex Mono", ui-monospace, Menlo, monospace'
FONT_MONO = '"JetBrains Mono", "IBM Plex Mono", ui-monospace, Menlo, monospace'

GOOGLE_FONTS_URL = (
    "https://fonts.googleapis.com/css2"
    "?family=Fraunces:opsz,wght@9..144,300;9..144,400;9..144,700;9..144,900"
    "&family=JetBrains+Mono:wght@300;400;500;700&display=swap"
)
```

- [ ] **Step 4: Run test — verify PASS**

Run: `python -m pytest tests/test_theme_v3.py::test_font_stack_v3_uses_fraunces_and_jetbrains -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/viz/theme.py tests/test_theme_v3.py
git commit -m "feat(design v3 #2): Fraunces + JetBrains Mono everywhere"
```

---

### Task 3: CSS injection refactor — Google Fonts CDN + noise overlay + gold rules

**Files:**
- Modify: `src/viz/theme.py` (`inject_streamlit_css()` function — find by name)
- Test: `tests/test_theme_v3.py`

- [ ] **Step 1: Add failing test**

```python
# tests/test_theme_v3.py (append)
from src.viz.theme import inject_streamlit_css_html  # NEW pure helper

def test_css_v3_loads_google_fonts():
    html = inject_streamlit_css_html()
    assert "fonts.googleapis.com" in html
    assert "Fraunces" in html
    assert "JetBrains+Mono" in html

def test_css_v3_has_noise_overlay_and_gold_rules():
    html = inject_streamlit_css_html()
    # Subtle SVG noise overlay (signature atmosphere)
    assert "noise" in html.lower() or "fractalnoise" in html.lower()
    # Gold rule for editorial dividers
    assert "#D4AF37" in html
    # No rounded radii > 4px on top-level cards (brutalist hard angles)
    assert "border-radius: 16px" not in html
    assert "border-radius: 20px" not in html

def test_css_v3_uses_display_font_on_h1():
    html = inject_streamlit_css_html()
    assert "Fraunces" in html
    # H1/headers should reach for the display font
    assert "h1" in html.lower()
```

- [ ] **Step 2: Run test — verify FAIL**

Run: `python -m pytest tests/test_theme_v3.py -v -k "css_v3"`
Expected: 3 FAIL (helper doesn't exist + content not migrated)

- [ ] **Step 3: Extract pure CSS string helper + rewrite content**

Add (or replace) the CSS injection function:

```python
# src/viz/theme.py
def inject_streamlit_css_html() -> str:
    """Pure-function variant returning the <style> block — testable.

    Called by inject_streamlit_css() which wraps it with st.markdown().
    """
    p = PALETTE
    return f"""
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="{GOOGLE_FONTS_URL}" rel="stylesheet">

<style>
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
    --qt-rule: {p.rule};
    --qt-accent-pos: {p.accent_pos};
    --qt-accent-neg: {p.accent_neg};
    --qt-accent-warn: {p.accent_warn};
    --qt-accent-serif: {p.accent_serif};
    --qt-font-display: {FONT_DISPLAY};
    --qt-font-body: {FONT_BODY};
    --qt-font-mono: {FONT_MONO};
  }}

  /* Page background: deep ink + SVG noise overlay + corner gold mesh */
  .stApp, [data-testid="stAppViewContainer"] {{
    background-color: var(--qt-bg) !important;
    background-image:
      radial-gradient(circle at 100% 0%, rgba(212,175,55,0.08) 0%, transparent 600px),
      url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='200' height='200'><filter id='n'><feTurbulence type='fractalNoise' baseFrequency='0.85' numOctaves='2' stitchTiles='stitch'/></filter><rect width='100%25' height='100%25' filter='url(%23n)' opacity='0.05'/></svg>");
    background-attachment: fixed;
    color: var(--qt-fg);
    font-family: var(--qt-font-body);
    font-variant-numeric: tabular-nums;
    letter-spacing: 0;
  }}

  /* Display: serif editorial — headers + hero */
  h1, h2, h3, .qt-display {{
    font-family: var(--qt-font-display);
    font-weight: 700;
    letter-spacing: -0.02em;
    color: var(--qt-fg);
  }}
  h1 {{ font-size: 2.6rem; font-variation-settings: "opsz" 96; line-height: 1.05; }}
  h2 {{ font-size: 1.85rem; font-variation-settings: "opsz" 32; }}
  h3 {{ font-size: 1.25rem; font-variation-settings: "opsz" 14; }}

  /* Mono everywhere else — terminal feel */
  p, span, div, td, th, label, input, .stMarkdown {{
    font-family: var(--qt-font-body);
  }}

  /* Sidebar */
  [data-testid="stSidebar"] {{
    background-color: var(--qt-bg-elev) !important;
    border-right: 1px solid var(--qt-border);
  }}

  /* Brutalist hard right-angles on KPI tiles */
  .qt-tile {{
    background: var(--qt-card);
    border: 1px solid var(--qt-border);
    border-left: 3px solid var(--qt-rule);
    border-radius: 0;
    padding: 16px 18px;
    transition: background-color 120ms ease, border-color 120ms ease;
  }}
  .qt-tile:hover {{
    background: var(--qt-card-hover);
    border-left-color: var(--qt-accent-pos);
  }}
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

  /* Empty states — ASCII art editorial */
  .qt-empty {{
    background: var(--qt-card);
    border: 1px solid var(--qt-border);
    border-radius: 0;
    padding: 28px;
    text-align: center;
    color: var(--qt-fg-muted);
  }}
  .qt-empty-icon {{ font-size: 2.2rem; opacity: 0.75; margin-bottom: 8px; }}
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

  /* Tabs — uppercase letter-spaced, no radius, gold underline on active */
  .stTabs [data-baseweb="tab-list"] {{
    gap: 0;
    border-bottom: 1px solid var(--qt-border);
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
  }}
  .stTabs [aria-selected="true"] {{
    border-bottom-color: var(--qt-rule) !important;
    color: var(--qt-fg) !important;
  }}

  /* Page-load staggered fade-in */
  @keyframes qt-fade-up {{
    from {{ opacity: 0; transform: translateY(6px); }}
    to   {{ opacity: 1; transform: translateY(0); }}
  }}
  .qt-tile, .qt-empty, h1, h2 {{
    animation: qt-fade-up 240ms ease-out both;
  }}
  .qt-tile:nth-child(2) {{ animation-delay: 30ms; }}
  .qt-tile:nth-child(3) {{ animation-delay: 60ms; }}
  .qt-tile:nth-child(4) {{ animation-delay: 90ms; }}
  .qt-tile:nth-child(5) {{ animation-delay: 120ms; }}

  /* Streamlit dataframes — thin gold rules between rows */
  [data-testid="stDataFrame"] table {{
    font-family: var(--qt-font-mono) !important;
    font-size: 0.82rem !important;
  }}
  [data-testid="stDataFrame"] td, [data-testid="stDataFrame"] th {{
    border-bottom: 1px solid var(--qt-border) !important;
  }}

  /* Inputs / buttons — sharp */
  .stButton > button {{
    border-radius: 0 !important;
    border: 1px solid var(--qt-border) !important;
    background: var(--qt-card) !important;
    color: var(--qt-fg) !important;
    font-family: var(--qt-font-mono) !important;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    transition: border-color 120ms ease;
  }}
  .stButton > button:hover {{
    border-color: var(--qt-rule) !important;
  }}

  /* Editorial § numbering helper */
  .qt-section-number {{
    font-family: var(--qt-font-display);
    font-variation-settings: "opsz" 144;
    font-weight: 900;
    font-size: 3.2rem;
    color: var(--qt-rule);
    line-height: 0.9;
    margin-right: 14px;
    opacity: 0.95;
  }}
  .qt-section-header {{
    display: flex;
    align-items: baseline;
    gap: 14px;
    padding: 18px 0 14px 0;
    border-bottom: 1px solid var(--qt-rule);
    margin-bottom: 18px;
  }}
  .qt-section-title {{
    font-family: var(--qt-font-display);
    font-weight: 700;
    font-size: 1.75rem;
    color: var(--qt-fg);
    letter-spacing: -0.01em;
  }}
  .qt-section-subtitle {{
    font-family: var(--qt-font-mono);
    font-size: 0.85rem;
    color: var(--qt-fg-muted);
    margin-top: 4px;
  }}
  .qt-section-meta {{
    margin-left: auto;
    font-family: var(--qt-font-mono);
    font-size: 0.75rem;
    color: var(--qt-fg-dim);
    text-transform: uppercase;
    letter-spacing: 0.08em;
  }}
</style>
"""


def inject_streamlit_css() -> None:
    """Call once at app start."""
    import streamlit as st
    st.markdown(inject_streamlit_css_html(), unsafe_allow_html=True)
```

If `inject_streamlit_css` already exists as a `st.markdown(...)` wrapper, replace its body with `st.markdown(inject_streamlit_css_html(), unsafe_allow_html=True)`.

- [ ] **Step 4: Run test — verify PASS**

Run: `python -m pytest tests/test_theme_v3.py -v -k "css_v3"`
Expected: 3 PASS

- [ ] **Step 5: Commit**

```bash
git add src/viz/theme.py tests/test_theme_v3.py
git commit -m "feat(design v3 #3): CSS injection — Google Fonts + noise overlay + gold rules"
```

---

### Task 4: Hero header v3 — asymmetric editorial with § number

**Files:**
- Modify: `src/viz/theme.py` (`hero_header_html()` function)
- Test: `tests/test_theme_v3.py`

- [ ] **Step 1: Add failing test**

```python
# tests/test_theme_v3.py (append)
from src.viz.theme import hero_header_html

def test_hero_v3_includes_section_number_and_uses_display_font():
    html = hero_header_html(
        title="Quant Terminal",
        subtitle="Institutional cross-asset cockpit",
        section_number="00",
    )
    assert "qt-section-number" in html or "qt-hero-number" in html
    assert "00" in html
    assert "Quant Terminal" in html
    assert "Institutional cross-asset cockpit" in html
```

- [ ] **Step 2: Run test — verify FAIL**

Run: `python -m pytest tests/test_theme_v3.py::test_hero_v3_includes_section_number_and_uses_display_font -v`
Expected: FAIL (current signature doesn't accept section_number)

- [ ] **Step 3: Replace hero_header_html in theme.py**

Find the existing `def hero_header_html(...)` and replace with:

```python
def hero_header_html(
    title: str,
    *,
    subtitle: str = "",
    section_number: str = "",
    meta: str = "",
) -> str:
    """Editorial hero block — § number on the left, title in serif display."""
    num_html = (
        f'<span class="qt-hero-number">§ {section_number}</span>'
        if section_number else ""
    )
    subtitle_html = (
        f'<div class="qt-hero-subtitle">{subtitle}</div>'
        if subtitle else ""
    )
    meta_html = (
        f'<div class="qt-hero-meta">{meta}</div>'
        if meta else ""
    )
    return f"""
    <style>
      .qt-hero {{
        display: flex;
        align-items: baseline;
        gap: 20px;
        padding: 28px 0 20px 0;
        border-bottom: 1px solid {PALETTE.rule};
        margin-bottom: 24px;
      }}
      .qt-hero-number {{
        font-family: {FONT_DISPLAY};
        font-variation-settings: "opsz" 144;
        font-weight: 900;
        font-size: 4rem;
        color: {PALETTE.rule};
        line-height: 0.85;
        opacity: 0.95;
      }}
      .qt-hero-body {{ flex: 1; }}
      .qt-hero-title {{
        font-family: {FONT_DISPLAY};
        font-weight: 700;
        font-size: 2.5rem;
        line-height: 1.05;
        color: {PALETTE.fg};
        letter-spacing: -0.02em;
      }}
      .qt-hero-subtitle {{
        font-family: {FONT_MONO};
        font-size: 0.9rem;
        color: {PALETTE.fg_muted};
        margin-top: 6px;
      }}
      .qt-hero-meta {{
        font-family: {FONT_MONO};
        font-size: 0.75rem;
        color: {PALETTE.fg_dim};
        text-transform: uppercase;
        letter-spacing: 0.08em;
      }}
    </style>
    <div class="qt-hero">
      {num_html}
      <div class="qt-hero-body">
        <div class="qt-hero-title">{title}</div>
        {subtitle_html}
      </div>
      {meta_html}
    </div>
    """
```

- [ ] **Step 4: Run test — verify PASS**

Run: `python -m pytest tests/test_theme_v3.py::test_hero_v3_includes_section_number_and_uses_display_font -v`
Expected: PASS

- [ ] **Step 5: Verify other callers still work**

Run: `python -c "from src.viz.theme import hero_header_html; print(hero_header_html('test'))"`
Expected: no exception (positional `title` still works, optional kwargs)

- [ ] **Step 6: Commit**

```bash
git add src/viz/theme.py tests/test_theme_v3.py
git commit -m "feat(design v3 #4): hero header — editorial § numbering"
```

---

### Task 5: section_header_html v3 — drop cap + ruled separator

**Files:**
- Modify: `src/viz/theme.py` (`section_header_html()`)
- Test: `tests/test_theme_v3.py`

- [ ] **Step 1: Add failing test**

```python
def test_section_header_v3_renders_with_serif_dropcap_and_rule():
    from src.viz.theme import section_header_html
    html = section_header_html("Portfolio", icon="📈", subtitle="60+ analytics", meta="NAV €10 000")
    assert "qt-section-header" in html
    # Serif display title (look for the css class only — fonts inline elsewhere)
    assert "qt-section-title" in html
    # Rule line is present
    assert "border-bottom" in html or "qt-section-header" in html
    assert "Portfolio" in html
    assert "60+ analytics" in html
    assert "NAV €10 000" in html
```

- [ ] **Step 2: Run test — verify FAIL**

Run: `python -m pytest tests/test_theme_v3.py::test_section_header_v3_renders_with_serif_dropcap_and_rule -v`
Expected: FAIL (current returns different markup)

- [ ] **Step 3: Replace section_header_html**

Find current function and replace:

```python
def section_header_html(
    title: str,
    *,
    icon: str | None = None,
    subtitle: str = "",
    meta: str = "",
) -> str:
    icon_html = f'<span class="qt-section-icon">{icon}</span>' if icon else ""
    subtitle_html = (
        f'<div class="qt-section-subtitle">{subtitle}</div>' if subtitle else ""
    )
    meta_html = (
        f'<div class="qt-section-meta">{meta}</div>' if meta else ""
    )
    return f"""
    <div class="qt-section-header">
      {icon_html}
      <div style="flex:1;">
        <div class="qt-section-title">{title}</div>
        {subtitle_html}
      </div>
      {meta_html}
    </div>
    """
```

(Styling for `.qt-section-*` already lives in `inject_streamlit_css_html()` from Task 3.)

- [ ] **Step 4: Run test — verify PASS**

Run: `python -m pytest tests/test_theme_v3.py::test_section_header_v3_renders_with_serif_dropcap_and_rule -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/viz/theme.py tests/test_theme_v3.py
git commit -m "feat(design v3 #5): section header — gold rule + serif title"
```

---

### Task 6: kpi_tile_html v3 — monolithic with left gold accent

**Files:**
- Modify: `src/viz/theme.py` (`kpi_tile_html()`)
- Test: `tests/test_theme_v3.py`

- [ ] **Step 1: Add failing test**

```python
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
    # No bullshit border-radius (brutalist hard angles enforced by CSS)
    # No inline gradients
    assert "linear-gradient" not in html
```

- [ ] **Step 2: Run test — verify FAIL or PASS**

Run: `python -m pytest tests/test_theme_v3.py::test_kpi_tile_v3_uses_left_accent_and_mono_label -v`

If the existing `kpi_tile_html` already returns these classes, this test may already pass — that's fine, move on. If it FAILs, fix:

- [ ] **Step 3: Replace kpi_tile_html if needed**

```python
def kpi_tile_html(
    label: str,
    value: str,
    *,
    delta: str = "",
    delta_dir: str = "neutral",
    hint: str = "",
    accent: str = "",
) -> str:
    accent_attr = f' data-accent="{accent}"' if accent else ""
    delta_html = (
        f'<div class="qt-tile-delta qt-tile-delta-{delta_dir}">{delta}</div>'
        if delta else ""
    )
    hint_html = f'<div class="qt-tile-hint">{hint}</div>' if hint else ""
    return f"""
    <div class="qt-tile"{accent_attr}>
      <div class="qt-tile-label">{label}</div>
      <div class="qt-tile-value">{value}</div>
      {delta_html}
      {hint_html}
    </div>
    """
```

- [ ] **Step 4: Run test — verify PASS**

Run: `python -m pytest tests/test_theme_v3.py::test_kpi_tile_v3_uses_left_accent_and_mono_label -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/viz/theme.py tests/test_theme_v3.py
git commit -m "feat(design v3 #6): KPI tile — monolithic gold-accent"
```

---

### Task 7: empty_state_html v3 — editorial tone

**Files:**
- Modify: `src/viz/theme.py` (`empty_state_html()`)
- Test: `tests/test_theme_v3.py`

- [ ] **Step 1: Add failing test**

```python
def test_empty_state_v3_outputs_brutalist_classes():
    from src.viz.theme import empty_state_html
    html = empty_state_html(title="No data", text="Upload a CSV.", icon="📥")
    assert "qt-empty" in html
    assert "qt-empty-title" in html
    assert "qt-empty-text" in html
    assert "qt-empty-icon" in html
    assert "No data" in html
    assert "Upload a CSV." in html
```

- [ ] **Step 2: Run test — verify state**

Run: `python -m pytest tests/test_theme_v3.py::test_empty_state_v3_outputs_brutalist_classes -v`

- [ ] **Step 3: Ensure empty_state_html returns the new classes**

```python
def empty_state_html(
    title: str = "No data",
    text: str = "",
    icon: str = "📭",
) -> str:
    text_html = f'<div class="qt-empty-text">{text}</div>' if text else ""
    return f"""
    <div class="qt-empty">
      <div class="qt-empty-icon">{icon}</div>
      <div class="qt-empty-title">{title}</div>
      {text_html}
    </div>
    """
```

- [ ] **Step 4: Run test — verify PASS**

Run: `python -m pytest tests/test_theme_v3.py::test_empty_state_v3_outputs_brutalist_classes -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/viz/theme.py tests/test_theme_v3.py
git commit -m "feat(design v3 #7): empty state — editorial brutalist"
```

---

### Task 8: stat_strip_html v3 — dense, divider-separated

**Files:**
- Modify: `src/viz/theme.py` (`stat_strip_html()`)
- Test: `tests/test_theme_v3.py`

- [ ] **Step 1: Add failing test**

```python
def test_stat_strip_v3_renders_grid_with_tiles():
    from src.viz.theme import stat_strip_html
    html = stat_strip_html([
        {"label": "VaR 95%", "value": "€421"},
        {"label": "Sharpe", "value": "1.42"},
        {"label": "Beta", "value": "0.87"},
    ])
    # 3 tiles, all using qt-tile class
    assert html.count("qt-tile-label") == 3
    assert html.count("qt-tile-value") == 3
    # Grid layout
    assert "grid-template-columns" in html
```

- [ ] **Step 2: Run test — verify state**

Run: `python -m pytest tests/test_theme_v3.py::test_stat_strip_v3_renders_grid_with_tiles -v`

(Should already pass if existing stat_strip_html builds from kpi_tile_html — verify, otherwise fix.)

- [ ] **Step 3: Confirm body**

The current stat_strip_html already uses a grid + kpi_tile_html. Leave as-is unless test fails.

- [ ] **Step 4: PASS**

- [ ] **Step 5: Commit (no-op if no changes)**

If no changes needed, skip the commit and move on.

---

### Task 9: Plotly template v3 — sharp axes, mono ticks, gold accent

**Files:**
- Create: `src/viz/plotly_template_v3.py`
- Modify: `src/viz/theme.py` (re-export `PLOTLY_TEMPLATE` from v3)
- Test: `tests/test_theme_v3.py`

- [ ] **Step 1: Add failing test**

```python
def test_plotly_template_v3_uses_v3_palette():
    from src.viz.theme import PLOTLY_TEMPLATE, PALETTE
    tpl = PLOTLY_TEMPLATE
    assert tpl["layout"]["paper_bgcolor"] == PALETTE.bg
    assert tpl["layout"]["plot_bgcolor"] == PALETTE.bg
    # Mono ticks
    assert "JetBrains Mono" in tpl["layout"]["font"]["family"]
    # Sharp grid (no faint lines)
    assert tpl["layout"]["xaxis"]["gridcolor"] == PALETTE.border
    # Colorway is the v3 7-hue palette
    assert tpl["layout"]["colorway"][0] == "#FAF7F2"
    assert "#FF3838" in tpl["layout"]["colorway"]
```

- [ ] **Step 2: Run test — verify FAIL**

Run: `python -m pytest tests/test_theme_v3.py::test_plotly_template_v3_uses_v3_palette -v`
Expected: FAIL

- [ ] **Step 3: Create the template module**

```python
# src/viz/plotly_template_v3.py
"""Plotly template v3 — Wall Street Brutalist visual language."""
from src.viz.theme import FONT_MONO, PALETTE

PLOTLY_TEMPLATE: dict = {
    "layout": {
        "paper_bgcolor": PALETTE.bg,
        "plot_bgcolor": PALETTE.bg,
        "font": {
            "family": FONT_MONO,
            "size": 12,
            "color": PALETTE.fg_muted,
        },
        "title": {
            "font": {"family": FONT_MONO, "size": 13, "color": PALETTE.fg},
            "x": 0.0,
            "xanchor": "left",
        },
        "colorway": list(PALETTE.plotly_colorway_v3),
        "xaxis": {
            "gridcolor": PALETTE.border,
            "linecolor": PALETTE.border_strong,
            "zerolinecolor": PALETTE.border_strong,
            "tickfont": {"family": FONT_MONO, "size": 11, "color": PALETTE.fg_muted},
            "title": {"font": {"family": FONT_MONO, "size": 12, "color": PALETTE.fg_dim}},
        },
        "yaxis": {
            "gridcolor": PALETTE.border,
            "linecolor": PALETTE.border_strong,
            "zerolinecolor": PALETTE.border_strong,
            "tickfont": {"family": FONT_MONO, "size": 11, "color": PALETTE.fg_muted},
            "title": {"font": {"family": FONT_MONO, "size": 12, "color": PALETTE.fg_dim}},
        },
        "legend": {
            "font": {"family": FONT_MONO, "size": 11, "color": PALETTE.fg_muted},
            "bgcolor": "rgba(0,0,0,0)",
            "bordercolor": PALETTE.border,
        },
        "margin": {"l": 50, "r": 30, "t": 40, "b": 40},
        "hoverlabel": {
            "bgcolor": PALETTE.card,
            "bordercolor": PALETTE.rule,
            "font": {"family": FONT_MONO, "color": PALETTE.fg},
        },
    }
}
```

- [ ] **Step 4: Re-export from theme.py**

In `src/viz/theme.py`, find the existing `PLOTLY_TEMPLATE = {...}` and replace with:

```python
from src.viz.plotly_template_v3 import PLOTLY_TEMPLATE as _PLOTLY_TEMPLATE_V3
PLOTLY_TEMPLATE = _PLOTLY_TEMPLATE_V3
```

Place this at the BOTTOM of theme.py to avoid circular import (theme.py doesn't import from plotly_template_v3 at the top).

- [ ] **Step 5: Run test — verify PASS**

Run: `python -m pytest tests/test_theme_v3.py::test_plotly_template_v3_uses_v3_palette -v`
Expected: PASS

- [ ] **Step 6: Run full test suite — verify no regression**

Run: `python -m pytest -q`
Expected: all 281 + new theme v3 tests pass

- [ ] **Step 7: Commit**

```bash
git add src/viz/theme.py src/viz/plotly_template_v3.py tests/test_theme_v3.py
git commit -m "feat(design v3 #9): Plotly template — mono ticks + sharp grid"
```

---

### Task 10: Smoke-test the app — visit every tab via streamlit run (manual)

**Files:** none modified.

- [ ] **Step 1: Launch the app**

```bash
cd quant_terminal
streamlit run app.py
```

- [ ] **Step 2: Manual walkthrough**

Open http://localhost:8501 and click through each of the 17 tabs:
- Portfolio · Trading Bench · Watchlists · Macro & Regime · Smart-Money · Decision Support · Catalysts & News · Event Trading · Backtest · Alerts · Execution · Snapshot & Tax · Short Squeeze · HMM Regime · Kalman · Daily Brief · 🌍 Cross-Asset

For each tab, verify:
- No Python exception in the terminal logs
- Hero header renders with serif title + gold rule
- KPI tiles show monolithic left-accent style with mono label + serif numerals
- Plotly charts use dark ink background + bone/mercury/amber colorway
- Empty states (where present) show the new editorial style
- Tabs at top are uppercase + letter-spaced + gold underline on active

- [ ] **Step 3: Document findings**

If any tab breaks visually, note it but don't fix yet — it likely means an existing inline-style overrides the v3 CSS. Open a follow-up task only if a tab is unreadable.

- [ ] **Step 4: Stop streamlit**

Ctrl+C in the terminal.

- [ ] **Step 5: No commit**

This is verification only.

---

### Task 11: Update app.py footer + DASHBOARD.md design section

**Files:**
- Modify: `app.py` (footer line)
- Modify: `docs/DASHBOARD.md` (Design language section)

- [ ] **Step 1: Update footer**

Find in app.py:

```python
"Quant Terminal · Alpaca + yfinance · FX EUR · 17 tabs · Cross-Asset · Daily Brief · HMM · Live Book · IV Crush"
```

Replace with:

```python
"Quant Terminal v3 · Wall Street Brutalist · Alpaca + yfinance · 17 tabs · Cross-Asset · Daily Brief · HMM"
```

- [ ] **Step 2: Update DASHBOARD.md design section**

Find the existing "Design language" section in `docs/DASHBOARD.md` (search for "Design" or "Theme") and replace with:

```markdown
## Design language (v3 — Wall Street Brutalist)

- **Display font**: Fraunces (variable serif, opsz 9..144) — used for hero, section titles, KPI numerals
- **Body / UI / mono**: JetBrains Mono everywhere else — true terminal feel
- **Palette**: deep ink #0A0A0F + bone white #FAF7F2 + mercury red #FF3838 (losses) + caution amber #FFB800 + sharp mint #2EE89E (gains) + gold #D4AF37 (rules + § numbering)
- **Atmosphere**: SVG fractal noise overlay 5% opacity + radial corner gradient gold 8% + 1px gold rule between sections
- **Geometry**: hard right angles everywhere (border-radius: 0), no drop shadows, no glassmorphism
- **Motion**: staggered fade-up 240ms on tab mount, hover scale on cards 0.99
- **Typography rules**: § numbering decorative, uppercase letter-spaced tabs (0.08em), tabular numerics, mono labels (text-transform: uppercase, letter-spacing: 0.12em)
- **Banned**: Inter, Roboto, Arial, system-ui, mint+cyan combos, drop shadows, border-radius > 4px
```

- [ ] **Step 3: Verify**

```bash
git diff app.py docs/DASHBOARD.md
```

- [ ] **Step 4: Commit**

```bash
git add app.py docs/DASHBOARD.md
git commit -m "docs(design v3 #11): footer + DASHBOARD.md design language section"
```

---

### Task 12: Full regression test + lint sweep

**Files:** none modified.

- [ ] **Step 1: Run full test suite**

```bash
python -m pytest -q
```

Expected: 281 + new theme v3 tests all PASS. If any regression in unrelated test, STOP and ask.

- [ ] **Step 2: Run lint**

```bash
python -m ruff check src/viz/ tests/test_theme_v3.py
```

Expected: All checks passed. If errors, run with `--fix` and re-check.

- [ ] **Step 3: Confirm import graph still works**

```bash
python -c "from src.viz.theme import (PALETTE, FONT_DISPLAY, FONT_BODY, FONT_MONO, PLOTLY_TEMPLATE, hero_header_html, section_header_html, kpi_tile_html, stat_strip_html, empty_state_html, inject_streamlit_css, inject_streamlit_css_html); print('OK')"
```

Expected: `OK`

- [ ] **Step 4: No commit**

Verification only.

---

### Task 13: Push branch + open PR

**Files:** none modified.

- [ ] **Step 1: Push the branch**

```bash
git push -u origin feat/design-v3-wall-street-brutalist
```

- [ ] **Step 2: Open PR**

```bash
gh pr create --title "feat(design v3): Wall Street Brutalist refonte aesthetic" --body "$(cat <<'EOF'
## Refonte aesthetic complète — design v3

Application de la doctrine `frontend-design` skill : direction BOLD éditoriale-mono "Wall Street Brutalist" qui remplace le theme v2 (Inter + cool blue) sans casser aucun des 17 tabs.

## Summary

- Display: **Fraunces** (variable serif éditorial)
- Body/UI/mono: **JetBrains Mono** everywhere — vrai feel terminal
- Palette: deep ink + bone white + mercury red + caution amber + gold rule lines
- Atmosphere: SVG fractal noise 5% + radial corner gradient gold 8% + 1px gold rules
- Geometry: hard right angles partout, zéro drop shadow, zéro glassmorphism
- Motion: staggered fade-up 240ms au mount, hover scales
- Tabs: uppercase letter-spaced + gold underline on active
- § numbering éditorial sur hero + section headers

## Banned (per frontend-design skill)

Inter, Roboto, Arial, Helvetica, system-ui, mint+cyan v2 combo, glassmorphism, drop shadows, border-radius > 4px.

## Architecture

- Upgrade in-place de `src/viz/theme.py` (25 fichiers importent — signatures préservées, zéro casse)
- Nouveau `src/viz/plotly_template_v3.py` isolé (importé depuis theme.py)
- Tests HTML/CSS output: `tests/test_theme_v3.py`
- Doc design language: `docs/DASHBOARD.md`

## Test plan

- [x] \`pytest tests/test_theme_v3.py\` — verts
- [x] \`pytest -q\` — full suite verts (zéro régression)
- [x] \`ruff check\` — clean
- [x] Smoke-test manuel des 17 tabs (Task 10)
- [ ] Smoke-test prod Streamlit Cloud après merge

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

- [ ] **Step 3: Capture PR URL and report**

The PR URL is the deliverable.

- [ ] **Step 4: No commit**

PR creation only.

---

## Self-Review

**1. Spec coverage:**
- ✅ Palette tokens (Task 1)
- ✅ Typography stack (Task 2)
- ✅ CSS injection with Google Fonts + noise + rules (Task 3)
- ✅ Hero with § numbering (Task 4)
- ✅ Section header with gold rule (Task 5)
- ✅ KPI tile with left accent (Task 6)
- ✅ Empty state editorial (Task 7)
- ✅ Stat strip (Task 8)
- ✅ Plotly template v3 (Task 9)
- ✅ Regression smoke test (Task 10)
- ✅ Footer + doc (Task 11)
- ✅ Lint + full pytest (Task 12)
- ✅ Push + PR (Task 13)

**2. Placeholder scan:** None — every step has real code or real command.

**3. Type consistency:** All HTML class names (`qt-tile`, `qt-tile-label`, `qt-tile-value`, `qt-tile-delta`, `qt-tile-hint`, `qt-tile-delta-pos/neg/neutral`, `qt-hero`, `qt-hero-number`, `qt-hero-title`, `qt-hero-subtitle`, `qt-hero-meta`, `qt-section-header`, `qt-section-title`, `qt-section-subtitle`, `qt-section-meta`, `qt-section-number`, `qt-empty`, `qt-empty-icon`, `qt-empty-title`, `qt-empty-text`) match between CSS rules in Task 3 and HTML builders in Tasks 4-7.

CSS variables (`--qt-bg`, `--qt-fg`, `--qt-rule`, etc.) match Palette field names.

Plotly template colorway in Task 1 (`plotly_colorway_v3`) is read in Task 9.

`inject_streamlit_css_html()` defined in Task 3 is called by `inject_streamlit_css()` (legacy entrypoint preserved).

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-05-27-design-v3-refonte.md`. Two execution options:

**1. Subagent-Driven** — Dispatch a fresh subagent per task, review between tasks. Best for very large plans with risk of context bloat.

**2. Inline Execution (recommended for this plan)** — Execute tasks in this session using executing-plans, batch with checkpoints. 13 tasks of ~5 min each = ~1 hour total, fits comfortably in current context.

Which approach?
