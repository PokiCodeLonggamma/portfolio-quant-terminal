"""Options flow analysis via yfinance — gratuit, pas d'API key.

Calcule pour chaque ticker :
- Put/Call ratio (OI-weighted)
- Total Call OI / Put OI
- Variation de l'OI Call vs snapshot précédent (via SQLite)
- Détection d'anomalies de volume (proxy pour unusual activity)
"""

import logging
from datetime import date, timedelta
from typing import Optional

import yfinance as yf

from src.storage.database import get_previous_options

logger = logging.getLogger(__name__)


def get_options_data(ticker: str) -> dict:
    """Analyse les options pour un ticker donné.

    On regarde les 4 prochaines expirations pour avoir un P/C ratio
    représentatif sans être pollué par des expirations très lointaines.
    """
    result = {
        "ticker": ticker,
        "put_call_ratio": None,
        "total_call_oi": 0,
        "total_put_oi": 0,
        "call_oi_change_pct": None,
        "unusual_activity": False,
        "unusual_details": None,
    }

    try:
        t = yf.Ticker(ticker)
        expirations = t.options
    except Exception as e:
        logger.warning(f"Options fetch failed for {ticker}: {e}")
        return result

    if not expirations:
        logger.debug(f"No options available for {ticker}")
        return result

    # Prendre les 4 prochaines expirations (court/moyen terme)
    near_expirations = expirations[:4]

    total_call_oi = 0
    total_put_oi = 0
    total_call_volume = 0
    total_put_volume = 0
    max_call_vol_oi_ratio = 0.0
    unusual_strike = None

    for exp in near_expirations:
        try:
            chain = t.option_chain(exp)
        except Exception:
            continue

        calls = chain.calls
        puts = chain.puts

        if calls is not None and not calls.empty:
            call_oi = calls["openInterest"].fillna(0).sum()
            call_vol = calls["volume"].fillna(0).sum()
            total_call_oi += int(call_oi)
            total_call_volume += int(call_vol)

            # Détection d'unusual activity : volume >> OI sur un strike OTM
            for _, row in calls.iterrows():
                oi = row.get("openInterest", 0) or 0
                vol = row.get("volume", 0) or 0
                if oi > 100 and vol > 0:
                    ratio = vol / oi
                    if ratio > max_call_vol_oi_ratio:
                        max_call_vol_oi_ratio = ratio
                        unusual_strike = {
                            "type": "CALL",
                            "strike": row.get("strike"),
                            "expiration": exp,
                            "volume": int(vol),
                            "oi": int(oi),
                            "ratio": round(ratio, 1),
                        }

        if puts is not None and not puts.empty:
            put_oi = puts["openInterest"].fillna(0).sum()
            put_vol = puts["volume"].fillna(0).sum()
            total_put_oi += int(put_oi)
            total_put_volume += int(put_vol)

    result["total_call_oi"] = total_call_oi
    result["total_put_oi"] = total_put_oi

    if total_call_oi > 0:
        result["put_call_ratio"] = round(total_put_oi / total_call_oi, 3)

    # Unusual activity : vol/OI > 5x sur un strike
    if max_call_vol_oi_ratio > 5.0:
        result["unusual_activity"] = True
        result["unusual_details"] = unusual_strike

    # Calcul du delta OI Call vs snapshot précédent
    today = date.today().isoformat()
    prev = get_previous_options(ticker, today)
    if prev and prev.get("total_call_oi") and prev["total_call_oi"] > 0:
        delta = (total_call_oi - prev["total_call_oi"]) / prev["total_call_oi"]
        result["call_oi_change_pct"] = round(delta, 3)

    return result
