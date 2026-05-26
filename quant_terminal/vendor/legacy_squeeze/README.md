# 🔍 Short Squeeze Scanner

Scanner automatisé de setups Short Squeeze sur les marchés NYSE/NASDAQ.

## Architecture

```
short-squeeze-scanner/
├── config/
│   └── settings.py          # Config centralisée (.env)
├── src/
│   ├── scrapers/
│   │   ├── finviz_scraper.py # Screening SI + données institutionnelles
│   │   ├── edgar_13f.py      # SEC EDGAR — variation holders 13F
│   │   └── options_flow.py   # yfinance — P/C ratio, OI, anomalies
│   ├── analysis/
│   │   └── scoring.py        # Moteur de scoring 3 piliers (/10)
│   ├── storage/
│   │   └── database.py       # SQLite — persistance + deltas historiques
│   ├── alerts/
│   │   └── telegram_bot.py   # Alertes Telegram
│   └── main.py               # Orchestrateur principal
├── data/                     # SQLite DB (auto-créé)
├── .env.example
└── pyproject.toml
```

## Installation

```bash
git clone <repo>
cd short-squeeze-scanner
pip install -e .

# Configuration
cp .env.example .env
# Éditer .env : renseigner SEC_USER_AGENT (obligatoire) + Telegram (optionnel)
```

## Usage

```bash
# Scan complet — screening + enrichissement + scoring
python -m src.main

# Scan un ticker spécifique
python -m src.main --ticker HIMS

# Mode scheduler (scan quotidien 18h30 EST)
python -m src.main --schedule

# Debug verbose
python -m src.main -v
```

## Scoring — 3 Piliers (/10)

### Pilier 1 — Structure VAD (4 pts)
| Critère | Seuil | Points |
|---------|-------|--------|
| Short % Float > 30% | 30% | 1.5 |
| Days to Cover > 7j | 7 | 1.5 |
| Borrow Rate > 30% | 30% | 0.5 |
| Utilization > 80% | 80% | 0.5 |

### Pilier 2 — Positionnement Institutionnel (4 pts)
| Critère | Source | Points |
|---------|--------|--------|
| Hausse institutional ownership | Finviz `Inst Trans` + EDGAR 13F | 1.5 |
| Call OI en hausse > 20% / 30j | yfinance (delta vs DB) | 1.0 |
| Put/Call Ratio < 0.7 | yfinance option chains | 1.0 |
| Unusual options activity | Volume/OI > 5x anomaly | 0.5 |

### Pilier 3 — Divergence (2 pts)
SI élevé + accumulation institutionnelle simultanée = 2 pts

### Signaux
- 🔴 **FORT** (≥ 7/10) — Setup actionnable
- 🟡 **MODÉRÉ** (5-6/10) — Surveiller catalyseur
- ⚪ **FAIBLE** (< 5/10) — Watchlist

## Sources de données

| Donnée | Source | Coût | Fréquence |
|--------|--------|------|-----------|
| Short Float, DTC | Finviz scraping | Gratuit | Bi-mensuel (FINRA) |
| Inst Own, Inst Trans | Finviz scraping | Gratuit | Trimestriel |
| Holders Δ (13F) | SEC EDGAR EFTS | Gratuit | Trimestriel |
| 13D activity | SEC EDGAR EFTS | Gratuit | Temps réel |
| Options OI, P/C ratio | yfinance | Gratuit | Quotidien |
| Borrow Rate | N/D (nécessite Ortex) | ~$50/mois | Intraday |
| Utilization | N/D (nécessite Ortex) | ~$50/mois | Intraday |

## Améliorations futures

- [ ] Intégration Ortex API (borrow rate + utilization)
- [ ] Highshortinterest.com comme source complémentaire
- [ ] ML scoring (Random Forest sur historique de squeezes)
- [ ] Dashboard Streamlit
- [ ] Backtest : labeller les squeezes passés et mesurer la précision du scoring
