Voici le cahier des charges détaillé et structuré pour la transformation du Quant Terminal en une plateforme institutionnelle de pointe.

---

# CAHIER DES CHARGES : QUANT TERMINAL (INSTITUTIONAL GRADE)

## 1. PÉRIMÈTRE DE L'UNIVERS CROSS-ASSET

L'infrastructure doit être capable de pricer, surveiller et modéliser l'univers complet suivant, en intégrant les spécificités de microstructure de chaque contrat.

### Indices US

| Actif | Contrat Standard | Mini | Micro | Exchange |
| --- | --- | --- | --- | --- |
| S&P 500 | SP | ES (E-mini) | MES (Micro E-mini) | CME |
| Nasdaq 100 | ND | NQ | MNQ | CME |
| Dow Jones | DJ | YM | MYM | CBOT |
| Russell 2000 | RTY | RTY (déjà mini) | M2K | CME |
| S&P MidCap 400 | — | EMD | — | CME |

### Volatilité

| Actif | Standard | Mini/Micro | Exchange |
| --- | --- | --- | --- |
| VIX | VX | VXM (Mini VIX) | CBOE |

### Taux US

| Actif | Standard | Mini/Micro | Exchange |
| --- | --- | --- | --- |
| 2-Year T-Note | ZT | TU | CBOT |
| 5-Year T-Note | ZF | FV | CBOT |
| 10-Year T-Note | ZN | TY | CBOT |
| 30-Year T-Bond | ZB | US | CBOT |

### Énergie

| Actif | Standard | Mini | Micro | Exchange |
| --- | --- | --- | --- | --- |
| WTI Crude Oil | CL | QM (E-mini Crude) | MCL | NYMEX |
| Brent Crude | B | — | MBT (selon broker) | ICE |
| Natural Gas | NG | QG (E-mini NG) | MNG | NYMEX |
| Heating Oil | HO | — | — | NYMEX |
| RBOB Gasoline | RB | — | — | NYMEX |

### Métaux Stratégiques & Précieux

*Inclusion du suivi des métaux critiques (Tungstène, Uranium) via actions et ETF associés.*

| Actif | Standard | Mini | Micro | Exchange |
| --- | --- | --- | --- | --- |
| Gold | GC | QO / MGC | MGC | COMEX |
| Silver | SI | QI | SIL | COMEX |
| Copper | HG | QC | MHG | COMEX |
| Platinum | PL | — | — | NYMEX |
| Palladium | PA | — | — | NYMEX |


### Crypto Futures

| Actif | Standard | Mini/Micro | Exchange |
| --- | --- | --- | --- |
| Bitcoin | BTC | MBT (Micro Bitcoin) | CME |
| Ether | ETH | MET (Micro Ether) | CME |

### Futures Européens

| Actif | Standard | Mini/Micro | Exchange |
| --- | --- | --- | --- |
| Euro Stoxx 50 | FESX | MFS (Mini Euro Stoxx) | Eurex |
| DAX | FDAX | FDXM (Mini-DAX), FDXS (Micro-DAX) | Eurex |
| CAC 40 | FCE | — | Euronext |
| FTSE 100 | Z | — | ICE Europe |
| Swiss Market Index | FSMI | — | Eurex |

### ETF Sectoriels & Thématiques (Options / Cash)

| Secteur / Thématique | ETF Principal | Futures Associés |
| --- | --- | --- |
| Tech | XLK / QQQ | NQ / MNQ |
| Semis | SMH / SOXX | NQ |
| Financières | XLF | ES |
| Énergie | XLE | CL / RB / NG |
| Utilities | XLU | ZN |
| Industrielles | XLI | ES |
| Santé | XLV | ES / NQ |
| Consommation | XLY / XLP | ES |
| Space Economy | ARKX / UFO | NQ / RTY |
| Uranium | URA / URNM | GC / Taux |

---

## 2. MOTEUR GEX, VOLATILITÉ ET DEALER POSITIONING

Refonte totale de l'approche statique actuelle pour implémenter un cockpit de microstructure dynamique évaluant l'exposition des market makers.

