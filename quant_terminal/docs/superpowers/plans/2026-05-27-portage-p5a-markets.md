# Portage P5a — Markets cluster Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans.

**Goal:** Wire 5 MARKETS routes + 1 /ticker/{logical} route on the live API. See `docs/superpowers/specs/2026-05-27-portage-p5a-markets-design.md`.

## Tasks

### Backend — Macro endpoint
- [ ] **B1** Create `src/services/macro_service.py` (MacroService + dependency-injected yfinance fetcher)
- [ ] **B2** Write `tests/test_services_macro.py` (4 tests: snapshot OK, empty fallback, VIX term contango/backwardation, no-streamlit assertion)
- [ ] **B3** Create `api/routes/macro.py` with `GET /api/regime/macro` @cached(300s)
- [ ] **B4** Mount in api/main.py, write `tests/test_api_macro.py` (2 tests: 200 + cache hit)

### Frontend — Components
- [ ] **F1** Create `web/components/widgets/DataTable.tsx` (HTML table, sortable, click handler)
- [ ] **F2** Create `web/components/widgets/TickerLink.tsx` (Link to /ticker/{logical})
- [ ] **F3** Create `web/components/charts/TradingViewWidget.tsx` (TV iframe wrapper)

### Frontend — Pages
- [ ] **F4** Replace `web/app/(dashboard)/markets/cross-asset/page.tsx` (heatmap + flagship grid)
- [ ] **F5** Replace `web/app/(dashboard)/markets/macro/page.tsx` (4 KPI tiles + status pills)
- [ ] **F6** Replace `web/app/(dashboard)/markets/hmm/page.tsx` (3-column grid SPY/QQQ/IWM, TanStack Query)
- [ ] **F7** Replace `web/app/(dashboard)/markets/squeeze/page.tsx` (sortable top-20 table)
- [ ] **F8** Replace `web/app/(dashboard)/markets/catalysts/page.tsx` (2-col: events + news)
- [ ] **F9** Create `web/app/(dashboard)/ticker/[logical]/page.tsx` (TV chart + ticker meta)

### Frontend — API helpers
- [ ] **F10** Add typed clients to `web/lib/api.ts`:
  - `getHeatmap()`, `getCatalysts(horizon)`, `getNews(limit)`, `getSqueeze(limit)`, `getMacro()`, `getHmm(ticker, n_states)`, `getContract(logical)`

### Tests
- [ ] **T1** `web/tests/DataTable.test.tsx` (3 tests: render rows, sort by column, click row)
- [ ] **T2** `web/tests/TradingViewWidget.test.tsx` (1 test: iframe src contains TV symbol)

### Finishing
- [ ] **L1** `pytest -q` → green
- [ ] **L2** `ruff check` → clean
- [ ] **L3** `cd web && npx tsc --noEmit && npx next build && npx vitest run` → clean
- [ ] **L4** Manual smoke: navigate to all 5 markets routes + /ticker/ES
- [ ] **L5** Commit + push + PR (base = feat/portage-phase-4-nextjs-shell)
