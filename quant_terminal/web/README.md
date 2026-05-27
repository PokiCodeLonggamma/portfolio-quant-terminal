# Quant Terminal — Next.js frontend

Phase 0 of the Streamlit → Next.js portage. See
[`docs/superpowers/plans/2026-05-27-portage-streamlit-nextjs-fastapi.md`](../docs/superpowers/plans/2026-05-27-portage-streamlit-nextjs-fastapi.md)
for the master plan.

## Stack

- Next.js 15 (App Router, RSC, Turbopack)
- React 19
- TypeScript 5
- Tailwind CSS v4 (CSS-first config in `styles/globals.css`)
- TanStack Query 5 (data fetching, Phase 4+)
- Zustand 5 (client state, Phase 4+)
- lightweight-charts 5 (candlesticks)
- radix-ui primitives + shadcn/ui-style components

## Design language

Wall Street Brutalist — Fraunces (variable serif display) + JetBrains Mono
(body/UI/numerics). Deep ink + bone white + gold rule lines + mercury red +
caution amber + sharp mint. Hard right angles, SVG noise atmosphere,
editorial § numbering. Ported from `src/viz/theme.py` (Python design v3).

## Run locally

```bash
# Terminal 1 — start the API
cd ..
uvicorn api.main:app --reload

# Terminal 2 — start Next.js
cd web
npm install
npm run dev
# → http://localhost:3000
```

Or via docker compose (recommended):

```bash
cd ..
docker compose -f docker-compose.dev.yml up   # redis + api
cd web && npm run dev
```

## Build for production

```bash
npm run build
npm start
```

## Environment

| Var | Default | Description |
|---|---|---|
| `NEXT_PUBLIC_API_BASE` | `""` (proxy via Next rewrites) | Set to the Render URL in prod (e.g. `https://quant-terminal-api.onrender.com`) |
