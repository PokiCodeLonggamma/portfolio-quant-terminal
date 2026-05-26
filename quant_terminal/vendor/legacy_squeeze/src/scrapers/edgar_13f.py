"""SEC EDGAR 13F Parser — détecte les variations d'ownership institutionnel.

Approche : pour un ticker donné, on cherche combien de fonds le détiennent
dans les 13F du trimestre courant vs le trimestre précédent.

L'API EDGAR EFTS (full-text search) est gratuite, sans clé API.
La SEC demande un User-Agent avec email — configuré dans .env.

Rate limit SEC : 10 requests/seconde max.
"""

import time
import logging
from datetime import datetime, timedelta
from typing import Optional

import requests

from config.settings import Config

logger = logging.getLogger(__name__)

SEC_HEADERS = {
    "User-Agent": Config.SEC_USER_AGENT,
    "Accept": "application/json",
}

# SEC rate limit : 10 req/s, on se met à 5 pour être safe
REQUEST_DELAY = 0.25


def _sec_get(url: str, params: dict = None) -> Optional[dict]:
    """GET sur l'API SEC avec rate limiting."""
    for attempt in range(3):
        try:
            time.sleep(REQUEST_DELAY)
            resp = requests.get(url, params=params, headers=SEC_HEADERS, timeout=15)
            if resp.status_code == 429:
                logger.warning("SEC rate limited, attente 10s")
                time.sleep(10)
                continue
            resp.raise_for_status()
            return resp.json()
        except requests.RequestException as e:
            logger.warning(f"SEC request failed (attempt {attempt+1}): {e}")
            time.sleep(2)
    return None


def _get_quarter_dates(quarter_offset: int = 0) -> tuple[str, str]:
    """Retourne (start_date, end_date) pour un trimestre.

    quarter_offset=0 : trimestre courant de filing (les 13F déposés récemment)
    quarter_offset=-1 : trimestre précédent
    """
    now = datetime.now()
    # Les 13F couvrent le trimestre précédent et sont déposés dans les 45j suivants
    # Si on est en Feb 2026, les derniers 13F couvrent Q4 2025 (Oct-Dec 2025)
    # déposés entre Jan 1 et Feb 14, 2026

    # On cherche les filings récents (dans les 60 derniers jours)
    if quarter_offset == 0:
        end = now
        start = now - timedelta(days=60)
    elif quarter_offset == -1:
        end = now - timedelta(days=60)
        start = now - timedelta(days=150)
    else:
        end = now - timedelta(days=150)
        start = now - timedelta(days=240)

    return start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")


def count_13f_holders(ticker: str, quarter_offset: int = 0) -> Optional[int]:
    """Compte le nombre de 13F filings mentionnant ce ticker pour un trimestre donné.

    Utilise l'EDGAR Full-Text Search (EFTS) pour chercher le ticker
    dans les formulaires 13F-HR déposés pendant la période.
    """
    start_date, end_date = _get_quarter_dates(quarter_offset)

    url = "https://efts.sec.gov/LATEST/search-index"
    params = {
        "q": f'"{ticker}"',
        "dateRange": "custom",
        "startdt": start_date,
        "enddt": end_date,
        "forms": "13F-HR",
    }

    data = _sec_get(url, params)
    if not data:
        return None

    total = data.get("hits", {}).get("total", {})
    if isinstance(total, dict):
        return total.get("value", 0)
    return int(total) if total else 0


def get_institutional_delta(ticker: str) -> dict:
    """Compare le nombre de holders 13F entre le trimestre actuel et le précédent.

    Retourne :
        holders_current: int
        holders_previous: int
        holders_delta: int (positif = accumulation)
        holders_delta_pct: float
        accumulating: bool
    """
    current = count_13f_holders(ticker, quarter_offset=0)
    previous = count_13f_holders(ticker, quarter_offset=-1)

    result = {
        "ticker": ticker,
        "holders_current": current,
        "holders_previous": previous,
        "holders_delta": None,
        "holders_delta_pct": None,
        "accumulating": False,
    }

    if current is not None and previous is not None and previous > 0:
        delta = current - previous
        result["holders_delta"] = delta
        result["holders_delta_pct"] = delta / previous
        result["accumulating"] = delta > 0

    return result


def get_company_filings(ticker: str, form_type: str = "13F-HR", limit: int = 5) -> list[dict]:
    """Retourne les derniers filings d'un type donné pour un ticker.

    Utile pour monitorer les 13D/G (prises de position >5%).
    """
    url = "https://efts.sec.gov/LATEST/search-index"
    params = {
        "q": f'"{ticker}"',
        "forms": form_type,
        "from": 0,
        "size": limit,
    }

    data = _sec_get(url, params)
    if not data:
        return []

    hits = data.get("hits", {}).get("hits", [])
    results = []
    for hit in hits:
        source = hit.get("_source", {})
        results.append({
            "filing_date": source.get("file_date"),
            "form_type": source.get("form_type"),
            "entity_name": source.get("entity_name"),
            "file_number": source.get("file_num"),
        })

    return results


def check_13d_activity(ticker: str, days_back: int = 90) -> list[dict]:
    """Détecte les filings 13D récents (=accumulation agressive >5% avec intention activiste)."""
    start = (datetime.now() - timedelta(days=days_back)).strftime("%Y-%m-%d")
    end = datetime.now().strftime("%Y-%m-%d")

    url = "https://efts.sec.gov/LATEST/search-index"
    params = {
        "q": f'"{ticker}"',
        "dateRange": "custom",
        "startdt": start,
        "enddt": end,
        "forms": "SC 13D,SC 13D/A",
    }

    data = _sec_get(url, params)
    if not data:
        return []

    hits = data.get("hits", {}).get("hits", [])
    return [
        {
            "entity": h.get("_source", {}).get("entity_name"),
            "date": h.get("_source", {}).get("file_date"),
        }
        for h in hits
    ]
