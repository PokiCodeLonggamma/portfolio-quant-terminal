# Quant Terminal — Dashboard guide

Institutional cross-asset cockpit. Streamlit app, 17 tabs, ~25k LoC, 295 tests.

## Design language (v3 — Wall Street Brutalist)

The visual language was chosen per the `frontend-design` skill doctrine: pick a
BOLD direction and execute it with precision. This terminal takes its cues from
Wall Street Journal print typography, Bloomberg terminal density, and brutalist
geometric precision.

### Typography
- **Display** : [Fraunces](https://fonts.google.com/specimen/Fraunces)
  — variable serif, opsz 9..144, weights 300/400/700/900. Used for the hero
  title, section titles, KPI numerals.
- **Body / UI / mono** : [JetBrains Mono](https://www.jetbrains.com/lp/mono/)
  EVERYWHERE else — true terminal feel, mono numerics by default, perfect for
  tables and dense data display.
- **Banned** (per doctrine) : Inter, Roboto, Arial, Helvetica, system-ui.

### Palette
| Token | Hex | Usage |
|---|---|---|
| `bg` | `#0A0A0F` | deep oil ink — page background |
| `bg_elev` | `#14141C` | sidebar, hero one elevation up |
| `card` | `#1A1A24` | cards, panels |
| `border` | `#2A2A38` | thin rules between rows |
| `rule` | `#D4AF37` | **gold** — § numbers, decorative dividers, accent borders |
| `fg` | `#FAF7F2` | bone white (warm) — primary text |
| `fg_muted` | `#B8B5AC` | secondary text |
| `accent_pos` | `#2EE89E` | sharp mint — P&L positive |
| `accent_neg` | `#FF3838` | mercury red — losses, warnings |
| `accent_warn` | `#FFB800` | caution amber — used SPARINGLY |

### Atmosphere
- SVG fractal-noise overlay 5% opacity (subtle paper grain across the whole app)
- Radial corner gradients : gold top-right 8%, mint bottom-left 4%
- Thin gold 1px rule lines between hero/section blocks
- Tabular numerics by default (`font-variant-numeric: tabular-nums`)

### Geometry
- Hard right angles everywhere (`border-radius: 0`)
- 3px left accent on KPI tiles (gold, switches to mint on hover)
- Uppercase letter-spaced (0.08em) on tabs, buttons, labels
- Tabs: gold underline on active, no rounded edges, mono 0.78rem

### Motion
- Staggered fade-up 240ms on hero / section / tile mount
- `tile:nth-child(N)` delays 30/60/90/120/150ms for cascading reveals
- Hover transitions on cards (120ms ease) : background lift + border accent

### Editorial flourishes
- `§` numbering on hero blocks (e.g. "§ 01 — Cross-Asset Universe")
- Drop-cap-style section numbers in Fraunces opsz 144 weight 900
- ASCII-like rule lines (`<hr class="qt-section-divider">`)
- Footer + captions in uppercase letter-spaced mono

### File map
- `src/viz/theme.py` — palette, fonts, CSS, HTML builders, formatters
- `src/viz/plotly_template_v3.py` — Plotly template (sharp grid, mono ticks, v3 colorway)
- `tests/test_theme_v3.py` — HTML/CSS output regressions

The HTML builders preserve their v2 signatures, so the 25 dashboards that
import from `src.viz.theme` keep working unchanged.

## Architecture (high-level)

```
quant_terminal/
├── app.py                         # 17 tabs (Portfolio, Trading Bench, …)
├── config/                        # 18 YAML config files
│   ├── universe_cross_asset.yaml  # CDC §1 — 99 contracts × 10 classes
│   └── …
├── src/
│   ├── universe/cross_asset.py    # CDC §1 — loader + symbol resolver
│   ├── viz/
│   │   ├── theme.py               # design tokens v3
│   │   ├── plotly_template_v3.py  # plotly v3 template
│   │   └── tv_chart.py            # TradingView candlestick drilldown
│   ├── decision/cross_asset_dashboard.py  # CDC §1 — 🌍 tab
│   └── …
└── tests/                         # 295 tests
```

## Tabs (17)

1. 📈 Portfolio — DEGIRO upload + Greeks + risk + tax
2. 🎯 Trading Bench — chains, GEX, IV analytics, trade ticket
3. 🛰️ Watchlists — private + trading + surveillance + bookmarks
4. 🌐 Macro & Regime — regimes, correlations, liquidity
5. 💸 Smart-Money & Fundamentals — 13F, insiders, ratings
6. 🧠 Decision Support — conviction matrix, hedge cost, journal
7. 📅 Catalysts & News — earnings, FOMC, analyst ratings, news pulse
8. 🎬 Event Trading — pre-event wizard, earnings simulator
9. 📒 Backtest — strategy backtests
10. 🔔 Alerts — triggers, channels, history
11. 📡 Execution — Alpaca paper / live (latch)
12. 📊 Snapshot & Tax — daily snapshots, FIFO lots, 2074
13. 🔥 Short Squeeze — SHO list + 4-pillar deep scan
14. 🌀 HMM Regime — 3-state vol regime
15. 🤖 Kalman — meta-labeling Phase 3
16. ☀️ Daily Brief — LLM morning summary
17. 🌍 Cross-Asset — CDC §1 universe + TradingView drilldown
