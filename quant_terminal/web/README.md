# Quant Terminal — Next.js frontend

Phase 4 of the Streamlit → Next.js portage. See
[`docs/superpowers/specs/2026-05-27-portage-p4-nextjs-shell-design.md`](../docs/superpowers/specs/2026-05-27-portage-p4-nextjs-shell-design.md)
for the design spec.

## Stack

- **Next.js 15** (App Router, RSC, Turbopack)
- **React 19** + **TypeScript 5**
- **Tailwind CSS v4** (CSS-first config in `styles/globals.css`)
- **TanStack Query 5** — data fetching
- **Zustand 5** — client state (UI, selection, prices)
- **Radix UI + shadcn-style primitives** — accessible base components
- **lightweight-charts 5** — candlesticks
- **react-plotly.js** — analytics charts (lazy-loaded)
- **echarts-for-react** — 3D vol surface + GEX heatmap (lazy-loaded)
- **Vitest + RTL** — component tests
- **bcrypt + python-jose** (backend) — JWT auth via HttpOnly cookie

## Design language

**Wall Street Brutalist** — Fraunces (variable serif display) + JetBrains Mono
(body/UI/numerics). Deep ink + bone white + gold rule lines + mercury red +
caution amber + sharp mint. Hard right angles, SVG noise atmosphere, editorial
§ numbering. Ported from `src/viz/theme.py`.

## Routes (19 + 1 login)

- `/` — Home (KPI strip + placeholder grid)
- `/login` — Auth gate
- **MARKETS** (5): `/markets/{cross-asset,macro,hmm,squeeze,catalysts}`
- **PORTFOLIO** (4): `/portfolio/{holdings,greeks,snapshot,tax}`
- **TRADING** (3): `/trading/{bench,watchlists,execution}`
- **DECISION** (4): `/decision/{conviction,smart-money,daily-brief,alerts}`
- **LAB** (3): `/lab/{backtest,event-trading,kalman}`

Every dashboard route is auth-gated by `middleware.ts`. All pages
currently render `PlaceholderPanel` cards — real data hookup happens
**Phase 5** (tab-by-tab migration).

## Run locally

### 1. Backend (FastAPI + Redis)

```bash
# In another terminal — the project root
cd ..
# Start Redis (docker-compose pre-configured)
docker compose -f docker-compose.dev.yml up -d redis
# Install deps + start the API
pip install -e ".[api]"
uvicorn api.main:app --reload
# → http://localhost:8000/docs
```

### 2. Set up admin credentials (first time only)

```bash
# Generate a bcrypt hash for your password
python scripts/hash_password.py
# Paste the output into .env (root):
#   QT_ADMIN_EMAIL=you@example.com
#   QT_ADMIN_PASSWORD_HASH=$2b$12$...
#   JWT_SECRET=<random 32+ byte string>
```

### 3. Frontend (Next.js)

```bash
cd web
npm install
npm run dev
# → http://localhost:3000 (redirects to /login)
```

After login you land on `/` with the full sidebar + 19 routes navigable.

## Commands

| Command | Description |
|---|---|
| `npm run dev` | Dev server with Turbopack hot-reload |
| `npm run build` | Production build (validates all 22 routes) |
| `npm run start` | Run the production build |
| `npm run typecheck` | tsc --noEmit |
| `npm run test` | Vitest (component + unit tests) |
| `npm run test:watch` | Vitest watch mode |
| `npm run lint` | Next lint |

## Environment

| Var | Default | Description |
|---|---|---|
| `NEXT_PUBLIC_API_BASE` | `""` (proxy via Next rewrites) | Render URL in prod (`https://quant-terminal-api.onrender.com`) |

Backend env vars: see root [`.env.example`](../.env.example).
