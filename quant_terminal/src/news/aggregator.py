"""News aggregator — daily article counts + mean sentiment per ticker.

Public API
----------
* `aggregate_news(tickers, lookback_days=7)` — return a long-format
  ``pd.DataFrame`` with columns ``ticker, day, article_count,
  mean_sentiment``.  The frame is suitable for the heatmap renderer.

Internally calls :func:`src.news.rss_fetcher.fetch_news` for each ticker
and :func:`src.news.sentiment.score_headline` to enrich the headlines.
Tests inject a ``rss_fetcher_fn`` to skip the network.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Callable

import pandas as pd

from src.news.rss_fetcher import fetch_news
from src.news.sentiment import score_headline
from src.utils.logging import get_logger

log = get_logger(__name__)

_AGG_COLUMNS = ["ticker", "day", "article_count", "mean_sentiment"]


def _empty_agg() -> pd.DataFrame:
    return pd.DataFrame(columns=_AGG_COLUMNS)


def aggregate_news(
    tickers: list[str],
    lookback_days: int = 7,
    *,
    rss_fetcher_fn: Callable[..., pd.DataFrame] | None = None,
) -> pd.DataFrame:
    """Aggregate per-day article counts + mean sentiment per ticker.

    Output
    ------
    Long-format DataFrame with columns:
        * ``ticker``         — universe ticker
        * ``day``            — ``date`` of the article cluster
        * ``article_count``  — number of articles found that day
        * ``mean_sentiment`` — mean of :func:`score_headline` for that day
    """
    if not tickers:
        return _empty_agg()
    fetcher = rss_fetcher_fn or fetch_news
    frames: list[pd.DataFrame] = []
    for tk in tickers:
        try:
            df = fetcher(tk, lookback_days=lookback_days)
        except TypeError:
            df = fetcher(tk)
        except Exception as exc:
            log.debug("rss fetch failed for %s: %s", tk, exc)
            continue
        if df is None or df.empty:
            continue
        frames.append(df)

    if not frames:
        return _empty_agg()

    full = pd.concat(frames, ignore_index=True)
    if "title" not in full.columns:
        return _empty_agg()
    full["sentiment"] = full["title"].astype(str).map(score_headline)
    full["ts"] = pd.to_datetime(full["ts"], errors="coerce")
    full = full.dropna(subset=["ts"])
    full["day"] = full["ts"].dt.date

    agg = full.groupby(["ticker", "day"], as_index=False).agg(
        article_count=("title", "count"),
        mean_sentiment=("sentiment", "mean"),
    )
    return agg.sort_values(["ticker", "day"]).reset_index(drop=True)


def aggregate_to_matrix(
    agg_df: pd.DataFrame,
    *,
    fill_value_count: int = 0,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Pivot the long-format agg into (count_matrix, sentiment_matrix).

    Rows = ticker, columns = day.  Missing cells are filled with
    ``fill_value_count`` for the count matrix and ``NaN`` for sentiment.
    Used by the heatmap renderer.
    """
    if agg_df is None or agg_df.empty:
        empty = pd.DataFrame()
        return empty, empty
    counts = agg_df.pivot(
        index="ticker", columns="day", values="article_count",
    ).fillna(fill_value_count).astype(int)
    senti = agg_df.pivot(
        index="ticker", columns="day", values="mean_sentiment",
    )
    return counts, senti
