# Portage Phase 4 — Next.js Shell Design Spec

**Status:** Approved 2026-05-27 (sections 1+2 explicitly approved, sections 3+4 batched per user request "ne me demande pas de validation à chaque fois").

## Goal

Livrer un Next.js shell **visuel complet** : 17 routes câblées avec layout 4-panel Bloomberg-style, auth fonctionnelle (login + middleware), composants réutilisables, state setup (TanStack Query + Zustand). Les panneaux internes affichent des placeholders annotés "wired in Phase 5". Le portage des données (page-par-page) est l'objet de Phase 5.

## Strategic decisions (validated in brainstorm)

| Axe | Choix |
|---|---|
| **Scope** | Shell visuel only — composants + routing + auth + state setup, panneaux en placeholders |
| **Navigation** | 17 routes (1 page par tab Streamlit), sidebar fixe groupée par 5 domaines |
| **Auth** | Login form + JWT HttpOnly cookie + bcrypt + ENV vars |
| **Sidebar** | 5 sections collapsibles (MARKETS / PORTFOLIO / TRADING / DECISION / LAB) |
| **Charts** | lightweight-charts (candles) + react-plotly.js (analytics) + ECharts (3D / gros viz) |
| **Responsive** | Desktop-first 1440px+, dégradation gracieuse mobile (vraie PWA = P6) |
| **Tests** | Vitest + RTL + 1 Playwright spec smoke |

## Architecture

```
web/
├── app/
│   ├── (auth)/login/page.tsx
│   ├── (dashboard)/
│   │   ├── layout.tsx              # AppShell wrapper
│   │   ├── page.tsx                # / (home)
│   │   ├── markets/{cross-asset,macro,hmm,squeeze,catalysts}/page.tsx  # 5 routes
│   │   ├── portfolio/{holdings,greeks,snapshot,tax}/page.tsx           # 4 routes
│   │   ├── trading/{bench,watchlists,execution}/page.tsx               # 3 routes
│   │   ├── decision/{conviction,smart-money,daily-brief,alerts}/page.tsx  # 4 routes
│   │   └── lab/{backtest,event-trading,kalman}/page.tsx                # 3 routes
│   ├── layout.tsx                  # root (existant)
│   └── globals.css                 # tokens v3 (existant)
├── components/
│   ├── ui/                         # shadcn primitives
│   ├── shell/                      # AppShell, Sidebar, TopBar, NavSection
│   ├── widgets/                    # KpiTile, SectionHeader, EmptyState, LivePill, PlaceholderPanel
│   └── charts/                     # TradingChart, PlotlyChart, EChart (lazy)
├── lib/
│   ├── api.ts                      # (existant) typed REST
│   ├── auth.ts                     # useAuth, useLogin, useLogout
│   ├── format.ts                   # fmt_eur, fmt_pct
│   └── nav.ts                      # NAV_SECTIONS config (5 groups × N routes)
├── store/
│   ├── auth.ts
│   ├── selection.ts                # currentTicker
│   ├── ui.ts                       # sidebarCollapsed
│   └── prices.ts                   # WS live ticks (ring buffer 100/ticker)
├── middleware.ts                   # Auth check on (dashboard)/*
└── tests/                          # Vitest + 1 Playwright smoke
```

## Backend additions (FastAPI)

3 nouveaux endpoints + 1 dependency :

- `api/auth.py` : `require_auth` FastAPI dependency (reads cookie, validates JWT, raises 401)
- `api/routes/auth.py` :
  - `POST /api/auth/login` — body `{email, password}` → set HttpOnly cookie + returns `{ok, user}`
  - `GET /api/auth/me` → `{email, exp}` (requires cookie)
  - `POST /api/auth/logout` → clear cookie

Storage: ENV vars `QT_ADMIN_EMAIL`, `QT_ADMIN_PASSWORD_HASH` (bcrypt), `JWT_SECRET`.

**Existing endpoints are NOT auth-gated in P4** — added incrementally in P5 as pages are wired (avoids breaking Streamlit cohabitation).

Helper script `scripts/hash_password.py` to generate a bcrypt hash for a given password.

## Tests strategy

- **Backend (pytest)** : 3 new tests for `/api/auth/*` (login OK, login wrong password 401, /me with cookie, /me without cookie 401)
- **Frontend (Vitest + RTL)** : snapshot tests for KpiTile, SectionHeader, EmptyState, LoginForm
- **E2E (Playwright, 1 smoke)** : visit /, get redirected to /login, submit creds (mocked via MSW), land on /

## Out of scope (deferred to P5+)

- Real page data (every page is a placeholder showing "Wired in Phase 5 — endpoint: GET /api/…")
- Cmd+K command palette (bonus if time)
- Mobile-specific layout (P6)
- WebSocket subscriptions on /trading/bench (P5)
- Storybook / visual regression
- DEGIRO upload UI (P5)
