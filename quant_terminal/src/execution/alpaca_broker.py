"""Thin wrapper around alpaca-py's TradingClient — paper-default.

All methods return our typed schemas (`OrderRecord`, `BrokerAccount`,
`BrokerPosition`) so the rest of the codebase never imports alpaca-py
directly. This keeps the broker swappable.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from src.common.schemas import (
    BrokerAccount,
    BrokerPosition,
    OrderRecord,
    OrderRequest,
)
from src.execution.modes import resolve_mode
from src.utils.config import get_config
from src.utils.logging import get_logger

log = get_logger(__name__)


# ---------------------------------------------------------------------------
# Broker client
# ---------------------------------------------------------------------------
class AlpacaBroker:
    """Thin wrapper. Holds a single TradingClient bound to paper or live."""

    def __init__(self, *, mode: str | None = None) -> None:
        cfg = get_config()
        self.mode = mode or resolve_mode()
        self._cfg = cfg
        self._client = None  # lazy

    def _get_client(self):  # noqa: ANN202
        if self._client is not None:
            return self._client
        try:
            from alpaca.trading.client import TradingClient
        except ImportError as exc:
            raise RuntimeError("alpaca-py not installed — cannot place orders") from exc
        if not self._cfg.secrets.has_alpaca:
            raise RuntimeError("Alpaca credentials missing in .env")
        is_paper = self.mode == "paper"
        self._client = TradingClient(
            api_key=self._cfg.secrets.alpaca_key_id,
            secret_key=self._cfg.secrets.alpaca_secret_key,
            paper=is_paper,
        )
        log.info("AlpacaBroker initialised (mode=%s)", self.mode)
        return self._client

    # ---- Account ---------------------------------------------------------
    def get_account(self) -> BrokerAccount:
        client = self._get_client()
        a = client.get_account()
        return BrokerAccount(
            mode=self.mode,
            cash_usd=float(getattr(a, "cash", 0) or 0),
            buying_power_usd=float(getattr(a, "buying_power", 0) or 0),
            portfolio_value_usd=float(getattr(a, "portfolio_value", 0) or 0),
            daytrade_count=int(getattr(a, "daytrade_count", 0) or 0),
            pattern_day_trader=bool(getattr(a, "pattern_day_trader", False)),
            status=str(getattr(a, "status", "ACTIVE")),
        )

    # ---- Positions -------------------------------------------------------
    def get_positions(self) -> list[BrokerPosition]:
        client = self._get_client()
        out: list[BrokerPosition] = []
        for p in client.get_all_positions():
            asset_class_raw = str(getattr(p, "asset_class", "us_equity")).lower()
            ac = "option" if "option" in asset_class_raw else (
                "crypto" if "crypto" in asset_class_raw else "stock"
            )
            out.append(BrokerPosition(
                symbol=str(getattr(p, "symbol", "")),
                asset_class=ac,
                qty=float(getattr(p, "qty", 0) or 0),
                avg_entry_price=float(getattr(p, "avg_entry_price", 0) or 0),
                market_value_usd=float(getattr(p, "market_value", 0) or 0),
                unrealized_pl_usd=float(getattr(p, "unrealized_pl", 0) or 0),
                side="SHORT" if float(getattr(p, "qty", 0) or 0) < 0 else "LONG",
            ))
        return out

    # ---- Orders ----------------------------------------------------------
    def submit_order(self, req: OrderRequest) -> OrderRecord:
        from alpaca.trading.enums import OrderSide, TimeInForce
        from alpaca.trading.requests import LimitOrderRequest, MarketOrderRequest

        client = self._get_client()
        side = OrderSide.BUY if req.side == "BUY" else OrderSide.SELL
        tif = TimeInForce.DAY if req.time_in_force == "day" else TimeInForce.GTC

        # Determine the symbol to submit
        symbol = req.contract_symbol if req.asset_class == "option" else req.ticker
        if not symbol:
            raise ValueError("no symbol resolved for order")

        if req.order_type == "limit":
            payload = LimitOrderRequest(
                symbol=symbol, qty=req.qty, side=side, time_in_force=tif,
                limit_price=req.limit_price,
            )
        else:
            payload = MarketOrderRequest(
                symbol=symbol, qty=req.qty, side=side, time_in_force=tif,
            )

        record = OrderRecord(
            order_id=str(uuid.uuid4()),
            status="pending",
            request=req,
        )
        try:
            resp = client.submit_order(payload)
            record.broker_order_id = str(getattr(resp, "id", ""))
            record.submitted_at = datetime.utcnow()
            status = str(getattr(resp, "status", "submitted")).lower()
            record.status = _map_broker_status(status)
            record.audit_log.append(f"submitted to {self.mode} — broker_id={record.broker_order_id}")
            return record
        except Exception as exc:
            record.status = "rejected"
            record.error = str(exc)
            record.audit_log.append(f"submit failed: {exc}")
            log.warning("Order submit failed for %s: %s", symbol, exc)
            return record

    def cancel_order(self, broker_order_id: str) -> bool:
        client = self._get_client()
        try:
            client.cancel_order_by_id(broker_order_id)
            return True
        except Exception as exc:
            log.warning("Cancel failed for %s: %s", broker_order_id, exc)
            return False

    def get_orders(self, *, status: str = "open", limit: int = 50) -> list[dict[str, Any]]:
        """Return open / closed orders from broker. Light dict, not our schema."""
        from alpaca.trading.requests import GetOrdersRequest
        from alpaca.trading.enums import QueryOrderStatus

        client = self._get_client()
        status_enum = {
            "open": QueryOrderStatus.OPEN,
            "closed": QueryOrderStatus.CLOSED,
            "all": QueryOrderStatus.ALL,
        }.get(status.lower(), QueryOrderStatus.OPEN)
        req = GetOrdersRequest(status=status_enum, limit=limit)
        rows: list[dict[str, Any]] = []
        for o in client.get_orders(filter=req):
            rows.append({
                "id": str(getattr(o, "id", "")),
                "symbol": str(getattr(o, "symbol", "")),
                "qty": float(getattr(o, "qty", 0) or 0),
                "filled_qty": float(getattr(o, "filled_qty", 0) or 0),
                "side": str(getattr(o, "side", "")),
                "type": str(getattr(o, "order_type", "")),
                "limit_price": float(getattr(o, "limit_price", 0) or 0)
                    if getattr(o, "limit_price", None) else None,
                "status": str(getattr(o, "status", "")),
                "submitted_at": str(getattr(o, "submitted_at", "")),
            })
        return rows


def _map_broker_status(s: str) -> str:
    s = s.lower()
    if "filled" in s and "partial" in s:
        return "partially_filled"
    if s == "filled":
        return "filled"
    if "cancel" in s:
        return "canceled"
    if "reject" in s:
        return "rejected"
    if "expire" in s:
        return "expired"
    return "submitted"
