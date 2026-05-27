"""WebSocket /ws/prices — live price ticks with Redis pub/sub fan-out.

Phase 2 shipped a per-connection mock pusher.
Phase 3 wires up Redis pub/sub: the arq worker publishes ticks to
``qt:prices`` once per second, and every connected WebSocket client
subscribes to that channel + filters by its own per-connection ticker set.

This means:
- 1 single upstream feed (worker) → N connected clients
- Adding/removing tickers is purely client-side (no upstream churn)
- If the worker isn't running (e.g. tests, dev without arq), the handler
  falls back to a per-connection mock pusher so the UX still works.

Protocol (client → server):
    { "op": "subscribe",   "tickers": ["ES", "NQ"] }
    { "op": "unsubscribe", "tickers": ["NQ"] }
    { "op": "ping" }

Protocol (server → client):
    { "type": "subscribed", "tickers": [...] }
    { "type": "unsubscribed", "tickers": [...] }
    { "type": "tick",       "ticker": "ES", "price": 5021.25, "asof": "…",
                            "source": "worker-mock" }
    { "type": "pong",       "asof": "…" }
    { "type": "error",      "message": "…" }
"""
from __future__ import annotations

import asyncio
import json
import logging
import random
from datetime import datetime
from typing import Any

import redis.asyncio as aioredis
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from api.deps import get_redis_url

router = APIRouter(tags=["ws"])
log = logging.getLogger(__name__)

PRICES_CHANNEL = "qt:prices"


# ---------------------------------------------------------------------------
# Fallback mock generator (when no Redis worker is publishing)
# ---------------------------------------------------------------------------
_LAST_PRICES: dict[str, float] = {
    "ES": 5000.0, "NQ": 18000.0, "YM": 41000.0, "RTY": 2050.0,
    "CL": 75.0, "GC": 2050.0, "SI": 25.0, "HG": 3.8,
    "BTC": 65000.0, "ETH": 3200.0,
    "SPY": 540.0, "QQQ": 470.0, "IWM": 215.0,
}


def _mock_tick(ticker: str) -> float:
    last = _LAST_PRICES.get(ticker, 100.0)
    delta = last * random.uniform(-0.0005, 0.0005)
    new_price = round(last + delta, 4)
    _LAST_PRICES[ticker] = new_price
    return new_price


# ---------------------------------------------------------------------------
# WebSocket handler
# ---------------------------------------------------------------------------
@router.websocket("/ws/prices")
async def ws_prices(websocket: WebSocket) -> None:
    await websocket.accept()
    subscribed: set[str] = set()
    redis: aioredis.Redis | None = None
    pubsub = None

    # Try to attach to the Redis pub/sub channel. Fall back to per-connection
    # mock if Redis is unreachable.
    try:
        redis = aioredis.from_url(get_redis_url(), decode_responses=True)
        await redis.ping()
        pubsub = redis.pubsub()
        await pubsub.subscribe(PRICES_CHANNEL)
        log.info("/ws/prices: subscribed to redis channel %s", PRICES_CHANNEL)
    except Exception as exc:
        log.warning("/ws/prices: redis unavailable (%s) → mock fallback", exc)
        if pubsub is not None:
            try:
                await pubsub.aclose()
            except Exception:
                pass
        if redis is not None:
            try:
                await redis.aclose()
            except Exception:
                pass
        pubsub = None
        redis = None

    async def relay_redis_ticks() -> None:
        """Forward Redis pub/sub messages → connected client (filtered)."""
        if pubsub is None:
            return
        try:
            async for message in pubsub.listen():
                if message["type"] != "message":
                    continue
                try:
                    payload = json.loads(message["data"])
                except Exception:
                    continue
                tk = payload.get("ticker")
                if tk and tk in subscribed:
                    await websocket.send_text(json.dumps(payload))
        except asyncio.CancelledError:
            return
        except Exception as exc:
            log.debug("relay_redis_ticks ended: %s", exc)

    async def mock_pusher() -> None:
        """Fallback when no Redis — push our own mock ticks once a second."""
        try:
            while True:
                if subscribed:
                    for t in list(subscribed):
                        price = _mock_tick(t)
                        await websocket.send_text(json.dumps({
                            "type": "tick",
                            "ticker": t,
                            "price": price,
                            "asof": datetime.utcnow().isoformat(timespec="seconds"),
                            "source": "mock-fallback",
                        }))
                await asyncio.sleep(1.0)
        except asyncio.CancelledError:
            return
        except Exception:
            return

    pusher_task = (
        asyncio.create_task(relay_redis_ticks()) if pubsub
        else asyncio.create_task(mock_pusher())
    )

    try:
        while True:
            raw = await websocket.receive_text()
            try:
                msg: dict[str, Any] = json.loads(raw)
            except json.JSONDecodeError:
                await websocket.send_text(json.dumps({
                    "type": "error",
                    "message": "Invalid JSON",
                }))
                continue
            op = msg.get("op")
            if op == "subscribe":
                tickers = [str(t).upper() for t in msg.get("tickers", [])]
                subscribed.update(tickers)
                await websocket.send_text(json.dumps({
                    "type": "subscribed",
                    "tickers": sorted(subscribed),
                    "source": "redis" if pubsub else "mock-fallback",
                }))
            elif op == "unsubscribe":
                tickers = [str(t).upper() for t in msg.get("tickers", [])]
                for t in tickers:
                    subscribed.discard(t)
                await websocket.send_text(json.dumps({
                    "type": "unsubscribed",
                    "tickers": sorted(subscribed),
                }))
            elif op == "ping":
                await websocket.send_text(json.dumps({
                    "type": "pong",
                    "asof": datetime.utcnow().isoformat(timespec="seconds"),
                }))
            else:
                await websocket.send_text(json.dumps({
                    "type": "error",
                    "message": f"Unknown op: {op!r}",
                }))
    except WebSocketDisconnect:
        pass
    finally:
        pusher_task.cancel()
        try:
            await pusher_task
        except (asyncio.CancelledError, Exception):
            pass
        if pubsub is not None:
            try:
                await pubsub.unsubscribe(PRICES_CHANNEL)
                await pubsub.aclose()
            except Exception:
                pass
        if redis is not None:
            try:
                await redis.aclose()
            except Exception:
                pass
