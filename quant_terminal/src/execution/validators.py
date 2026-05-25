"""Pre-trade validators — defence-in-depth before any broker call.

Returns a list of human-readable refusal reasons; an empty list means "OK
to submit". The broker layer MUST call `validate()` before `submit_order()`.
"""
from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

import pandas as pd
import yaml

from src.common.schemas import BrokerAccount, OrderRequest
from src.utils.config import PROJECT_ROOT
from src.utils.logging import get_logger

log = get_logger(__name__)

_CFG_FILE = PROJECT_ROOT / "config" / "execution.yaml"
_ORDERS_FILE = PROJECT_ROOT / "data" / "execution" / "orders.parquet"

DEFAULT_LIMITS = {
    "max_daily_orders": 20,
    "max_daily_notional_usd": 5_000.0,
    "max_single_order_notional_usd": 2_000.0,
    "max_pct_of_portfolio_per_trade": 0.05,   # 5 %
    "fat_finger_qty_threshold": 1_000,
}


def load_limits(yaml_path: Path | None = None) -> dict:
    path = Path(yaml_path) if yaml_path else _CFG_FILE
    if not path.exists():
        return dict(DEFAULT_LIMITS)
    try:
        with path.open("r", encoding="utf-8") as fp:
            data = yaml.safe_load(fp) or {}
        return {**DEFAULT_LIMITS, **(data.get("limits", {}) or {})}
    except Exception as exc:
        log.warning("execution.yaml read failed: %s", exc)
        return dict(DEFAULT_LIMITS)


def _today_orders_count(today: date | None = None) -> tuple[int, float]:
    """Returns (n_orders_today, notional_usd_today). Reads the parquet OMS log."""
    if not _ORDERS_FILE.exists():
        return 0, 0.0
    try:
        df = pd.read_parquet(_ORDERS_FILE)
    except Exception:
        return 0, 0.0
    if df.empty or "submitted_at" not in df.columns:
        return 0, 0.0
    today = today or date.today()
    df["_date"] = pd.to_datetime(df["submitted_at"], errors="coerce").dt.date
    mask = (df["_date"] == today) & df["status"].isin(["submitted", "filled", "partially_filled"])
    sub = df.loc[mask]
    if sub.empty:
        return 0, 0.0
    # rough notional = filled_qty × avg_fill_price (USD), fallback to limit_price
    notional = 0.0
    for _, r in sub.iterrows():
        qty = float(r.get("filled_qty") or 0)
        px = r.get("avg_fill_price")
        if not px or pd.isna(px):
            # fall back to the requested limit price in the audit (best-effort)
            px = 0.0
        notional += qty * float(px)
    return int(len(sub)), float(notional)


def _estimate_notional_usd(req: OrderRequest, last_px_eur: float | None = None,
                            eurusd_rate: float | None = None) -> float:
    """Best-effort notional in USD. We don't always have an immediate spot — use the limit price
    when available, else the EUR-converted last close.
    """
    if req.limit_price is not None and req.limit_price > 0:
        px = float(req.limit_price)
    elif last_px_eur is not None:
        # convert EUR back to USD assuming the broker reports USD
        rate = eurusd_rate if eurusd_rate else 1.10
        px = float(last_px_eur) * rate
    else:
        return 0.0
    multiplier = 100 if req.asset_class == "option" else 1
    return float(req.qty) * px * multiplier


def validate(
    req: OrderRequest,
    *,
    account: BrokerAccount | None = None,
    last_px_eur: float | None = None,
    eurusd_rate: float | None = None,
    limits: dict | None = None,
) -> list[str]:
    """Run every safety gate. Return list of refusal reasons (empty == pass)."""
    limits = limits or load_limits()
    reasons: list[str] = []

    # ---- Basic sanity ----------------------------------------------------
    if req.qty <= 0:
        reasons.append(f"qty must be positive (got {req.qty})")
    if req.order_type == "limit" and (req.limit_price is None or req.limit_price <= 0):
        reasons.append("limit order requires a positive limit_price")
    if req.asset_class == "option" and not req.contract_symbol:
        reasons.append("option order requires a contract_symbol (OCC)")

    # ---- Fat finger -------------------------------------------------------
    fat_q = int(limits.get("fat_finger_qty_threshold", 1_000))
    if req.qty > fat_q:
        reasons.append(f"fat-finger guard: qty {req.qty} > {fat_q}")

    # ---- Single-order notional cap ---------------------------------------
    notional = _estimate_notional_usd(req, last_px_eur, eurusd_rate)
    single_cap = float(limits.get("max_single_order_notional_usd", 2_000.0))
    if notional > single_cap:
        reasons.append(f"single-order notional ${notional:,.0f} > cap ${single_cap:,.0f}")

    # ---- % of portfolio --------------------------------------------------
    if account is not None and account.portfolio_value_usd > 0:
        pct = notional / account.portfolio_value_usd
        max_pct = float(limits.get("max_pct_of_portfolio_per_trade", 0.05))
        if pct > max_pct:
            reasons.append(
                f"notional {pct * 100:.1f}% of portfolio > cap {max_pct * 100:.1f}%"
            )

    # ---- Daily caps -------------------------------------------------------
    n_today, notional_today = _today_orders_count()
    max_day_orders = int(limits.get("max_daily_orders", 20))
    if n_today >= max_day_orders:
        reasons.append(f"daily order count {n_today} ≥ {max_day_orders}")
    max_day_notional = float(limits.get("max_daily_notional_usd", 5_000.0))
    if (notional_today + notional) > max_day_notional:
        reasons.append(
            f"daily notional ${notional_today + notional:,.0f} would exceed cap ${max_day_notional:,.0f}"
        )

    # ---- Cash check (BUY only) -------------------------------------------
    if req.side == "BUY" and account is not None:
        bp = float(account.buying_power_usd)
        if notional > bp:
            reasons.append(f"buying power ${bp:,.0f} < notional ${notional:,.0f}")

    return reasons
