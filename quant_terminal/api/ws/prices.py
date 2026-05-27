"""WebSocket /ws/prices — live price ticks.

Phase 2 ships the **skeleton** (subscribe/unsubscribe protocol + heartbeat).
Real upstream fan-out (Alpaca quote stream + yfinance polling) lands in
Phase 3 together with the Redis pub/sub layer.

Protocol (client → server):
    { "op": "subscribe",   "tickers": ["ES", "NQ"] }
    { "op": "unsubscribe", "tickers": ["NQ"] }
    { "op": "ping" }

Protocol (server → client):
    { "type": "subscribed", "tickers": [...] }
    { "type": "tick",       "ticker": "ES", "price": 5021.25, "asof": "…" }
    { "type": "pong",       "asof": "…" }
    { "type": "error",      "message": "…" }

Pricing source: until Phase 3, ticks come from a deterministic mock so the
frontend can wire the integration today.
"""
from __future__ import annotations

import asyncio
import json
import random
from datetime import datetime
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

router = APIRouter(tags=["ws"])


# ---------------------------------------------------------------------------
# Mock price generator — deterministic random walk per ticker
# ---------------------------------------------------------------------------
_LAST_PRICES: dict[str, float] = {
    "ES": 5000.0, "NQ": 18000.0, "YM": 41000.0, "RTY": 2050.0,
    "CL": 75.0, "GC": 2050.0, "SI": 25.0, "HG": 3.8,
    "BTC": 65000.0, "ETH": 3200.0,
    "SPY": 540.0, "QQQ": 470.0, "IWM": 215.0,
}


def _next_tick(ticker: str) -> float:
    """Deterministic-ish random walk around the last price.

    Replaced in Phase 3 with the real upstream feed.
    """
    last = _LAST_PRICES.get(ticker, 100.0)
    # ±0.05% step
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

    async def push_ticks() -> None:
        """Background task — push one tick per second per subscribed ticker."""
        try:
            while True:
                if subscribed:
                    for t in list(subscribed):
                        price = _next_tick(t)
                        await websocket.send_text(json.dumps({
                            "type": "tick",
                            "ticker": t,
                            "price": price,
                            "asof": datetime.utcnow().isoformat(timespec="seconds"),
                            "source": "mock",
                        }))
                await asyncio.sleep(1.0)
        except asyncio.CancelledError:
            return
        except Exception:
            return

    pusher_task = asyncio.create_task(push_ticks())

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
        except asyncio.CancelledError:
            pass
