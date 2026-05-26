# Quant Terminal

[![CI](https://github.com/PokiCodeLonggamma/portfolio-quant-terminal/actions/workflows/ci.yml/badge.svg)](https://github.com/PokiCodeLonggamma/portfolio-quant-terminal/actions/workflows/ci.yml)
[![CodeQL](https://github.com/PokiCodeLonggamma/portfolio-quant-terminal/actions/workflows/codeql.yml/badge.svg)](https://github.com/PokiCodeLonggamma/portfolio-quant-terminal/actions/workflows/codeql.yml)

Terminal quant institutionnel multi-modules. Trois piliers :

1. **Portfolio Analytics** -- ingestion DEGIRO, prix Alpaca (+ fallback yfinance), conversion FX live, VaR/CVaR, stress tests, factor exposures, lightweight-charts.
2. **Short Squeeze Scanner** -- branchement SEC EDGAR + Finviz (template prêt).
3. **Kalman Elastic Trading** -- monitoring de la Phase 2 industrialisée et des métriques Phase 3.

## Installation

```bash
cp .env.example .env       # remplir les clés Alpaca + SEC_EMAIL
pip install -e .
python -m src.main         # lance Streamlit
```

`python -m src.main` est un wrapper qui appelle `streamlit run` sur `app.py` avec la bonne config.

## Arborescence

```
quant_terminal/
├── pyproject.toml / setup.py / requirements.txt / .env.example
├── app.py                       # Streamlit multi-onglets (entry-point UI)
├── config/
│   ├── settings.yaml
│   ├── universe.yaml            # mapping ticker -> thème, région, devise
│   └── risk_limits.yaml
├── src/
│   ├── main.py                  # wrapper -> streamlit
│   ├── data/        loaders.py, degiro_parser.py, fx.py, fred_client.py
│   ├── portfolio/   holdings.py, analytics.py, risk.py
│   ├── analytics/   factors.py, scenarios.py, optimizer.py
│   ├── scanners/    short_squeeze.py (template SEC EDGAR + Finviz)
│   ├── kalman/      monitoring.py (template Phase 2/3)
│   ├── viz/         dashboards.py, plots.py, theme.py
│   └── utils/       config.py, logging.py, cache.py
└── tests/
```

## Données

- **Alpaca** (primary, US equities) — `APCA_API_KEY_ID` / `APCA_API_SECRET_KEY`.
- **yfinance** (fallback silencieux pour ETP européens, TSX, CAD/EUR).
- **FRED** (séries macro).
- **SEC EDGAR** (scraper short squeeze, requiert `SEC_EMAIL`).

## Forex

Toutes les valeurs sont normalisées en EUR avant les calculs (PnL, VaR, drawdown). Voir
`src/data/fx.py` (taux live via yfinance) et `src/portfolio/analytics.py`.

## Charts

`lightweight-charts` (moteur TradingView) via `streamlit-lightweight-charts` pour
rendre les bougies et indicateurs avec une qualité institutionnelle.
