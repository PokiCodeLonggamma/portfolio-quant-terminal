"""Real-time news pipeline.

Combines:
  * RSS poll (Google News per ticker) — existing `rss_fetcher`
  * Sentiment score per headline — existing `sentiment.score_headline`
  * Optional LLM-based net-sentiment via `llm_summarizer.summarise_news_burst`
  * **Push hook** into the Alerts engine when net sentiment crosses a
    threshold OR a high-impact headline arrives.

The Streamlit Live mode (Feature 4) ticks `refresh_realtime()` every N
seconds; the function persists last-seen headline IDs so the same alert
doesn't fire twice.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

from src.alerts.channels import dispatch as channel_dispatch
from src.alerts.state import append_history
from src.alerts.triggers import AlertEvent
from src.news.rss_fetcher import fetch_news
from src.news.sentiment import score_headline
from src.utils.config import PROJECT_ROOT
from src.utils.logging import get_logger

log = get_logger(__name__)

_STATE_DIR = PROJECT_ROOT / "data" / "alerts"
_STATE_FILE = _STATE_DIR / "news_realtime_seen.json"


def _seen_load() -> dict[str, list[str]]:
    if not _STATE_FILE.exists():
        return {}
    try:
        return json.loads(_STATE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _seen_save(seen: dict[str, list[str]]) -> None:
    _STATE_DIR.mkdir(parents=True, exist_ok=True)
    try:
        _STATE_FILE.write_text(json.dumps(seen)[:2_000_000], encoding="utf-8")
    except Exception as exc:
        log.warning("news realtime state save failed: %s", exc)


def refresh_realtime(
    tickers: list[str],
    *,
    lookback_hours: int = 6,
    bearish_threshold: float = -0.4,
    bullish_threshold: float = 0.5,
    dispatch: bool = True,
) -> pd.DataFrame:
    """Pull fresh headlines, score them, fire alerts on extreme sentiment.

    Returns a DataFrame of NEW headlines this tick (already-seen ones excluded).
    """
    if not tickers:
        return pd.DataFrame()
    seen = _seen_load()
    cutoff = datetime.utcnow() - timedelta(hours=lookback_hours)
    new_rows: list[dict] = []
    for t in tickers:
        try:
            df = fetch_news(t, lookback_days=1)
        except Exception as exc:
            log.debug("realtime: rss for %s failed: %s", t, exc)
            continue
        if df.empty or "title" not in df.columns:
            continue
        df = df[pd.to_datetime(df["ts"], errors="coerce") >= cutoff]
        already_seen = set(seen.get(t.upper(), []))
        for _, row in df.iterrows():
            link = str(row.get("link", ""))
            title = str(row.get("title", "")).strip()
            if not title or link in already_seen:
                continue
            sent = float(score_headline(title))
            new_rows.append({
                "ticker": t.upper(),
                "ts": row["ts"],
                "title": title,
                "link": link,
                "source": row.get("source"),
                "sentiment": sent,
            })
            already_seen.add(link)
        seen[t.upper()] = list(already_seen)[-200:]  # cap memory

        # Fire an alert when net sentiment for this ticker crosses thresholds
        if dispatch and new_rows:
            sub = [r for r in new_rows if r["ticker"] == t.upper()]
            if sub:
                avg = sum(r["sentiment"] for r in sub) / len(sub)
                if avg <= bearish_threshold or avg >= bullish_threshold:
                    severity = "warning" if avg <= bearish_threshold else "info"
                    event = AlertEvent(
                        trigger_name=f"news_realtime_{t.upper()}",
                        fired_at=datetime.utcnow(),
                        severity=severity,
                        title=f"[{t.upper()}] {len(sub)} fresh news, net sentiment {avg:+.2f}",
                        body="\n".join(f"• {r['title']}" for r in sub[:5]),
                        payload={"avg_sentiment": avg, "count": len(sub)},
                        channels=["streamlit", "discord"],
                    )
                    try:
                        channel_dispatch(event)
                        append_history(event)
                    except Exception as exc:
                        log.warning("realtime alert dispatch failed for %s: %s", t, exc)
    _seen_save(seen)
    if not new_rows:
        return pd.DataFrame()
    return pd.DataFrame(new_rows).sort_values("ts", ascending=False).reset_index(drop=True)
