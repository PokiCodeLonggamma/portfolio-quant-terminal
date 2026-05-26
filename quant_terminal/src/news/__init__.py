"""News flow — Cluster 4 (module J).

* RSS-based headline scraper (Google News).
* Lightweight rule-based finance-sentiment scorer.
* Aggregation helpers + Streamlit dashboards.
"""
from __future__ import annotations

from src.news.aggregator import aggregate_news
from src.news.rss_fetcher import fetch_news
from src.news.sentiment import score_headline, score_headlines

__all__ = [
    "aggregate_news",
    "fetch_news",
    "score_headline",
    "score_headlines",
]
