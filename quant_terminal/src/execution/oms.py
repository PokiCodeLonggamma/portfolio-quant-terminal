"""Order Management System — persistence + reconciliation.

Stores every `OrderRecord` in `data/execution/orders.parquet`. Provides
helpers to refresh status from broker, list open/closed, append audit log
entries.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pandas as pd

from src.common.schemas import OrderRecord, OrderRequest
from src.execution.alpaca_broker import AlpacaBroker
from src.execution.validators import validate
from src.utils.config import PROJECT_ROOT
from src.utils.logging import get_logger

log = get_logger(__name__)

_DIR = PROJECT_ROOT / "data" / "execution"
_ORDERS_FILE = _DIR / "orders.parquet"
_AUDIT_FILE = _DIR / "audit.log"


def _ensure_dir() -> None:
    _DIR.mkdir(parents=True, exist_ok=True)


def _load_df() -> pd.DataFrame:
    if not _ORDERS_FILE.exists():
        return pd.DataFrame()
    try:
        return pd.read_parquet(_ORDERS_FILE)
    except Exception as exc:
        log.warning("orders parquet read failed: %s", exc)
        return pd.DataFrame()


def _save_df(df: pd.DataFrame) -> None:
    _ensure_dir()
    try:
        df.to_parquet(_ORDERS_FILE, index=False)
    except Exception as exc:
        log.warning("orders parquet write failed: %s", exc)


def _append_audit(line: str) -> None:
    _ensure_dir()
    try:
        with _AUDIT_FILE.open("a", encoding="utf-8") as f:
            f.write(f"{datetime.utcnow().isoformat()}Z {line}\n")
    except Exception:
        pass


def persist(record: OrderRecord) -> None:
    """Write/update a single OrderRecord into the parquet store."""
    df = _load_df()
    row = json.loads(record.model_dump_json())
    # Flatten nested request fields for easier querying
    req = row.pop("request", {})
    row.update({
        "ticker": req.get("ticker"),
        "qty": req.get("qty"),
        "side": req.get("side"),
        "asset_class": req.get("asset_class"),
        "order_type": req.get("order_type"),
        "limit_price": req.get("limit_price"),
        "contract_symbol": req.get("contract_symbol"),
        "mode": req.get("mode"),
        "requested_at": req.get("requested_at"),
    })
    row["audit_log"] = " | ".join(record.audit_log)
    if df.empty:
        df = pd.DataFrame([row])
    else:
        mask = df["order_id"] == record.order_id
        if mask.any():
            df.loc[mask, :] = pd.DataFrame([row]).values
        else:
            df = pd.concat([df, pd.DataFrame([row])], ignore_index=True)
    _save_df(df)
    _append_audit(f"order={record.order_id} status={record.status} ticker={req.get('ticker')}")


def list_open() -> pd.DataFrame:
    df = _load_df()
    if df.empty or "status" not in df.columns:
        return pd.DataFrame()
    return df[df["status"].isin(["pending", "submitted", "partially_filled"])].reset_index(drop=True)


def list_all() -> pd.DataFrame:
    return _load_df()


def submit(req: OrderRequest, *, broker: AlpacaBroker | None = None,
           limits: dict | None = None, account=None, last_px_eur: float | None = None,
           eurusd_rate: float | None = None) -> OrderRecord:
    """End-to-end submit: validate → call broker → persist."""
    refusals = validate(req, account=account, last_px_eur=last_px_eur,
                        eurusd_rate=eurusd_rate, limits=limits)
    if refusals:
        record = OrderRecord(
            order_id=_gen_id(),
            status="rejected",
            request=req,
            error="; ".join(refusals),
            audit_log=[f"pre-trade refused: {r}" for r in refusals],
        )
        persist(record)
        return record

    broker = broker or AlpacaBroker()
    record = broker.submit_order(req)
    persist(record)
    return record


def refresh_status(broker: AlpacaBroker | None = None) -> int:
    """Re-fetch open broker orders and update local records. Returns # updated."""
    df = list_open()
    if df.empty:
        return 0
    broker = broker or AlpacaBroker()
    try:
        live_orders = {o["id"]: o for o in broker.get_orders(status="all", limit=200)}
    except Exception as exc:
        log.warning("refresh_status: broker fetch failed: %s", exc)
        return 0
    updated = 0
    full = _load_df()
    for idx, row in df.iterrows():
        bid = row.get("broker_order_id")
        if not bid or bid not in live_orders:
            continue
        live = live_orders[bid]
        new_status_raw = str(live.get("status", "")).lower()
        new_status = "filled" if new_status_raw == "filled" else (
            "partially_filled" if "partial" in new_status_raw else
            "canceled" if "cancel" in new_status_raw else
            "rejected" if "reject" in new_status_raw else
            "submitted"
        )
        if new_status != row.get("status"):
            mask = full["order_id"] == row["order_id"]
            full.loc[mask, "status"] = new_status
            full.loc[mask, "filled_qty"] = float(live.get("filled_qty", 0))
            updated += 1
            _append_audit(f"order={row['order_id']} -> {new_status}")
    if updated:
        _save_df(full)
    return updated


def cancel(broker_order_id: str, *, broker: AlpacaBroker | None = None) -> bool:
    broker = broker or AlpacaBroker()
    ok = broker.cancel_order(broker_order_id)
    if ok:
        full = _load_df()
        if not full.empty and "broker_order_id" in full.columns:
            mask = full["broker_order_id"] == broker_order_id
            full.loc[mask, "status"] = "canceled"
            _save_df(full)
            _append_audit(f"cancel broker_id={broker_order_id}")
    return ok


def _gen_id() -> str:
    import uuid
    return str(uuid.uuid4())
