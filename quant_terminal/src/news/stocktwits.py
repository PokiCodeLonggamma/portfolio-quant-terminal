"""Stocktwits cashtag monitor — free alternative to paid Twitter/X API.

Endpoint
--------
GET https://api.stocktwits.com/api/2/streams/symbol/<SYMBOL>.json
  - No authentication required
  - Rate-limited (~200 req / 30 min per IP)
  - Returns 30 most recent messages with sentiment when tagged

We expose
---------
* `fetch_cashtag(ticker, *, limit=30)` -> DataFrame[ts, body, user, sentiment_bull,
  sentiment_bear, likes]
* `aggregate_cashtag(tickers)` -> wide-format heatmap-friendly DataFrame.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

import pandas as pd
import requests

from src.utils.cache import read as cache_read, write as cache_write
from src.utils.logging import get_logger

log = get_logger(__name__)

_BASE = "https://api.stocktwits.com/api/2/streams/symbol"
_CACHE_NS = "stocktwits"
_CACHE_TTL = 60 * 5   # 5 min — they update fast


def _ua() -> dict[str, str]:
    return {"User-Agent": "quant-terminal/0.1 (+stocktwits cashtag)"}


def fetch_cashtag(ticker: str, *, limit: int = 30) -> pd.DataFrame:
    """Return up to `limit` recent posts for $TICKER. Empty DF on failure."""
    cache_key = f"{ticker.upper()}|{limit}"
    cached = cache_read(cache_key, namespace=_CACHE_NS, max_age_seconds=_CACHE_TTL)
    if cached is not None and not cached.empty:
        return cached.copy()
    try:
        url = f"{_BASE}/{ticker.upper()}.json"
        resp = requests.get(url, headers=_ua(), params={"limit": limit}, timeout=10)
        if resp.status_code == 429:
            log.info("Stocktwits 429 (rate-limited) for %s", ticker)
            return pd.DataFrame()
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:
        log.warning("Stocktwits fetch failed for %s: %s", ticker, exc)
        return pd.DataFrame()

    rows: list[dict[str, Any]] = []
    for msg in (data.get("messages") or [])[:limit]:
        sent = (msg.get("entities") or {}).get("sentiment") or {}
        sent_basic = sent.get("basic") if isinstance(sent, dict) else None
        rows.append({
            "ticker": ticker.upper(),
            "ts": pd.to_datetime(msg.get("created_at"), errors="coerce"),
            "body": str(msg.get("body", ""))[:280],
            "user": (msg.get("user") or {}).get("username"),
            "user_followers": (msg.get("user") or {}).get("followers"),
            "sentiment_bull": 1 if sent_basic == "Bullish" else 0,
            "sentiment_bear": 1 if sent_basic == "Bearish" else 0,
            "likes": (msg.get("likes") or {}).get("total", 0),
        })
    df = pd.DataFrame(rows)
    if not df.empty:
        try:
            cache_write(cache_key, df, namespace=_CACHE_NS)
        except Exception:
            pass
    return df


def aggregate_cashtag(tickers: list[str], *, lookback_hours: int = 24) -> pd.DataFrame:
    """Per-ticker rollup of bullish/bearish post counts in the lookback window."""
    if not tickers:
        return pd.DataFrame()
    cutoff = datetime.utcnow() - timedelta(hours=lookback_hours)
    rows = []
    for t in tickers:
        df = fetch_cashtag(t, limit=30)
        if df.empty:
            rows.append({"ticker": t, "bull": 0, "bear": 0,
                         "neutral": 0, "n_posts": 0, "bull_ratio": 0.0})
            continue
        sub = df[pd.to_datetime(df["ts"]).dt.tz_localize(None) >= cutoff]
        bull = int(sub["sentiment_bull"].sum())
        bear = int(sub["sentiment_bear"].sum())
        total = len(sub)
        neutral = max(0, total - bull - bear)
        rows.append({
            "ticker": t,
            "bull": bull,
            "bear": bear,
            "neutral": neutral,
            "n_posts": total,
            "bull_ratio": (bull / (bull + bear)) if (bull + bear) > 0 else 0.0,
        })
    return pd.DataFrame(rows).sort_values("n_posts", ascending=False).reset_index(drop=True)
