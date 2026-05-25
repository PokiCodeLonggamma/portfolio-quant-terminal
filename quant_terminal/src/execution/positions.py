"""Broker positions reader + reconciliation vs internal portfolio."""
from __future__ import annotations

import pandas as pd

from src.common.schemas import BrokerPosition
from src.execution.alpaca_broker import AlpacaBroker
from src.portfolio.holdings import Portfolio
from src.utils.logging import get_logger

log = get_logger(__name__)


def get_positions(broker: AlpacaBroker | None = None) -> list[BrokerPosition]:
    broker = broker or AlpacaBroker()
    try:
        return broker.get_positions()
    except Exception as exc:
        log.warning("get_positions failed: %s", exc)
        return []


def reconcile(internal: Portfolio | None, broker_positions: list[BrokerPosition]) -> pd.DataFrame:
    """Diff broker positions vs DEGIRO-parsed internal portfolio.

    Returns DataFrame columns:
      symbol · broker_qty · internal_qty · delta_qty · broker_mv_usd · internal_value_eur · status
    """
    rows: list[dict] = []
    broker_map = {p.symbol: p for p in broker_positions}

    if internal is not None and not internal.holdings.empty:
        for _, h in internal.holdings.iterrows():
            sym = str(h["universe_key"])
            bp = broker_map.pop(sym, None)
            rows.append({
                "symbol": sym,
                "broker_qty": float(bp.qty) if bp else 0.0,
                "internal_qty": float(h["quantity"]),
                "delta_qty": float(bp.qty) - float(h["quantity"]) if bp else -float(h["quantity"]),
                "broker_mv_usd": float(bp.market_value_usd) if bp else 0.0,
                "internal_value_eur": float(h["value_eur"]),
                "status": "match" if (bp and abs(float(bp.qty) - float(h["quantity"])) < 0.01)
                          else ("broker_missing" if not bp else "qty_mismatch"),
            })

    # Broker-only positions (not in internal)
    for sym, bp in broker_map.items():
        rows.append({
            "symbol": sym,
            "broker_qty": float(bp.qty),
            "internal_qty": 0.0,
            "delta_qty": float(bp.qty),
            "broker_mv_usd": float(bp.market_value_usd),
            "internal_value_eur": 0.0,
            "status": "internal_missing",
        })

    return pd.DataFrame(rows)
