# Portage P4 — Next.js Shell Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement task-by-task. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Ship the Next.js shell visuel complet — 17 routes, sidebar 5 groups, auth flow, components, state setup. Panels show placeholders. Backend gets 3 auth endpoints.

**Architecture:** See `docs/superpowers/specs/2026-05-27-portage-p4-nextjs-shell-design.md`.

**Tech Stack:** Next.js 15 App Router · TypeScript 5 · Tailwind 4 · shadcn/ui (radix) · TanStack Query 5 · Zustand 5 · lightweight-charts 5 · react-plotly.js · echarts-for-react · Vitest + RTL · Playwright (1 smoke).

---

## Tasks (executed inline; checkboxes track progress)

### Backend — auth (FastAPI)
- [ ] **B1** Create `api/auth.py` with `require_auth` dependency, JWT encode/decode helpers, settings reader (QT_ADMIN_EMAIL, QT_ADMIN_PASSWORD_HASH, JWT_SECRET)
- [ ] **B2** Create `api/routes/auth.py` with `POST /api/auth/login`, `GET /api/auth/me`, `POST /api/auth/logout`. Mount in `api/main.py`.
- [ ] **B3** Create `scripts/hash_password.py` helper
- [ ] **B4** Write `tests/test_api_auth.py` covering 4 scenarios. Run pytest, ensure green.

### Frontend — scaffold + shadcn primitives
- [ ] **F1** Install deps: tanstack/react-query, zustand (already), @radix-ui/*, lightweight-charts (already), react-plotly.js plotly.js, echarts-for-react echarts, react-hook-form zod, msw vitest playwright @testing-library/react @testing-library/jest-dom @vitejs/plugin-react jsdom @types/node tanstack/react-table cmdk lucide-react
- [ ] **F2** Init `tailwind.config` if needed (Tailwind v4 = CSS-first), tweak `globals.css` to add component utility classes
- [ ] **F3** Drop in shadcn/ui-style primitives in `components/ui/` (button, card, input, label, dialog, sheet, tabs, select, popover, tooltip, command, separator, scroll-area, dropdown-menu, skeleton). Hand-written (not via shadcn CLI which is interactive) — each as a thin radix wrapper styled brutalist.

### Frontend — state + lib
- [ ] **F4** Create `lib/format.ts` (fmt_eur, fmt_pct, fmt_pct_color)
- [ ] **F5** Create `lib/auth.ts` (useAuth, useLogin, useLogout via TanStack Query)
- [ ] **F6** Create `lib/nav.ts` (NAV_SECTIONS config exporting 5 groups × N routes)
- [ ] **F7** Create `lib/query-client.ts` (singleton QueryClient with global defaults)
- [ ] **F8** Create `store/auth.ts`, `store/selection.ts`, `store/ui.ts`, `store/prices.ts` (Zustand stores)
- [ ] **F9** Update `lib/api.ts` to support cookie-based auth (credentials: "include")

### Frontend — shell components
- [ ] **F10** Create `components/shell/AppShell.tsx` (sidebar + topbar + main grid)
- [ ] **F11** Create `components/shell/Sidebar.tsx` (5 collapsible NavSections)
- [ ] **F12** Create `components/shell/NavSection.tsx` (header + items)
- [ ] **F13** Create `components/shell/TopBar.tsx` (logo + asof + LivePill + user menu)
- [ ] **F14** Create `components/shell/Providers.tsx` (QueryClientProvider + Toaster + ErrorBoundary)

### Frontend — widget components
- [ ] **F15** Create `components/widgets/KpiTile.tsx`, `SectionHeader.tsx`, `StatStrip.tsx`, `EmptyState.tsx`, `LivePill.tsx`, `DataTable.tsx`, `PlaceholderPanel.tsx`

### Frontend — chart wrappers
- [ ] **F16** Create `components/charts/TradingChart.tsx` (lightweight-charts wrapper)
- [ ] **F17** Create `components/charts/PlotlyChart.tsx` (lazy dynamic import)
- [ ] **F18** Create `components/charts/EChart.tsx` (lazy dynamic import)

### Frontend — auth + middleware
- [ ] **F19** Create `middleware.ts` (redirect to /login if no cookie on /(dashboard)/*)
- [ ] **F20** Create `app/(auth)/layout.tsx` (minimal layout — no sidebar)
- [ ] **F21** Create `app/(auth)/login/page.tsx` (login form)

### Frontend — routes (17 + home)
- [ ] **F22** Move existing `app/page.tsx` → `app/(dashboard)/page.tsx` (home with KPI strip placeholders)
- [ ] **F23** Create `app/(dashboard)/layout.tsx` (wraps in AppShell)
- [ ] **F24** Create the 17 page.tsx files (each a PlaceholderPanel with the route's purpose + Phase 5 endpoint annotation):
  - markets: cross-asset, macro, hmm, squeeze, catalysts
  - portfolio: holdings, greeks, snapshot, tax
  - trading: bench, watchlists, execution
  - decision: conviction, smart-money, daily-brief, alerts
  - lab: backtest, event-trading, kalman

### Tests
- [ ] **T1** Configure Vitest (`vitest.config.ts`) + RTL + jsdom
- [ ] **T2** Component tests: KpiTile, SectionHeader, EmptyState, LoginForm renders + click handler
- [ ] **T3** Playwright config (1 spec): /login flow with MSW

### Finishing
- [ ] **L1** Ensure `next build` passes (typecheck + bundle)
- [ ] **L2** Update `web/README.md` with launch instructions
- [ ] **L3** Update `web/.env.example` with required vars
- [ ] **L4** Run pytest full sweep, ruff
- [ ] **L5** Commit, push, open PR

---

## Verification

After all tasks:

1. `python -m pytest -q` → ≥ 412 passed (408 + 4 new auth tests)
2. `python -m ruff check src/ api/ app.py tests/ --select F401,F811,F841,E711,E712` → clean
3. `cd web && npm run typecheck` → clean
4. `cd web && npm run build` → success, all 17+ routes prerendered (or marked dynamic if cookie-dependent)
5. `cd web && npx vitest run` → ≥ 4 component tests pass
6. Manual smoke: `uvicorn api.main:app --reload` + `cd web && npm run dev` → http://localhost:3000 redirects to /login → submit → land on / → click sidebar items → all 17 routes render their PlaceholderPanel
