"""arq worker — async background job runner.

Run with::

    arq api.workers.worker.WorkerSettings

Jobs:
  - **refresh_hot_chains** — every 60s. Refresh options chains for the
    bookmarked tickers (warms the @cached endpoints).
  - **refresh_news**       — every 5 min.
  - **refit_hmm**          — every 60 min.
  - **publish_price_tick** — every 1s. Publish a mock tick to Redis
    pub/sub channel ``qt:prices`` (consumed by /ws/prices in Phase 3).

In Phase 3 the publisher is mock random walk; Phase 4+ swaps in Alpaca
quote stream.
"""
from __future__ import annotations

import json
import logging
import random
from datetime import datetime, timedelta

import redis.asyncio as aioredis
from arq import cron

from api.deps import get_redis_url

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Default ticker baskets (could come from config later)
# ---------------------------------------------------------------------------
_HOT_OPTION_TICKERS: list[str] = ["SPY", "QQQ", "IWM", "ASTS", "RKLB", "TSLA"]
_NEWS_DEFAULT_TICKERS: list[str] = ["SPY", "QQQ", "ES=F", "NQ=F", "VIX"]
_HMM_TICKERS: list[str] = ["SPY", "QQQ", "IWM"]
_PRICE_FEED_TICKERS: list[str] = [
    "ES", "NQ", "YM", "RTY", "VX", "CL", "GC", "SI", "HG",
    "BTC", "ETH", "SPY", "QQQ", "IWM",
]

# Last-published prices for the mock random walk
_LAST: dict[str, float] = {
    "ES": 5000.0, "NQ": 18000.0, "YM": 41000.0, "RTY": 2050.0, "VX": 18.0,
    "CL": 75.0, "GC": 2050.0, "SI": 25.0, "HG": 3.8,
    "BTC": 65000.0, "ETH": 3200.0,
    "SPY": 540.0, "QQQ": 470.0, "IWM": 215.0,
}

# Redis pub/sub channel for live ticks
PRICES_CHANNEL = "qt:prices"


# ---------------------------------------------------------------------------
# Jobs
# ---------------------------------------------------------------------------
async def refresh_hot_chains(ctx: dict) -> int:
    """Warm @cached(/api/options/{ticker}/{chain|gex|vol_surface}) for hot tickers."""
    from src.services import OptionsService
    svc = OptionsService()
    refreshed = 0
    for tk in _HOT_OPTION_TICKERS:
        try:
            dump = svc.get_chain_dump(tk)
            if dump:
                refreshed += 1
        except Exception as exc:
            log.warning("refresh_hot_chains(%s) failed: %s", tk, exc)
    log.info("refresh_hot_chains: refreshed %d/%d", refreshed, len(_HOT_OPTION_TICKERS))
    return refreshed


async def refresh_news(ctx: dict) -> int:
    """Pull fresh news for the default watchlist."""
    from src.services import NewsService
    svc = NewsService()
    pulse = svc.get_latest(tickers=_NEWS_DEFAULT_TICKERS, lookback_hours=6)
    log.info("refresh_news: fetched %d items", len(pulse.items))
    return len(pulse.items)


async def refit_hmm(ctx: dict) -> dict:
    """Refit HMM for SPY/QQQ/IWM (results land in the cache once Phase 4 wires
    a write-through call from this job — for now the @cached endpoint
    discovers a stale entry on next hit)."""
    from src.services import RegimeService
    svc = RegimeService()
    out: dict[str, str] = {}
    for tk in _HMM_TICKERS:
        try:
            res = svc.fit_hmm(tk)
            out[tk] = res.current_label if res else "n/a"
        except Exception as exc:
            log.warning("refit_hmm(%s) failed: %s", tk, exc)
            out[tk] = "error"
    log.info("refit_hmm: %s", out)
    return out


async def publish_price_tick(ctx: dict) -> int:
    """Publish one tick per ticker to the Redis ``qt:prices`` channel."""
    redis: aioredis.Redis = ctx["redis"]  # type: ignore[assignment]
    n = 0
    for tk in _PRICE_FEED_TICKERS:
        last = _LAST.get(tk, 100.0)
        delta = last * random.uniform(-0.0005, 0.0005)
        new_price = round(last + delta, 4)
        _LAST[tk] = new_price
        msg = {
            "type": "tick",
            "ticker": tk,
            "price": new_price,
            "asof": datetime.utcnow().isoformat(timespec="seconds"),
            "source": "worker-mock",
        }
        try:
            await redis.publish(PRICES_CHANNEL, json.dumps(msg))
            n += 1
        except Exception as exc:
            log.debug("publish_price_tick(%s) failed: %s", tk, exc)
    return n


# ---------------------------------------------------------------------------
# WorkerSettings
# ---------------------------------------------------------------------------
async def _startup(ctx: dict) -> None:
    """Open the redis pub/sub client for the publisher job."""
    ctx["redis"] = aioredis.from_url(get_redis_url(), decode_responses=True)


async def _shutdown(ctx: dict) -> None:
    try:
        await ctx["redis"].aclose()
    except Exception:
        pass


class WorkerSettings:
    """arq WorkerSettings — picked up automatically by the CLI."""
    functions = [
        refresh_hot_chains,
        refresh_news,
        refit_hmm,
        publish_price_tick,
    ]
    cron_jobs = [
        # Every minute on the second 30 — refresh hot chains
        cron(refresh_hot_chains, minute=set(range(0, 60)), second={30}, unique=True),
        # Every 5 minutes
        cron(refresh_news, minute={0, 5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55}, second={15}, unique=True),
        # Every hour (top of the hour)
        cron(refit_hmm, minute={0}, second={45}, unique=True),
        # Publish prices every second
        cron(publish_price_tick, second=set(range(0, 60)), unique=True),
    ]
    on_startup = _startup
    on_shutdown = _shutdown
    job_timeout = timedelta(minutes=5).total_seconds()
