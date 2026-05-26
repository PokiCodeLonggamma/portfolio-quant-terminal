"""Analyst rating changes — Financial Modeling Prep (FMP) API.

Endpoints used (FMP free tier OK for limited symbols / daily quota):
  * /v3/upgrades-downgrades/{symbol}
  * /v3/upgrades-downgrades-rss-feed                — cross-market feed
  * /v3/price-target/{symbol}                       — current consensus target
  * /v3/grade/{symbol}                              — historical grade transitions

We expose a single DataFrame for downstream display, plus a per-ticker
summary helper. All calls are cached (12h TTL — analyst moves are slow).

Falls back to an empty DataFrame when ``FMP_API_KEY`` is missing rather
than raising — the dashboard handles the empty case explicitly.
"""
from __future__ import annotations

import os
from datetime import date, timedelta

import pandas as pd
import requests

from src.utils.cache import read as cache_read, write as cache_write
from src.utils.logging import get_logger

log = get_logger(__name__)


_BASE = "https://financialmodelingprep.com/api/v3"
_CACHE_NS = "analyst_ratings"
_CACHE_TTL = 60 * 60 * 12          # 12 hours


def _api_key() -> str:
    return os.getenv("FMP_API_KEY", "").strip()


def _get_json(url: str, params: dict | None = None) -> list | dict | None:
    params = dict(params or {})
    key = _api_key()
    if not key:
        return None
    params["apikey"] = key
    try:
        resp = requests.get(url, params=params, timeout=15)
        if resp.status_code != 200:
            log.debug("FMP %s → %s", url, resp.status_code)
            return None
        return resp.json()
    except Exception as exc:
        log.debug("FMP request failed (%s): %s", url, exc)
        return None


# ---------------------------------------------------------------------------
# Per-ticker rating history
# ---------------------------------------------------------------------------
def get_upgrades_downgrades(
    ticker: str, *, lookback_days: int = 90,
) -> pd.DataFrame:
    """Recent rating actions for a single ticker.

    Columns: date, publishedDate, action (Upgrade / Downgrade / Initiated / …),
    newGrade, previousGrade, gradingCompany, priceTarget, ticker.
    """
    if not ticker:
        return pd.DataFrame()
    cache_key = f"upgr|{ticker.upper()}|{lookback_days}"
    cached = cache_read(cache_key, namespace=_CACHE_NS, max_age_seconds=_CACHE_TTL)
    if cached is not None and not cached.empty:
        return cached

    data = _get_json(f"{_BASE}/upgrades-downgrades/{ticker.upper()}")
    if not data:
        return pd.DataFrame()
    df = pd.DataFrame(data)
    if df.empty:
        return df
    df["publishedDate"] = pd.to_datetime(df.get("publishedDate"), errors="coerce")
    cutoff = pd.Timestamp(date.today() - timedelta(days=lookback_days))
    df = df[df["publishedDate"] >= cutoff].copy()
    df["ticker"] = ticker.upper()
    keep = [c for c in [
        "publishedDate", "newsTitle", "newsURL", "newsPublisher", "newGrade",
        "previousGrade", "gradingCompany", "action", "priceTarget", "ticker",
    ] if c in df.columns]
    df = df[keep].sort_values("publishedDate", ascending=False).reset_index(drop=True)
    cache_write(cache_key, df, namespace=_CACHE_NS)
    return df


def get_rating_changes_multi(
    tickers: list[str], *, lookback_days: int = 30,
) -> pd.DataFrame:
    """Flat DataFrame of upgrades/downgrades for a list of tickers, latest first."""
    if not tickers:
        return pd.DataFrame()
    parts = []
    for t in tickers:
        df = get_upgrades_downgrades(t, lookback_days=lookback_days)
        if df is not None and not df.empty:
            parts.append(df)
    if not parts:
        return pd.DataFrame()
    out = pd.concat(parts, ignore_index=True)
    if "publishedDate" in out.columns:
        out = out.sort_values("publishedDate", ascending=False).reset_index(drop=True)
    return out


# ---------------------------------------------------------------------------
# Price target consensus
# ---------------------------------------------------------------------------
def get_price_target(ticker: str) -> dict | None:
    """Latest consensus price target on FMP — None if missing / no key."""
    if not ticker:
        return None
    cache_key = f"pt|{ticker.upper()}"
    cached = cache_read(cache_key, namespace=_CACHE_NS, max_age_seconds=_CACHE_TTL)
    if cached is not None and not cached.empty:
        return cached.iloc[0].to_dict()
    data = _get_json(f"{_BASE}/price-target/{ticker.upper()}")
    if not data or not isinstance(data, list) or not data:
        return None
    latest = data[0]
    df = pd.DataFrame([latest])
    cache_write(cache_key, df, namespace=_CACHE_NS)
    return latest


def get_consensus_targets(tickers: list[str]) -> pd.DataFrame:
    """One row per ticker with the latest consensus target."""
    if not tickers:
        return pd.DataFrame()
    rows = []
    for t in tickers:
        d = get_price_target(t)
        if not d:
            continue
        rows.append({
            "ticker":              t.upper(),
            "consensus_target":    d.get("priceTarget"),
            "analyst_name":        d.get("analystName"),
            "analyst_company":     d.get("analystCompany"),
            "rating":              d.get("newGrade") or d.get("rating"),
            "published_date":      d.get("publishedDate"),
        })
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows).sort_values("published_date", ascending=False).reset_index(drop=True)


def _action_color(action: str) -> str:
    a = (action or "").lower()
    if any(k in a for k in ("upgrade", "raised", "buy", "outperform", "overweight")):
        return "🟢 BUY"
    if any(k in a for k in ("downgrade", "cut", "sell", "underperform", "underweight")):
        return "🔴 SELL"
    if "initiat" in a or "coverage" in a:
        return "🟡 INIT"
    return "⚪ HOLD"


def normalize_for_display(df: pd.DataFrame) -> pd.DataFrame:
    """Clean / re-label columns for a Streamlit dataframe."""
    if df is None or df.empty:
        return pd.DataFrame()
    out = df.copy()
    if "publishedDate" in out.columns:
        out["date"] = pd.to_datetime(out["publishedDate"], errors="coerce").dt.strftime("%Y-%m-%d")
    if "action" in out.columns:
        out["signal"] = out["action"].apply(_action_color)
    show_cols = [c for c in [
        "date", "ticker", "signal", "action", "newGrade", "previousGrade",
        "gradingCompany", "priceTarget", "newsTitle",
    ] if c in out.columns]
    out = out[show_cols].rename(columns={
        "newGrade": "to",
        "previousGrade": "from",
        "gradingCompany": "firm",
        "priceTarget": "target",
        "newsTitle": "headline",
    })
    return out


__all__ = [
    "get_upgrades_downgrades", "get_rating_changes_multi",
    "get_price_target", "get_consensus_targets",
    "normalize_for_display",
]
