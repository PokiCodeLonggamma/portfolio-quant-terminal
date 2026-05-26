"""Scraper Finviz — récupère les tickers à haut short interest + données institutionnelles.

Deux fonctions principales :
1. screen_high_short_interest() — screener Finviz pour SI > seuil
2. get_ticker_details() — page ticker pour Inst Own, Inst Trans, sector, etc.

Pas d'API, pas de clé. Rate-limit respecté avec delays.
"""

import re
import time
import logging
from typing import Optional

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
}
BASE = "https://finviz.com"

# Délai entre requêtes pour éviter le ban
REQUEST_DELAY = 1.5


def _get(url: str) -> Optional[BeautifulSoup]:
    """GET avec retry simple et rate limiting."""
    for attempt in range(3):
        try:
            time.sleep(REQUEST_DELAY)
            resp = requests.get(url, headers=HEADERS, timeout=15)
            if resp.status_code == 403:
                logger.warning("Finviz 403 — rate limited, attente 30s")
                time.sleep(30)
                continue
            resp.raise_for_status()
            return BeautifulSoup(resp.text, "lxml")
        except requests.RequestException as e:
            logger.warning(f"Finviz request failed (attempt {attempt+1}): {e}")
            time.sleep(5)
    return None


def _parse_pct(val: str) -> Optional[float]:
    """Parse '35.20%' → 0.352 ou '-2.10%' → -0.021."""
    if not val or val == "-":
        return None
    val = val.strip().replace("%", "").replace(",", "")
    try:
        return float(val) / 100
    except ValueError:
        return None


def _parse_number(val: str) -> Optional[float]:
    """Parse '1.23B' → 1_230_000_000, '45.6M' → 45_600_000."""
    if not val or val == "-":
        return None
    val = val.strip().replace(",", "")
    multipliers = {"B": 1e9, "M": 1e6, "K": 1e3, "T": 1e12}
    for suffix, mult in multipliers.items():
        if val.endswith(suffix):
            try:
                return float(val[:-1]) * mult
            except ValueError:
                return None
    try:
        return float(val)
    except ValueError:
        return None


def screen_high_short_interest(min_short_float: float = 0.20) -> list[str]:
    """Retourne la liste des tickers avec Short Float > seuil depuis le screener Finviz.

    Finviz encode les filtres de short float :
      sh_short_o30 = >30%, sh_short_o25 = >25%, sh_short_o20 = >20%
    """
    if min_short_float >= 0.30:
        filt = "sh_short_o30"
    elif min_short_float >= 0.25:
        filt = "sh_short_o25"
    elif min_short_float >= 0.20:
        filt = "sh_short_o20"
    elif min_short_float >= 0.15:
        filt = "sh_short_o15"
    else:
        filt = "sh_short_o10"

    tickers = []
    page = 1  # Finviz pagine par 20 (r=1, r=21, r=41...)

    while True:
        r_param = (page - 1) * 20 + 1
        url = f"{BASE}/screener.ashx?v=152&f={filt}&r={r_param}"
        soup = _get(url)
        if not soup:
            break

        # Les tickers sont dans les liens de la table #screener-views-table
        rows = soup.select("table.screener_table tr.styled-row, table.screener_table tr.styled-row-1")
        if not rows:
            # Essai alternatif — Finviz change parfois ses classes CSS
            rows = soup.select("#screener-views-table tr")[1:]  # skip header

        if not rows:
            break

        page_tickers = []
        for row in rows:
            cols = row.find_all("td")
            if len(cols) >= 2:
                ticker_link = cols[1].find("a")
                if ticker_link:
                    page_tickers.append(ticker_link.text.strip())

        if not page_tickers:
            break

        tickers.extend(page_tickers)
        logger.info(f"Finviz screener page {page}: {len(page_tickers)} tickers")

        # Si moins de 20 résultats, c'est la dernière page
        if len(page_tickers) < 20:
            break

        page += 1

        # Safety cap
        if page > 15:
            break

    logger.info(f"Finviz screening total: {len(tickers)} tickers avec SI > {min_short_float:.0%}")
    return tickers


def get_ticker_details(ticker: str) -> dict:
    """Scrape la page Finviz d'un ticker pour extraire les métriques clés.

    Retourne dict avec : short_float, inst_own, inst_trans, market_cap,
    price, sector, industry, country, avg_volume, etc.
    """
    url = f"{BASE}/quote.ashx?t={ticker}&ty=c&p=d&b=1"
    soup = _get(url)
    if not soup:
        return {"ticker": ticker, "error": "fetch_failed"}

    data = {"ticker": ticker}

    # Parse la table de métriques (snapshot-table2)
    # Finviz utilise des paires clé-valeur dans des <td>
    table = soup.find("table", class_="snapshot-table2")
    if not table:
        # Fallback : chercher tous les td avec la classe snapshot-td2
        cells = soup.find_all("td", class_="snapshot-td2")
        if not cells:
            return data

        # Les cellules alternent label/value
        for i in range(0, len(cells) - 1, 2):
            label = cells[i].text.strip()
            value = cells[i + 1].text.strip()
            _map_finviz_field(data, label, value)
    else:
        rows = table.find_all("tr")
        for row in rows:
            cells = row.find_all("td")
            # Les cellules sont en paires : [label, value, label, value, ...]
            for i in range(0, len(cells) - 1, 2):
                label = cells[i].text.strip()
                value = cells[i + 1].text.strip()
                _map_finviz_field(data, label, value)

    return data


def _map_finviz_field(data: dict, label: str, value: str) -> None:
    """Mappe un champ Finviz vers notre dict normalisé."""
    mapping = {
        "Short Float": ("short_float", _parse_pct),
        "Short Ratio": ("days_to_cover", lambda v: float(v) if v and v != "-" else None),
        "Inst Own": ("inst_own_pct", _parse_pct),
        "Inst Trans": ("inst_trans_pct", _parse_pct),
        "Market Cap": ("market_cap", _parse_number),
        "Price": ("price", lambda v: float(v) if v and v != "-" else None),
        "Sector": ("sector", lambda v: v if v != "-" else None),
        "Industry": ("industry", lambda v: v if v != "-" else None),
        "Country": ("country", lambda v: v if v != "-" else None),
        "Avg Volume": ("avg_volume", _parse_number),
        "Shares Short": ("shares_short", _parse_number),
        "Shs Float": ("shares_float", _parse_number),
        "Shs Outstand": ("shares_outstanding", _parse_number),
        "Insider Own": ("insider_own_pct", _parse_pct),
        "Insider Trans": ("insider_trans_pct", _parse_pct),
        "Earnings Date": ("earnings_date", lambda v: v if v != "-" else None),
        "Volatility": ("volatility", lambda v: v if v != "-" else None),
    }

    if label in mapping:
        key, parser = mapping[label]
        try:
            data[key] = parser(value)
        except (ValueError, TypeError):
            data[key] = None


def screen_with_details(min_short_float: float = 0.20) -> list[dict]:
    """Pipeline complet : screener + détails pour chaque ticker."""
    tickers = screen_high_short_interest(min_short_float)
    results = []
    for i, ticker in enumerate(tickers):
        logger.info(f"[{i+1}/{len(tickers)}] Fetching details for {ticker}")
        details = get_ticker_details(ticker)
        if details.get("market_cap") and details["market_cap"] > 0:
            results.append(details)
    return results
