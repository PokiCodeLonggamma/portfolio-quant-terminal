"""Google News RSS fetcher.

Public API
----------
* `fetch_news(ticker, lookback_days=7)` — returns a DataFrame with columns
  ``ticker, ts, title, link, source`` of recent headlines for `ticker`.
* `fetch_news_multi(tickers, lookback_days=7)` — concatenated frame for
  several tickers.

Why Google News RSS?
--------------------
* No API key.
* Stable URL pattern, fast (XML <5 KB per call).
* Headlines are clean enough for a rule-based sentiment pass.

Caveats
-------
* Google occasionally returns HTML instead of XML when rate-limited.
  ``feedparser`` handles both, but we still defensively guard for empty
  entry lists.
* Cache namespace ``news_rss``, 1-hour TTL.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any
from urllib.parse import quote_plus

import pandas as pd

from src.utils.cache import read as cache_read, write as cache_write
from src.utils.logging import get_logger

log = get_logger(__name__)

_CACHE_NS = "news_rss"
_CACHE_TTL_SECONDS = 60 * 60  # 1h

_COLUMNS = ["ticker", "ts", "title", "link", "source"]

_RSS_TEMPLATE = (
    "https://news.google.com/rss/search?q={query}&hl=en-US&gl=US&ceid=US:en"
)


def _safe_dataframe() -> pd.DataFrame:
    return pd.DataFrame(columns=_COLUMNS)


def _build_query(ticker: str) -> str:
    # Combine ticker + "stock" to bias toward financial coverage.
    return quote_plus(f"{ticker} stock")


def _parse_ts(entry: Any) -> datetime | None:
    """Pull a parsed timestamp from a feedparser entry."""
    raw = entry.get("published_parsed") or entry.get("updated_parsed")
    if raw is not None:
        try:
            return datetime(*raw[:6])
        except (TypeError, ValueError):
            pass
    raw_str = entry.get("published") or entry.get("updated")
    if raw_str:
        try:
            return pd.to_datetime(raw_str, errors="coerce", utc=True).to_pydatetime().replace(tzinfo=None)  # type: ignore[union-attr]
        except Exception:
            return None
    return None


def _entry_source(entry: Any) -> str:
    src = entry.get("source")
    if isinstance(src, dict):
        return str(src.get("title") or src.get("href") or "Google News")
    if hasattr(src, "title"):
        return str(getattr(src, "title", "Google News"))
    return "Google News"


def fetch_news(
    ticker: str,
    lookback_days: int = 7,
    *,
    feedparser_module=None,
    max_items: int = 60,
) -> pd.DataFrame:
    """Return recent headlines for `ticker` as a DataFrame.

    Parameters
    ----------
    ticker
        Universe ticker — used verbatim in the Google News query.
    lookback_days
        Older entries are filtered out.
    feedparser_module
        Optional override (used by tests).
    max_items
        Hard cap on the number of headlines returned.
    """
    if not ticker or not ticker.strip():
        return _safe_dataframe()
    ticker = ticker.strip().upper()
    cache_key = f"{ticker}|{lookback_days}"
    cached = cache_read(cache_key, namespace=_CACHE_NS, max_age_seconds=_CACHE_TTL_SECONDS)
    if cached is not None and not cached.empty:
        try:
            df = cached.copy()
            df["ts"] = pd.to_datetime(df["ts"], errors="coerce")
            return df.head(max_items)
        except Exception:
            pass

    if feedparser_module is None:
        try:
            import feedparser
            feedparser_module = feedparser
        except ImportError:
            log.error("feedparser not installed; cannot fetch news")
            return _safe_dataframe()

    url = _RSS_TEMPLATE.format(query=_build_query(ticker))
    try:
        feed = feedparser_module.parse(url)
    except Exception as exc:
        log.debug("rss parse failed for %s: %s", ticker, exc)
        return _safe_dataframe()
    entries = getattr(feed, "entries", None) or feed.get("entries", []) if hasattr(feed, "get") else []
    if not entries:
        return _safe_dataframe()

    cutoff = datetime.utcnow() - timedelta(days=int(lookback_days))
    rows: list[dict] = []
    for entry in entries:
        ts = _parse_ts(entry)
        if ts is None:
            continue
        if ts < cutoff:
            continue
        title = str(entry.get("title") or "").strip()
        link = str(entry.get("link") or "").strip()
        if not title:
            continue
        rows.append({
            "ticker": ticker,
            "ts": ts,
            "title": title,
            "link": link,
            "source": _entry_source(entry),
        })
        if len(rows) >= max_items:
            break

    df = pd.DataFrame(rows, columns=_COLUMNS)
    if not df.empty:
        df = df.sort_values("ts", ascending=False).reset_index(drop=True)
        try:
            to_cache = df.copy()
            to_cache["ts"] = to_cache["ts"].astype(str)
            cache_write(cache_key, to_cache, namespace=_CACHE_NS)
        except Exception as exc:
            log.debug("rss cache write failed for %s: %s", ticker, exc)
    return df


def fetch_news_multi(tickers: list[str], lookback_days: int = 7) -> pd.DataFrame:
    """Concatenated news across tickers."""
    frames = []
    for tk in tickers:
        df = fetch_news(tk, lookback_days=lookback_days)
        if not df.empty:
            frames.append(df)
    if not frames:
        return _safe_dataframe()
    return pd.concat(frames, ignore_index=True).sort_values("ts", ascending=False)
