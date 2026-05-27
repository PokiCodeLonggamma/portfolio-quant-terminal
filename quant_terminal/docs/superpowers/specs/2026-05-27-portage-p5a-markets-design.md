# Portage Phase 5a — Markets cluster (5 routes) Design Spec

**Status:** Approved 2026-05-27 (2 brainstorm Q answered).

## Goal

Câbler les 5 routes du domaine MARKETS sur les vraies données live de l'API FastAPI :
- `/markets/cross-asset` — heatmap + flagship contracts + drilldown ticker
- `/markets/macro` — VIX/DXY/US10Y/SPY-200d + correlation matrix
- `/markets/hmm` — 3-state HMM regime pour SPY/QQQ/IWM
- `/markets/squeeze` — top-20 short squeeze candidates
- `/markets/catalysts` — upcoming events + news pulse

+ Une nouvelle page `/ticker/{logical}` plein écran (TV chart + ticker info) accessible depuis tous les tableaux.

## Strategic decisions

| Axe | Choix |
|---|---|
| /api/regime/macro | À CRÉER (MacroService + endpoint + tests) — pas en placeholder |
| Drilldown ticker | Page dédiée `/ticker/{logical}` plein écran avec TV iframe |
| Charts utilisés | Cross-asset heatmap = HTML table styled ; Macro corr = ECharts heatmap ; HMM probabilities = HTML bar ; Squeeze = HTML table ; Catalysts = HTML list |
| Auth | Toutes ces nouvelles routes sont déjà gated par middleware.ts (cookie qt_auth) — pas de gate côté backend en P5a (Streamlit cohabitation) |

## Backend additions

### `src/services/macro_service.py` (NEW)
- Wraps `src/macro/regime.py` (existing) + new yfinance helpers for VIX term + DXY + US10Y
- Returns `MacroRegimeSnapshot` (already in services/schemas.py)
- Dependency-injected `quote_fetch_fn` for testability

### `api/routes/macro.py` (NEW)
- `GET /api/regime/macro` → MacroRegimeSnapshot
- `@cached(ttl_seconds=300, prefix="regime.macro")`
- Mounted in api/main.py

### Tests
- `tests/test_services_macro.py` (4-5 tests)
- `tests/test_api_macro.py` (2-3 tests)

## Frontend — 5 page wiring + 1 new route

### `/markets/cross-asset/page.tsx`
- Server component fetches `/api/cross-asset/heatmap` at request time (revalidate 60s)
- Render:
  - StatStrip: top-3 gainers + top-3 losers as KPI tiles
  - DataTable (HTML, no lib): all rows sortable by 1d %, with click handlers → `/ticker/{logical}`
  - Color-coded 1d% / 5d% cells (mint/mercury)

### `/markets/macro/page.tsx`
- Server component fetches `/api/regime/macro` (revalidate 300s)
- Render:
  - StatStrip: VIX level + term structure pill + DXY + US10Y
  - "SPY above 200d" status pill
  - Lazy ECharts correlation matrix (Phase 5a delivers KPIs, matrix in 5b if time)

### `/markets/hmm/page.tsx`
- Client component (3 parallel TanStack Query calls SPY/QQQ/IWM)
- Render 3-column grid, each column = ticker:
  - Current regime label as big KPI
  - Probabilities as horizontal bar chart (HTML, color-coded by label)
  - sample_size + asof as hint

### `/markets/squeeze/page.tsx`
- Server fetch `/api/scanners/squeeze?limit=20` (revalidate 600s)
- Render DataTable sortable: ticker, short_pct_float, days_to_cover, cost_to_borrow, utilization, on_sho flag, composite_score
- Composite score visualized as inline bar
- Click ticker → `/ticker/{logical}`

### `/markets/catalysts/page.tsx`
- Server fetches both `/api/catalysts/upcoming?horizon_days=30` AND `/api/news/latest`
- Render 2-column layout:
  - Left: chronological event list (Date · Ticker · Category · Title · EPS estimate)
  - Right: news feed (sentiment-colored chip · ticker · title · source · time ago)

### `/ticker/{logical}/page.tsx` (NEW route, outside (dashboard) group? or inside?)
- Inside (dashboard) for auth gating
- Resolves `logical` via `/api/universe/contracts/{logical}` (fetched server-side)
- Renders:
  - SectionHeader with ticker + name + exchange + currency + mult
  - Large TradingChart iframe (TV widget — port of tv_chart.py)
  - Back link to referrer (or default `/markets/cross-asset`)

## Components to add

- `web/components/widgets/DataTable.tsx` — HTML table styled brutalist, sortable, click handler
- `web/components/widgets/TickerLink.tsx` — `<Link href="/ticker/{logical}">` with hover style
- `web/components/charts/TradingViewWidget.tsx` — TV iframe wrapper (port of src/viz/tv_chart.py)

## Out of scope (for P5b / later)

- Cross-asset: per-asset-class deep-dive (separate page) — flagship grid covers main UX
- Macro: correlation matrix heatmap if time-constrained (KPIs are enough for P5a)
- HMM: transition matrix viz (only label + probs in P5a)
- Squeeze: detailed drilldown per ticker (just the table + ticker page link)
- Catalysts: filtering by ticker / category (just chronological list)
- Ticker page: GEX / options / IV (those live in /trading/bench — P5b)

## Tests

- Backend: pytest test_services_macro.py + test_api_macro.py (~7 tests)
- Frontend: Vitest snapshots for DataTable, TickerLink, TradingViewWidget (~5 tests)
- Manual smoke: 5 pages + /ticker/ES render with live data

## Risk register

| Risk | Mitigation |
|---|---|
| `/api/regime/macro` requires yfinance calls (slow first hit) | Cached 5min via @cached |
| HMM endpoint takes ~5s on cold cache | Already cached 1h in P3 |
| Squeeze data may be empty if SHO refresh hasn't run | Show EmptyState with refresh button |
| TV iframe blocked by CSP / X-Frame-Options | Set Next config to allow `*.tradingview.com` |
| 19-route nav links break for routes still using PlaceholderPanel | They keep working (no behavior change) |
