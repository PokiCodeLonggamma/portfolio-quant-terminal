# Portage Quant Terminal — Streamlit → Next.js + FastAPI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Sortir Streamlit comme couche présentation et le remplacer par **FastAPI (backend) + Next.js (frontend) + WebSockets (live) + Redis (cache)** tout en réutilisant 100% de la logique quant Python existante (122/147 modules sont déjà purs).

**Architecture:** Monorepo `quant_terminal/` accueille 3 surfaces :
1. `quant_terminal/src/` (existant) — cœur quant pur Python : universe, gex, hmm, options_chain, scanners, analytics, portfolio engine
2. `quant_terminal/api/` (NEW) — FastAPI sur le cœur, expose REST + WebSocket, cache Redis
3. `quant_terminal/web/` (NEW) — Next.js 15 App Router + TypeScript + Tailwind + TanStack Query + Zustand + lightweight-charts (TradingView free lib)

Streamlit reste actif EN PARALLÈLE pendant la migration — chaque tab est portée → l'ancienne est désactivée. Pas de big-bang.

**Tech Stack:**
- Backend : Python 3.11, FastAPI 0.115+, uvicorn, redis-py, arq (background jobs async), Pydantic v2 (déjà utilisé)
- Cache : Redis 7+ (local docker en dev, Upstash ou Redis Cloud en prod)
- Frontend : Node 20+, Next.js 15, TypeScript 5, Tailwind 4, shadcn/ui (radix primitives), TanStack Query 5, Zustand 5, lightweight-charts 5, Plotly.js 2
- Deploy (FREE TIER stack — validated) :
  - **Next.js** → **Vercel free Hobby plan** (100GB bandwidth/mois, build illimité)
  - **FastAPI** → **Render free** (web service 512MB RAM, cold-start ~30-60s après 15min idle — acceptable pour un dashboard de trading qu'on garde ouvert pendant la session)
  - **Redis** → **Upstash free** (10k commandes/jour, 256MB, latence <50ms via REST API)
  - **Worker arq** → SAME Render service (background job intra-process, pas de worker séparé en free tier)
  - **Alternative latency-critique** : Fly.io free (256MB VM, cold-start ~500ms, requiert CB enregistrée)
  - **Domain** : `quant-terminal.vercel.app` (gratuit) ou domaine perso ~10€/an

---

## Architecture cible

```
┌───────────────────────────────────────────────────────────────────────────┐
│                          NEXT.JS 15 (Vercel)                              │
│  ┌──────────┬──────────┬──────────┬──────────┬──────────┬─────────────┐   │
│  │Watchlist │ Charts   │ GEX      │Positions │ News     │ Execution   │   │
│  │+ Alerts  │ + Chains │ + Vol3D  │+ Greeks  │+ Catalyst│ + Logs      │   │
│  │+ Bookmark│          │          │+ Risk    │          │             │   │
│  └──────────┴──────────┴──────────┴──────────┴──────────┴─────────────┘   │
│  ┌───────────────────────── Mobile (PWA) ──────────────────────────────┐ │
│  │  Quick-Execute · Alerts · Macro Snapshot · Mini GEX · Portfolio    │ │
│  └─────────────────────────────────────────────────────────────────────┘ │
└──────────────────────────┬────────────────────────────────────────────────┘
                           │ HTTPS (REST) + WSS (live)
┌──────────────────────────▼────────────────────────────────────────────────┐
│                         FASTAPI (Fly.io)                                  │
│  /api/universe   /api/portfolio   /api/options/{tk}/chain                 │
│  /api/gex/{tk}   /api/hmm/{tk}    /api/scanners/squeeze                   │
│  /api/news       /api/catalysts   /api/alerts                             │
│  /ws/prices      /ws/alerts       /ws/positions                           │
└─────────┬───────────────────────────────────┬─────────────────────────────┘
          │ async/await                       │ pub/sub
┌─────────▼──────────────┐         ┌──────────▼──────────────┐
│  PYTHON CORE (existing)│         │      REDIS              │
│  src/universe          │         │  - options chain (60s)  │
│  src/trading/gex       │         │  - GEX (60s)            │
│  src/trading/...       │         │  - HMM fit (1h)         │
│  src/regime/hmm        │         │  - vol surface (60s)    │
│  src/portfolio         │         │  - news (5min)          │
│  src/scanners          │         │  - prices live (pub/sub)│
│  src/news              │         └─────────────────────────┘
└────────────────────────┘
          │
          │ external APIs
          ▼
   Alpaca · yfinance · SEC EDGAR · FRED · FMP · Stocktwits · Anthropic
```

---

## File Structure (monorepo flat layout)

```
quant_terminal/
├── src/                       # EXISTING — pure Python quant core
│   ├── universe/              # ← réutilisé tel quel
│   ├── trading/               # ← réutilisé tel quel
│   ├── regime/                # ← réutilisé tel quel
│   ├── portfolio/             # ← réutilisé tel quel
│   ├── scanners/              # ← réutilisé tel quel
│   ├── news/                  # ← réutilisé tel quel
│   ├── decision/              # ← business logic réutilisée, dashboards.py deprecate
│   ├── viz/                   # ← Plotly figures réutilisées (rendues côté Python pour PNG/JSON)
│   └── ...
├── api/                       # NEW — FastAPI app
│   ├── main.py                # uvicorn entrypoint
│   ├── deps.py                # auth, redis client, config
│   ├── routes/
│   │   ├── universe.py
│   │   ├── portfolio.py
│   │   ├── options.py         # chains + GEX
│   │   ├── regime.py
│   │   ├── scanners.py
│   │   ├── news.py
│   │   ├── alerts.py
│   │   └── execution.py
│   ├── ws/
│   │   ├── prices.py
│   │   ├── alerts.py
│   │   └── positions.py
│   ├── cache.py               # redis wrapper + TTL decorators
│   ├── workers/               # arq async jobs
│   │   ├── refresh_chains.py
│   │   ├── refresh_news.py
│   │   └── fit_hmm.py
│   └── models.py              # Pydantic v2 response schemas (réutilise src/common/schemas.py)
├── web/                       # NEW — Next.js 15 frontend
│   ├── app/                   # App Router
│   │   ├── layout.tsx         # shell brutalist (theme v3 porté)
│   │   ├── page.tsx           # accueil = redirect /dashboard
│   │   ├── (desktop)/
│   │   │   ├── dashboard/page.tsx       # 4-panel terminal
│   │   │   ├── portfolio/page.tsx
│   │   │   ├── trading/page.tsx         # chains + GEX + ticket
│   │   │   ├── cross-asset/page.tsx     # CDC §1
│   │   │   ├── macro/page.tsx
│   │   │   ├── catalysts/page.tsx
│   │   │   ├── hmm/page.tsx
│   │   │   ├── squeeze/page.tsx
│   │   │   ├── smart-money/page.tsx
│   │   │   ├── decision/page.tsx
│   │   │   ├── alerts/page.tsx
│   │   │   ├── execution/page.tsx
│   │   │   └── ...
│   │   ├── m/                 # mobile-only routes
│   │   │   ├── positions/page.tsx
│   │   │   ├── alerts/page.tsx
│   │   │   ├── macro/page.tsx
│   │   │   └── quick-execute/page.tsx
│   │   └── api/auth/...       # NextAuth route handlers (optionnel)
│   ├── components/
│   │   ├── ui/                # shadcn/ui primitives (button, card, sheet, ...)
│   │   ├── KpiTile.tsx
│   │   ├── SectionHeader.tsx
│   │   ├── TradingChart.tsx   # lightweight-charts wrapper
│   │   ├── OptionsChain.tsx
│   │   ├── GexMap.tsx
│   │   ├── VolSurface3D.tsx   # plotly.js
│   │   ├── DataTable.tsx      # tanstack/react-table
│   │   ├── LivePill.tsx       # WS connection indicator
│   │   └── ...
│   ├── lib/
│   │   ├── api.ts             # typed REST client (codegen depuis OpenAPI)
│   │   ├── ws.ts              # WebSocket reconnect logic
│   │   ├── auth.ts
│   │   └── format.ts          # fmt_eur, fmt_pct (TS port)
│   ├── store/
│   │   ├── alerts.ts          # zustand
│   │   ├── prices.ts
│   │   └── selection.ts
│   ├── styles/
│   │   ├── globals.css        # design v3 brutalist port
│   │   └── tokens.css         # CSS vars (palette, fonts)
│   ├── public/
│   │   └── manifest.json      # PWA
│   ├── tailwind.config.ts
│   ├── tsconfig.json
│   ├── package.json
│   └── next.config.mjs
├── docker-compose.dev.yml     # postgres + redis + arq worker
├── docker-compose.prod.yml    # idem + nginx reverse proxy
├── app.py                     # EXISTING Streamlit — gardé pendant migration
├── pyproject.toml             # Python deps unifiées (ajoute fastapi, redis, arq)
└── tests/                     # existing pytest + new test_api/, test_ws/
```

**Pas de monorepo Turborepo / npm workspaces** dans la v1 — la structure flat est suffisante. Next.js et Python coexistent au même niveau, chacun a son propre lockfile (`package-lock.json` et `uv.lock` / `requirements.lock`).

---

## Phase Map (7 phases, ~10 semaines)

| Phase | Livrable | Durée estimée | Détail |
|---|---|---|---|
| **0** | Foundation : Docker, Redis, FastAPI skeleton + 1 endpoint, Next.js skeleton + 1 page | 1 semaine | Détaillé ci-dessous |
| **1** | Service extraction : isoler la logique métier des modules `*_dashboard.py` en services purs, écrire les Pydantic models de réponse pour tout `src/` | 1 semaine | Détaillé ci-dessous |
| **2** | FastAPI surface complète : 12 routes REST + 3 WebSockets, OpenAPI auto-doc, auth JWT | 2 semaines | Plan détaillé à écrire au début de Phase 2 |
| **3** | Cache Redis + workers async (arq) : chains, GEX, HMM, vol surface, news, prices live | 1 semaine | Plan détaillé à écrire au début de Phase 3 |
| **4** | Next.js scaffold + design v3 port (Fraunces + JetBrains Mono + brutalist tokens en Tailwind) | 1 semaine | Plan détaillé à écrire au début de Phase 4 |
| **5** | Migration tab-par-tab : 17 tabs → 17 pages Next.js (priorité : Cross-Asset, Portfolio, Trading Bench, Macro, Catalysts) | 3-4 semaines | Plan détaillé à écrire au début de Phase 5 |
| **6** | Mobile PWA : routes /m/*, manifest, push notifications, mode trader | 1 semaine | Plan détaillé à écrire au début de Phase 6 |
| **7** | Streamlit deprecation + retirement | 0.5 semaine | Plan détaillé à écrire au début de Phase 7 |

**Total : ~10 semaines** en travail intensif, ~3-4 mois en parallèle d'autres tâches.

**CDC §2-§6 pendant le portage** : on développe les nouveaux modules quant directement avec FastAPI endpoints from day one. Pas d'attente. §2 (Moteur GEX v2) en particulier bénéficie immédiatement de Redis + workers async (calculs lourds).

---

## Phase 0 — Foundation (1 semaine)

### Task 0.1 : Branch + monorepo dirs

**Files:**
- Create: `api/`, `web/`, `docker-compose.dev.yml`

- [ ] **Step 1: Branch off main**

```bash
git checkout main
git pull
git checkout -b feat/portage-phase-0-foundation
```

- [ ] **Step 2: Create directories**

```bash
mkdir -p api/routes api/ws api/workers
mkdir -p web/app web/components web/lib web/store web/styles web/public
touch api/__init__.py api/main.py api/deps.py api/cache.py api/models.py
touch api/routes/__init__.py
touch api/ws/__init__.py
touch api/workers/__init__.py
```

- [ ] **Step 3: Commit empty scaffold**

```bash
git add api/ web/
git commit -m "chore(portage 0.1): empty api/ and web/ directories"
```

---

### Task 0.2 : Docker Compose dev — postgres + redis + arq worker

**Files:**
- Create: `docker-compose.dev.yml`, `Dockerfile.api`

- [ ] **Step 1: Write docker-compose.dev.yml**

```yaml
# docker-compose.dev.yml
services:
  redis:
    image: redis:7-alpine
    ports: ["6379:6379"]
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 5s
      timeout: 3s
      retries: 5

  api:
    build:
      context: .
      dockerfile: Dockerfile.api
    ports: ["8000:8000"]
    environment:
      REDIS_URL: redis://redis:6379/0
      APCA_API_KEY_ID: ${APCA_API_KEY_ID}
      APCA_API_SECRET_KEY: ${APCA_API_SECRET_KEY}
    depends_on:
      redis:
        condition: service_healthy
    volumes:
      - ./src:/app/src
      - ./api:/app/api
      - ./config:/app/config
    command: uvicorn api.main:app --reload --host 0.0.0.0 --port 8000

  worker:
    build:
      context: .
      dockerfile: Dockerfile.api
    environment:
      REDIS_URL: redis://redis:6379/0
    depends_on:
      redis:
        condition: service_healthy
    volumes:
      - ./src:/app/src
      - ./api:/app/api
      - ./config:/app/config
    command: arq api.workers.worker.WorkerSettings
```

- [ ] **Step 2: Write Dockerfile.api**

```dockerfile
# Dockerfile.api
FROM python:3.11-slim
WORKDIR /app
COPY pyproject.toml .
RUN pip install --no-cache-dir uv && uv pip install --system -e .[api]
COPY src/ src/
COPY api/ api/
COPY config/ config/
EXPOSE 8000
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

- [ ] **Step 3: Verify it builds**

```bash
docker compose -f docker-compose.dev.yml build
docker compose -f docker-compose.dev.yml up -d redis
docker compose -f docker-compose.dev.yml ps
docker compose -f docker-compose.dev.yml exec redis redis-cli ping
# Expected: "PONG"
docker compose -f docker-compose.dev.yml down
```

- [ ] **Step 4: Commit**

```bash
git add docker-compose.dev.yml Dockerfile.api
git commit -m "chore(portage 0.2): docker-compose dev — redis + api + worker"
```

---

### Task 0.3 : Add FastAPI + Redis + arq deps to pyproject.toml

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: Add optional-dependencies section**

```toml
# pyproject.toml — add this section
[project.optional-dependencies]
api = [
    "fastapi>=0.115.0",
    "uvicorn[standard]>=0.30.0",
    "redis>=5.0.0",
    "arq>=0.26.0",
    "python-jose[cryptography]>=3.3.0",  # JWT
    "passlib[bcrypt]>=1.7.4",
    "python-multipart>=0.0.9",
    "httpx>=0.27.0",  # async http
]
```

- [ ] **Step 2: Verify install**

```bash
pip install -e .[api]
python -c "import fastapi, redis, arq; print('OK')"
# Expected: OK
```

- [ ] **Step 3: Commit**

```bash
git add pyproject.toml
git commit -m "chore(portage 0.3): add api extras (fastapi, redis, arq, jose)"
```

---

### Task 0.4 : Minimal FastAPI app + healthcheck endpoint + test

**Files:**
- Create: `api/main.py`, `api/deps.py`, `tests/test_api_health.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_api_health.py
from fastapi.testclient import TestClient

from api.main import app


def test_health_endpoint_returns_ok():
    client = TestClient(app)
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert "version" in body
    assert "redis" in body


def test_openapi_schema_published():
    client = TestClient(app)
    r = client.get("/openapi.json")
    assert r.status_code == 200
    schema = r.json()
    assert schema["info"]["title"] == "Quant Terminal API"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python -m pytest tests/test_api_health.py -v
# Expected: ModuleNotFoundError: No module named 'api.main'
```

- [ ] **Step 3: Write api/deps.py**

```python
# api/deps.py
"""Shared FastAPI dependencies: redis client, config, auth (stub)."""
from __future__ import annotations

import os
from functools import lru_cache

import redis.asyncio as aioredis
from fastapi import Depends


@lru_cache(maxsize=1)
def get_redis_url() -> str:
    return os.getenv("REDIS_URL", "redis://localhost:6379/0")


async def get_redis() -> aioredis.Redis:
    """Async redis client — closed per-request via FastAPI lifespan."""
    return aioredis.from_url(get_redis_url(), decode_responses=True)


RedisDep = Depends(get_redis)
```

- [ ] **Step 4: Write api/main.py**

```python
# api/main.py
"""Quant Terminal — FastAPI entry point."""
from __future__ import annotations

from contextlib import asynccontextmanager

import redis.asyncio as aioredis
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.deps import get_redis_url

VERSION = "0.1.0"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: create the shared redis client. Shutdown: close it."""
    app.state.redis = aioredis.from_url(get_redis_url(), decode_responses=True)
    yield
    await app.state.redis.aclose()


app = FastAPI(
    title="Quant Terminal API",
    version=VERSION,
    description="Cross-asset cockpit — REST + WebSocket surface over the Python core.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "https://quant-terminal.vercel.app"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health():
    """Liveness + redis ping."""
    redis_ok = False
    try:
        # Test client lifecycle: app.state.redis isn't set under TestClient
        # without lifespan, so build a one-shot client here.
        r = aioredis.from_url(get_redis_url(), decode_responses=True)
        pong = await r.ping()
        redis_ok = bool(pong)
        await r.aclose()
    except Exception:
        redis_ok = False
    return {
        "status": "ok",
        "version": VERSION,
        "redis": "up" if redis_ok else "down",
    }
```

- [ ] **Step 5: Run test to verify PASS**

```bash
python -m pytest tests/test_api_health.py -v
# Expected: 2 passed (redis may be "down" if not running — that's fine, the test only
#           asserts the key exists)
```

- [ ] **Step 6: Smoke test live**

```bash
# Terminal 1 (start redis):
docker compose -f docker-compose.dev.yml up -d redis
# Terminal 2:
uvicorn api.main:app --reload
# Terminal 3:
curl http://localhost:8000/health
# Expected: {"status":"ok","version":"0.1.0","redis":"up"}
curl http://localhost:8000/openapi.json | python -c "import sys,json; print(json.load(sys.stdin)['info']['title'])"
# Expected: "Quant Terminal API"
```

- [ ] **Step 7: Commit**

```bash
git add api/ tests/test_api_health.py
git commit -m "feat(portage 0.4): FastAPI skeleton + /health + redis ping"
```

---

### Task 0.5 : First real endpoint — /api/universe (read-only)

**Files:**
- Create: `api/routes/universe.py`, `api/models.py`, `tests/test_api_universe.py`
- Modify: `api/main.py` (mount router)

- [ ] **Step 1: Write the failing test**

```python
# tests/test_api_universe.py
from fastapi.testclient import TestClient
from api.main import app

def test_get_universe_returns_all_classes():
    c = TestClient(app)
    r = c.get("/api/universe")
    assert r.status_code == 200
    body = r.json()
    assert "asset_classes" in body
    keys = {ac["key"] for ac in body["asset_classes"]}
    assert "us_indices" in keys
    assert "energy" in keys
    assert "crypto" in keys

def test_get_universe_class_returns_contracts():
    c = TestClient(app)
    r = c.get("/api/universe/us_indices")
    assert r.status_code == 200
    body = r.json()
    assert body["key"] == "us_indices"
    logicals = {c["logical"] for c in body["contracts"]}
    assert "ES" in logicals and "MES" in logicals

def test_get_contract_by_logical():
    c = TestClient(app)
    r = c.get("/api/universe/contracts/ES")
    assert r.status_code == 200
    body = r.json()
    assert body["logical"] == "ES"
    assert body["exchange"] == "CME"
    assert body["tradingview"] == "CME_MINI:ES1!"

def test_get_unknown_contract_returns_404():
    c = TestClient(app)
    r = c.get("/api/universe/contracts/NOPE")
    assert r.status_code == 404
```

- [ ] **Step 2: Run test — verify FAIL**

```bash
python -m pytest tests/test_api_universe.py -v
# Expected: 404 on all routes (router not mounted yet)
```

- [ ] **Step 3: Write api/models.py**

```python
# api/models.py
"""Pydantic response models for the FastAPI layer."""
from __future__ import annotations

from typing import Literal
from pydantic import BaseModel


class ContractResponse(BaseModel):
    logical: str
    name: str
    tier: Literal["standard", "mini", "micro"]
    root: str
    exchange: str
    asset_class: str
    yfinance: str
    alpaca: str
    tradingview: str
    multiplier: float
    currency: str
    tick_size: float
    tick_value: float
    option_market: bool
    notes: str


class AssetClassResponse(BaseModel):
    key: str
    label: str
    icon: str
    order: int
    contracts: list[ContractResponse]


class UniverseResponse(BaseModel):
    asset_classes: list[AssetClassResponse]
    theme_to_drivers: dict[str, dict[str, list[str]]]
```

- [ ] **Step 4: Write api/routes/universe.py**

```python
# api/routes/universe.py
"""Cross-asset universe endpoints — read-only, served from in-memory YAML."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from api.models import AssetClassResponse, ContractResponse, UniverseResponse
from src.universe.cross_asset import get_universe

router = APIRouter(prefix="/api/universe", tags=["universe"])


def _contract_to_dict(c) -> dict:
    return {
        "logical": c.logical, "name": c.name, "tier": c.tier, "root": c.root,
        "exchange": c.exchange, "asset_class": c.asset_class,
        "yfinance": c.yfinance, "alpaca": c.alpaca, "tradingview": c.tradingview,
        "multiplier": c.multiplier, "currency": c.currency,
        "tick_size": c.tick_size, "tick_value": c.tick_value,
        "option_market": c.option_market, "notes": c.notes,
    }


@router.get("", response_model=UniverseResponse)
async def get_universe_root():
    u = get_universe()
    return {
        "asset_classes": [
            {
                "key": ac.key, "label": ac.label, "icon": ac.icon, "order": ac.order,
                "contracts": [_contract_to_dict(c) for c in ac.contracts],
            }
            for ac in u.asset_classes
        ],
        "theme_to_drivers": u.theme_to_drivers,
    }


@router.get("/{class_key}", response_model=AssetClassResponse)
async def get_asset_class(class_key: str):
    u = get_universe()
    for ac in u.asset_classes:
        if ac.key == class_key:
            return {
                "key": ac.key, "label": ac.label, "icon": ac.icon, "order": ac.order,
                "contracts": [_contract_to_dict(c) for c in ac.contracts],
            }
    raise HTTPException(status_code=404, detail=f"Unknown asset class: {class_key}")


@router.get("/contracts/{logical}", response_model=ContractResponse)
async def get_contract(logical: str):
    u = get_universe()
    spec = u.find(logical)
    if spec is None:
        raise HTTPException(status_code=404, detail=f"Unknown logical: {logical}")
    return _contract_to_dict(spec)
```

- [ ] **Step 5: Mount router in api/main.py**

```python
# api/main.py — add after the CORSMiddleware block
from api.routes import universe as universe_router  # noqa: E402

app.include_router(universe_router.router)
```

- [ ] **Step 6: Run test — verify PASS**

```bash
python -m pytest tests/test_api_universe.py -v
# Expected: 4 passed
```

- [ ] **Step 7: Live smoke test**

```bash
uvicorn api.main:app --reload &
sleep 1
curl http://localhost:8000/api/universe | python -c "import sys,json; d=json.load(sys.stdin); print(len(d['asset_classes']), 'classes')"
# Expected: "10 classes"
curl http://localhost:8000/api/universe/contracts/ES
# Expected: ES contract JSON
kill %1
```

- [ ] **Step 8: Commit**

```bash
git add api/routes/universe.py api/models.py api/main.py tests/test_api_universe.py
git commit -m "feat(portage 0.5): /api/universe — first real endpoint"
```

---

### Task 0.6 : Next.js scaffold + Tailwind + first page hitting the API

**Files:**
- Create: `web/package.json`, `web/tsconfig.json`, `web/next.config.mjs`, `web/tailwind.config.ts`, `web/app/layout.tsx`, `web/app/page.tsx`, `web/styles/globals.css`

- [ ] **Step 1: Bootstrap Next.js**

```bash
cd web
npx create-next-app@latest . \
  --typescript --tailwind --eslint \
  --app --no-src-dir \
  --import-alias "@/*" \
  --yes
cd ..
```

- [ ] **Step 2: Install runtime deps**

```bash
cd web
npm install @tanstack/react-query zustand lightweight-charts plotly.js \
  @radix-ui/react-dialog @radix-ui/react-tabs @radix-ui/react-select \
  clsx class-variance-authority
npm install --save-dev @types/plotly.js
cd ..
```

- [ ] **Step 3: Write web/lib/api.ts**

```typescript
// web/lib/api.ts
const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";

export async function fetchJSON<T>(path: string, init?: RequestInit): Promise<T> {
  const r = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
  });
  if (!r.ok) throw new Error(`${r.status} ${r.statusText} on ${path}`);
  return r.json();
}

export type Contract = {
  logical: string; name: string; tier: "standard" | "mini" | "micro";
  root: string; exchange: string; asset_class: string;
  yfinance: string; alpaca: string; tradingview: string;
  multiplier: number; currency: string; tick_size: number; tick_value: number;
  option_market: boolean; notes: string;
};

export type AssetClass = {
  key: string; label: string; icon: string; order: number;
  contracts: Contract[];
};

export type Universe = {
  asset_classes: AssetClass[];
  theme_to_drivers: Record<string, Record<string, string[]>>;
};

export const getUniverse = () => fetchJSON<Universe>("/api/universe");
```

- [ ] **Step 4: Replace web/app/page.tsx with a real Universe view**

```tsx
// web/app/page.tsx
import { getUniverse } from "@/lib/api";

export const revalidate = 300; // 5 min ISR

export default async function Home() {
  let universe;
  try {
    universe = await getUniverse();
  } catch (e) {
    return (
      <main className="p-8">
        <h1 className="qt-display text-4xl">Quant Terminal</h1>
        <p className="qt-mono text-red-400 mt-4">
          API offline. Start <code>uvicorn api.main:app</code> on port 8000.
        </p>
      </main>
    );
  }
  return (
    <main className="p-8">
      <header className="flex items-baseline gap-4 border-b border-amber-600 pb-4 mb-6">
        <span className="qt-display text-6xl text-amber-500 leading-none">§ 00</span>
        <div>
          <h1 className="qt-display text-4xl">Quant Terminal</h1>
          <p className="qt-mono text-sm text-stone-400">
            Cross-asset cockpit — Next.js + FastAPI · {universe.asset_classes.length} asset classes
          </p>
        </div>
      </header>
      <section className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
        {universe.asset_classes.map((ac) => (
          <article key={ac.key} className="qt-tile border-l-amber-600">
            <div className="qt-mono uppercase tracking-widest text-xs text-stone-400">
              {ac.icon} {ac.label}
            </div>
            <div className="qt-display text-2xl font-bold mt-1">{ac.contracts.length}</div>
            <div className="qt-mono text-xs text-stone-500 mt-1">
              {ac.contracts.slice(0, 4).map((c) => c.logical).join(" · ")}
              {ac.contracts.length > 4 ? "…" : ""}
            </div>
          </article>
        ))}
      </section>
    </main>
  );
}
```

- [ ] **Step 5: Write web/styles/globals.css with v3 tokens**

```css
/* web/styles/globals.css */
@import "tailwindcss";

@import url("https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,300;9..144,400;9..144,700;9..144,900&family=JetBrains+Mono:wght@300;400;500;700&display=swap");

@theme {
  --color-ink: #0a0a0f;
  --color-elev: #14141c;
  --color-card: #1a1a24;
  --color-bone: #faf7f2;
  --color-rule: #d4af37;
  --color-mercury: #ff3838;
  --color-mint: #2ee89e;
  --color-amber: #ffb800;
  --font-display: "Fraunces", "Newsreader", Georgia, serif;
  --font-mono: "JetBrains Mono", ui-monospace, monospace;
}

body {
  background: var(--color-ink);
  color: var(--color-bone);
  font-family: var(--font-mono);
  background-image:
    radial-gradient(circle at 100% 0%, rgba(212,175,55,0.08) 0%, transparent 600px),
    url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='200' height='200'><filter id='n'><feTurbulence type='fractalNoise' baseFrequency='0.85' numOctaves='2' stitchTiles='stitch'/></filter><rect width='100%25' height='100%25' filter='url(%23n)' opacity='0.05'/></svg>");
  background-attachment: fixed;
}

.qt-display { font-family: var(--font-display); letter-spacing: -0.02em; }
.qt-mono { font-family: var(--font-mono); }

.qt-tile {
  background: var(--color-card);
  border: 1px solid #2A2A38;
  border-left: 3px solid var(--color-rule);
  border-radius: 0;
  padding: 16px 18px;
  transition: background-color 120ms ease;
}
.qt-tile:hover { background: #242430; }
```

- [ ] **Step 6: Run dev server**

```bash
# Terminal 1: start FastAPI
uvicorn api.main:app --reload &
# Terminal 2: start Next.js
cd web && npm run dev
# Open http://localhost:3000
# Expected: brutalist page rendering all 10 asset classes from the live API
```

- [ ] **Step 7: Verify visually**

Open http://localhost:3000 in a browser. Check:
- Fraunces displays in the title
- JetBrains Mono in the body
- Deep ink background with noise overlay
- 10 asset classes shown in a grid with gold left accent

- [ ] **Step 8: Commit**

```bash
git add web/
git commit -m "feat(portage 0.6): Next.js scaffold + first universe view hitting FastAPI"
```

---

### Task 0.7 : Push branch + open PR

**Files:** none modified.

- [ ] **Step 1: Run full test suite**

```bash
python -m pytest -q
# Expected: all 295 + 6 new api tests pass
```

- [ ] **Step 2: Run lint**

```bash
ruff check src/ api/ app.py tests/ --select F401,F811,F841,E711,E712
# Expected: All checks passed!
```

- [ ] **Step 3: Push**

```bash
git push -u origin feat/portage-phase-0-foundation
```

- [ ] **Step 4: Open PR**

```bash
gh pr create --title "feat(portage 0): foundation — FastAPI + Next.js + Redis docker" \
  --body "Phase 0 du portage Streamlit → Next.js/FastAPI.\n\n- docker-compose dev (redis + api + worker)\n- FastAPI skeleton + /health + /api/universe\n- Next.js 15 scaffold + premier hit live sur l'API\n- Design v3 ported en Tailwind CSS variables\n\nStreamlit reste actif en parallèle. CDC §2-§6 développés directement avec FastAPI endpoints from day one.\n\n🤖 Generated with [Claude Code](https://claude.com/claude-code)"
```

---

## Phase 1 — Service extraction (1 semaine)

### Goal
Isoler la logique métier des `*_dashboard.py` (qui mélangent compute + Streamlit) en services purs retournant des Pydantic models. C'est le prérequis pour exposer ces services via FastAPI sans réécrire la logique.

### Inventory des 25 modules Streamlit-couplés

| Module | Logique métier à extraire | Service cible |
|---|---|---|
| `src/alerts/dashboards.py` | trigger eval, channel dispatch | déjà extrait dans `src/alerts/engine.py` |
| `src/backtest/dashboards.py` | backtest run + metrics | extraire `BacktestService` |
| `src/calendar_engine/dashboards.py` | event fetch + render | déjà extrait dans `src/calendar_engine/store.py` |
| `src/data_sec/dashboards.py` | Form 4/13F/SHO fetch + parse | extraire `SECService` |
| `src/decision/dashboards.py` | conviction scoring, hedge cost | extraire `ConvictionService`, `HedgeService` |
| `src/decision/cross_asset_dashboard.py` | quote enrichment + heatmap data | extraire `CrossAssetService` |
| `src/event_trading/dashboards.py` | pre-event wizard, earnings sim | extraire `EventService` |
| `src/execution/dashboards.py` | OMS state | déjà dans `src/execution/oms.py` |
| `src/liquidity/dashboards.py` | liquidity metrics | extraire `LiquidityService` |
| `src/macro/dashboards.py` | regime + correlations + liquidity | extraire `MacroService` |
| `src/news/dashboards.py` | news aggregation + sentiment | extraire `NewsService` |
| `src/portfolio/greeks_dashboards.py` | portfolio greeks roll-up | extraire `GreeksService` |
| `src/regime/hmm_dashboards.py` | HMM fit + plot data | extraire `HMMService` |
| `src/regime/sizing.py` | regime-conditional sizing | mostly pure already, light cleanup |
| `src/scanners/squeeze_zoom.py` | squeeze visual data | extraire `SqueezeVisualService` |
| `src/snapshot/dashboards.py` | snapshot capture + replay | extraire `SnapshotService` |
| `src/tax/dashboards.py` | tax lots FIFO + 2074 | déjà extrait dans `src/tax/lots.py` |
| `src/trading/dashboards.py` | options chain fetch + GEX | déjà dans `src/trading/options_chain.py`, `gex.py` |
| `src/trading/live_book.py` | aggregate book greeks | déjà extrait |
| `src/trading/vol_surface.py` | surface grid | déjà extrait |
| `src/viz/dashboards.py` | plot helpers | reste viz, pas service |
| `src/watchlist/dashboards.py` | watchlist read/write | extraire `WatchlistService` |
| `src/watchlist/trading_board_render.py` | board card data | extraire `BoardService` |

### Task 1.1 to 1.10
À détailler en plan complet une fois Phase 0 livrée. Format identique : TDD, bite-sized, commit par service.

---

## Phases 2-7 (outlines)

À détailler en plans complets une fois la phase précédente livrée. Outline ici uniquement pour validation directionnelle.

### Phase 2 — FastAPI surface complète (2 semaines)
Routes REST :
- `/api/portfolio/{user_id}` GET → portfolio + Greeks
- `/api/portfolio/{user_id}/upload` POST → ingest DEGIRO CSV
- `/api/options/{ticker}/chain` GET → options chain (cached 60s)
- `/api/options/{ticker}/gex` GET → GEX (cached 60s)
- `/api/options/{ticker}/vol_surface` GET → 3D surface
- `/api/options/{ticker}/iv_term_structure` GET → term structure
- `/api/options/{ticker}/iv_crush` POST → scenario projection
- `/api/regime/hmm` GET → HMM regime (cached 1h)
- `/api/regime/macro` GET → macro regime snapshot
- `/api/scanners/universe` GET → options universe scanner
- `/api/scanners/squeeze` GET → SHO + 4-pillar deep scan
- `/api/news/latest` GET → news pulse (cached 5min)
- `/api/news/sentiment/{ticker}` GET → sentiment temps-réel
- `/api/catalysts/upcoming` GET → calendar
- `/api/alerts` CRUD
- `/api/alerts/triggers` POST → eval engine
- `/api/execution/orders` CRUD (paper + live latch)
- `/api/execution/positions` GET
- `/api/snapshot/{date}` GET → daily snapshot
- `/api/tax/lots` GET → FIFO + 2074
- `/api/cross-asset/quotes` POST `{logicals: [...]}` → bulk quotes
- `/api/daily-brief` GET → LLM brief (cached 1h)

WebSockets :
- `/ws/prices` → live prices (Alpaca + yfinance fan-out)
- `/ws/alerts` → alert notifications
- `/ws/positions` → position updates

Auth : JWT bearer (single-user, no signup) ou session cookie HttpOnly.

### Phase 3 — Redis cache + workers async (1 semaine)
- `api/cache.py` : `@cached(ttl=60, key_fn=...)` decorator
- `api/workers/refresh_chains.py` : arq job qui refresh chains pour les tickers en bookmarks toutes les 60s
- `api/workers/refresh_news.py` : pull RSS + Stocktwits + sentiment toutes les 5min
- `api/workers/fit_hmm.py` : refit HMM SPY/QQQ/IWM toutes les heures
- `api/workers/snapshot.py` : daily snapshot à 22h UTC

### Phase 4 — Next.js scaffold + design v3 port (1 semaine)
- App Router shell + layout brutalist (sidebar gauche + main + sidebar droite + bottom)
- Tailwind config porté du design v3 (Fraunces + JetBrains Mono + tokens palette)
- shadcn/ui primitives (button, card, sheet, dialog, tabs, select, popover)
- TanStack Query setup + reactQueryProvider
- Zustand stores (alerts, prices, selection)
- TradingChart component (lightweight-charts) qui remplace le TV iframe
- KpiTile, SectionHeader, DataTable, LivePill, EmptyState components
- Auth flow (NextAuth ou JWT manuel)

### Phase 5 — Migration tab-par-tab (3-4 semaines)
Ordre de migration (du plus simple au plus complexe) :
1. Cross-Asset (CDC §1, déjà structuré)
2. Watchlists + Bookmarks
3. Macro & Regime
4. Catalysts & News
5. HMM Regime
6. Portfolio (DEGIRO upload côté serveur)
7. Smart-Money & Fundamentals
8. Decision Support
9. Short Squeeze
10. Backtest
11. Snapshot & Tax
12. Daily Brief
13. Event Trading
14. Trading Bench (chains + GEX + ticket — complexe)
15. Alerts
16. Kalman (optionnel — laisser en Streamlit si peu utilisé)
17. Execution (CRITIQUE — DERNIER, avec garde-fou EXECUTION_ALLOW_LIVE=0)

Pour chaque tab :
- Plan détaillé séparé
- 1 PR par tab
- Streamlit tab desactivé seulement après validation utilisateur

### Phase 6 — Mobile PWA (1 semaine)
- `public/manifest.json` + service worker (next-pwa)
- Routes `/m/positions`, `/m/alerts`, `/m/macro`, `/m/quick-execute`
- Layout mobile-first avec bottom navigation
- Push notifications via Web Push API (alerts critiques)
- Mode "trader" : positions + alerts + execute en 2 taps

### Phase 7 — Streamlit deprecation (0.5 semaine)
- Bannière sur `app.py` "Migrate to https://quant-terminal.vercel.app"
- 30 jours de cohabitation
- Retire Streamlit deploy
- Archive `app.py` dans `legacy/streamlit_app.py`

---

## Risk Register

| Risque | Impact | Mitigation |
|---|---|---|
| Re-implémentation Plotly côté frontend lourde | 1-2 semaines en plus | Servir les figures Plotly comme JSON depuis FastAPI, hydrater côté client avec `react-plotly.js` |
| WebSocket reconnect / state sync complexe | bugs en prod | TanStack Query + Zustand pattern bien rodé, tests d'intégration |
| Auth single-user mais besoin de protéger les keys API | leak | Toutes les keys côté FastAPI uniquement, jamais en `NEXT_PUBLIC_*` |
| FX EUR-normalisation côté frontend | calculs incohérents | Tous les montants normalisés EUR côté FastAPI avant envoi |
| DEGIRO CSV upload côté serveur (multipart) | doit gérer encoding latin-1 / UTF-8 mix | tests dédiés avec fixtures DEGIRO réelles |
| Vercel cold starts vs FastAPI persistent | latence | Fly.io ou Railway pour FastAPI (toujours warm) |
| User a investi temps significatif dans Streamlit theme v3 | morale | Tout le travail v3 est PORTÉ (palette, fonts, classes CSS) — pas perdu |
| 17 tabs × estimation 2-3 jours/tab = 6-8 semaines pour Phase 5 | timeline | Migration progressive, Streamlit reste utilisable |
| CDC §2 (GEX v2) bloqué en attendant le portage | retard CDC | §2 développé directement avec FastAPI endpoints dès Phase 2 |

---

## Self-Review

**1. Spec coverage** (`docs/Portage.md`) :
- ✅ Next.js + React : Phases 0, 4, 5
- ✅ FastAPI backend : Phases 0, 1, 2
- ✅ WebSockets temps réel : Phase 2 (`/ws/prices`, `/ws/alerts`, `/ws/positions`)
- ✅ Workers async (calculs lourds) : Phase 3 (arq)
- ✅ Redis cache : Phases 0, 3
- ✅ Mobile (PWA) : Phase 6
- ✅ Garder Python : Phase 0+ — `src/` réutilisé tel quel
- ✅ Transformer Streamlit en backend temporaire : Phase 1 (extraction services purs)
- ✅ Vrai frontend terminal (4-panel layout) : Phase 4
- ✅ Mode mobile trader : Phase 6

**2. Placeholder scan** :
- Phases 2-7 sont volontairement en outline pour rester pragmatique (chaque phase fait l'objet d'un plan détaillé à son démarrage). Pas un placeholder — c'est une livraison incrémentale.
- Phase 0 et Phase 1 ont des tâches concrètes avec code complet.

**3. Type consistency** :
- `ContractResponse` / `AssetClassResponse` / `UniverseResponse` (Phase 0.5) cohérents avec `ContractSpec` / `AssetClass` / `CrossAssetUniverse` du core Python.
- TypeScript `Contract` / `AssetClass` / `Universe` (web/lib/api.ts) miroir exact des Pydantic models.

---

## Execution Handoff

Plan complet sauvegardé à `docs/superpowers/plans/2026-05-27-portage-streamlit-nextjs-fastapi.md`. Deux options d'exécution :

**1. Subagent-Driven (recommandé pour ce plan-cadre)** — Dispatch un sub-agent frais par phase. Permet de tester chaque phase isolément, review entre phases, contexte propre à chaque démarrage.

**2. Inline Execution** — Exécuter Phase 0 puis Phase 1 dans cette session. ~12 tâches Phase 0 (~3-5 min each) = ~1h, tient dans le contexte actuel.

**Avant exécution, validation utilisateur sur 4 points** :

1. **Choix d'hosting** : Vercel (Next.js gratuit) + Fly.io (FastAPI ~5€/mois) + Upstash Redis (gratuit) — OK ?
2. **CDC §2-§6 en parallèle ou bloqués ?** : Recommandation : §2 démarre directement avec FastAPI endpoints, ne BLOQUE pas la suite du CDC.
3. **Auth scope** : single-user (clés API en env vars, JWT bearer simple) — OK ?
4. **Layout terminal** : 4-panel (sidebar gauche + main + droite + bottom) comme dans `Portage.md` ou 3-panel avec drawer mobile — préférence ?