* **Modélisation du Dealer Positioning :** Implémentation d'un algorithme assignant la polarité (long/short) des flux d'options en fonction de l'agressivité au bid/ask.
* **Calcul du Net GEX (Gamma Exposure) :** Agrégation par maturité et par bucket de delta pour isoler les zones de friction et de liquidité (Gamma Flip, Call Wall, Put Wall, Vol Trigger).
* **Sensibilités de Second Ordre (Vanna) :** Mesure de la variation du delta face à un choc de volatilité implicite, modélisée mathématiquement par $\text{Vanna} = \frac{\partial \Delta}{\partial \sigma}$.
* **Sensibilités de Second Ordre (Charm) :** Estimation de la pression de couverture induite par l'écoulement du temps en fin de session, calculée par $\text{Charm} = -\frac{\partial \Delta}{\partial \tau}$.
* **Impact 0DTE & Sticky Gamma :** Jauges isolant le poids spécifique des flux expirant le jour même, permettant de repérer les zones de "Gamma pinning" (où l'actif est aimanté vers un strike) ou de "Gamma squeeze" (accélération directionnelle).

---

## 3. MARKET POSITIONING SNAPSHOT CROSS-ASSET

Création d'une matrice de surveillance institutionnelle centralisant l'état de chaque contrat de l'univers défini dans la Section 1.

* **Score de Crowding & CTA Positioning :** Estimation systématique du positionnement des fonds trend-followers (Max Long, Flat, Max Short) basé sur la distance relative aux moyennes mobiles institutionnelles (1 mois, 3 mois, 12 mois).
* **Régimes de Liquidité & Volatilité :** Analyse de la structure par terme du VIX (Contango vs Backwardation) couplée aux conditions de liquidité dollar et au contexte de repo/funding.
* **Sensibilités Macro Dynamiques :** Matrice de corrélation glissante mesurant l'influence instantanée du DXY, des taux US (ZN), et du pétrole (CL) sur la performance des thématiques spécifiques (ex: la sensibilité exacte du secteur spatial aux conditions monétaires).

---

## 4. PORTFOLIO CONTROL CENTER & RISQUE

Élévation de l'onglet Portfolio pour répondre aux exigences strictes de gestion de risque et d'allocation tactique.

* **Gestion Stricte du Drawdown (Paramétrage 10 000 €) :** Intégration de limites absolues de perte journalière (ex: 5%) et de perte maximale (ex: 10%), calquées sur les standards des prop firms modernes, avec coupure automatique des expositions.
* **Optimisation Dynamique du Covered Call :** Module dédié utilisant le Machine Learning pour la détection des régimes de volatilité afin de moduler dynamiquement la distance des strikes vendus, maximisant la capture de prime tout en limitant le risque de hausse d'opportunité.
* **Intégration Kalman Phase 3 :** Intégration du système de méta-labeling et de feature engineering pour filtrer les faux signaux et ajuster dynamiquement le sizing des stratégies élastiques.
* **Décomposition Factorielle & Fragilité :** Analyse en composantes principales pour détecter les corrélations cachées et calcul d'un score d'antifragilité pondérant les options longues (protection) par rapport au tail risk du portefeuille.

---

## 5. GESTION THÉMATIQUE

Capacité à monitorer, isoler et trader des narratifs sectoriels précis avec une granularité chirurgicale (Tech, Space Economy, Semis, Uranium).

* **Breadth & Momentum Thématique :** Suivi du pourcentage d'actions au sein d'une thématique (ex: ASTS, RKLB, BKSY) négociant au-dessus de leurs seuils critiques pour identifier la force interne du mouvement.
* **Accumulation Smart Money & Clusters :** Analyse des formulaires 13F croisés avec les transactions d'insiders pour détecter l'accumulation furtive institutionnelle avant le grand public.
* **Ségrégation Stricte des Données :** Garantie que les analyses fondamentales concernant des tickers spécifiques (ex: Algide [$ALGID]) ne sont pas parasitées par des entités homonymes ou structurellement différentes.

---

## 6. SHORT SQUEEZE SCANNER & SNAPSHOT

Restructuration du module existant pour fournir une vue d'ensemble immédiate de la pression vendeuse systémique.

* **Snapshot de l'Univers Short Squeeze :** Un tableau de bord consolidé généré quotidiennement, affichant une liste restreinte des 20 tickers les plus asymétriques du marché. Ce snapshot doit fusionner les entités présentes sur la SEC SHO Threshold List avec les données structurelles (Short Interest %, Days To Cover > 5, Cost To Borrow en pic, Utilisation à 100%).
* **Divergence Microstructurelle :** Détection automatique d'anomalies où le volume d'options Call augmente drastiquement tandis que le volume de short selling continue, annonçant une rupture de liquidité imminente pour les vendeurs à découvert.

---

## 7. WORKFLOWS TRADER & EXÉCUTION

Automatisation des routines d'analyse pour transformer les données brutes en signaux d'exécution immédiats, avec un routage de pointe.

* **Bridge d'Exécution Multi-Plateformes :** Maintien de l'API Alpaca pour l'équité US, complété par une intégration MetaTrader 5 (MT5) via Python pour l'exécution directe des Futures et du Forex (adapté aux environnements FTMO).
* **Workflow Pré-Market (07:00 - 09:30 EST) :** Tableau de bord unifié listant les gaps de nuit (ES, NQ), le glissement de la structure à terme du VIX, et le réajustement pré-open du Gamma Flip pour établir le biais directionnel du jour.
* **Sweep Detection & Options Flow :** Suivi en direct du carnet d'ordres pour détecter les achats agressifs institutionnels hors de la monnaie (Unusual Options Activity), permettant au trader de se positionner en amont des événements de volatilité ou des annonces d'earnings.