"""Tax lots model + FIFO matching engine.

Storage:
  data/tax/lots.parquet         — open + partially-consumed lots
  data/tax/realised.parquet     — sale records

EUR cost basis is computed at acquisition using the FX rate snapshot
provided by the importer (defaults to 1.0 for EUR-listed names).
"""
from __future__ import annotations

import uuid
from datetime import date
from pathlib import Path

import pandas as pd

from src.common.schemas import RealisedTrade, TaxLot
from src.utils.config import PROJECT_ROOT
from src.utils.logging import get_logger

log = get_logger(__name__)

_DIR = PROJECT_ROOT / "data" / "tax"
_LOTS_FILE = _DIR / "lots.parquet"
_REALISED_FILE = _DIR / "realised.parquet"


def _ensure() -> None:
    _DIR.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------
def _read(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    try:
        return pd.read_parquet(path)
    except Exception as exc:
        log.warning("tax parquet read failed for %s: %s", path.name, exc)
        return pd.DataFrame()


def _write(path: Path, df: pd.DataFrame) -> None:
    _ensure()
    try:
        df.to_parquet(path, index=False)
    except Exception as exc:
        log.warning("tax parquet write failed for %s: %s", path.name, exc)


def list_lots(open_only: bool = True) -> pd.DataFrame:
    df = _read(_LOTS_FILE)
    if open_only and not df.empty and "qty" in df.columns:
        df = df[df["qty"] > 1e-9]
    return df.reset_index(drop=True)


def list_realised() -> pd.DataFrame:
    return _read(_REALISED_FILE)


# ---------------------------------------------------------------------------
# Mutations
# ---------------------------------------------------------------------------
def add_lot(
    ticker: str,
    qty: float,
    acquired_at: date,
    price_local: float,
    currency: str = "USD",
    fx_rate_eur: float = 1.0,
    account: str = "CTO",
    notes: str = "",
) -> TaxLot:
    """Record a new acquisition. Cost basis in EUR is computed here."""
    if currency.upper() == "EUR":
        cost_eur = qty * price_local
    elif currency.upper() in {"GBP", "GBX", "GBP"}:
        # GBp (London pence) → /100 before FX
        if currency.upper() in {"GBX", "GBP"} and currency != "GBP":
            cost_eur = qty * (price_local / 100.0) / fx_rate_eur if fx_rate_eur else 0.0
        else:
            cost_eur = qty * price_local / fx_rate_eur if fx_rate_eur else 0.0
    else:
        cost_eur = qty * price_local / fx_rate_eur if fx_rate_eur else 0.0

    lot = TaxLot(
        lot_id=str(uuid.uuid4()),
        ticker=ticker.upper(),
        qty=float(qty),
        qty_initial=float(qty),
        acquired_at=acquired_at,
        price_local=float(price_local),
        currency=currency.upper(),
        fx_rate_eur=float(fx_rate_eur or 1.0),
        cost_eur=float(cost_eur),
        account=account,
        notes=notes,
    )
    df = _read(_LOTS_FILE)
    new_row = pd.DataFrame([lot.model_dump()])
    df = pd.concat([df, new_row], ignore_index=True) if not df.empty else new_row
    _write(_LOTS_FILE, df)
    return lot


def record_sale(
    ticker: str,
    qty_sold: float,
    sold_at: date,
    sale_price_local: float,
    sale_currency: str = "USD",
    sale_fx_rate_eur: float = 1.0,
    account: str = "CTO",
) -> RealisedTrade | None:
    """FIFO match the sale against the open lots and persist the RealisedTrade.

    Returns None if no lots are available for the ticker.
    """
    df = list_lots(open_only=True)
    if df.empty:
        log.warning("No open lots for sale of %s", ticker)
        return None
    df = df[df["ticker"] == ticker.upper()].copy()
    if df.empty:
        log.warning("No open lots for %s — sale not matched", ticker)
        return None
    df = df.sort_values("acquired_at")

    # Sale proceeds in EUR
    if sale_currency.upper() == "EUR":
        proceeds_eur = qty_sold * sale_price_local
    elif sale_currency.upper() in {"GBX", "GBp"}:
        proceeds_eur = qty_sold * (sale_price_local / 100.0) / sale_fx_rate_eur if sale_fx_rate_eur else 0.0
    else:
        proceeds_eur = qty_sold * sale_price_local / sale_fx_rate_eur if sale_fx_rate_eur else 0.0

    remaining = float(qty_sold)
    consumed: list[dict] = []
    cost_basis_eur = 0.0
    holding_days_weighted = 0.0
    full = _read(_LOTS_FILE)

    for idx, lot in df.iterrows():
        if remaining <= 1e-9:
            break
        avail = float(lot["qty"])
        take = min(avail, remaining)
        if take <= 0:
            continue
        # Cost basis pro-rata
        per_share_cost = float(lot["cost_eur"]) / float(lot["qty_initial"]) if lot["qty_initial"] else 0.0
        lot_cost_eur = take * per_share_cost
        consumed.append({"lot_id": lot["lot_id"], "qty": take, "cost_eur": lot_cost_eur})
        cost_basis_eur += lot_cost_eur
        # holding-period weighted
        acq = lot["acquired_at"]
        if isinstance(acq, str):
            try:
                acq = date.fromisoformat(acq)
            except Exception:
                acq = sold_at
        holding_days_weighted += take * max(0, (sold_at - acq).days)
        # Reduce in master
        full.loc[full["lot_id"] == lot["lot_id"], "qty"] = avail - take
        remaining -= take

    avg_holding_days = int(holding_days_weighted / qty_sold) if qty_sold > 0 else 0
    realised_pnl_eur = proceeds_eur - cost_basis_eur

    trade = RealisedTrade(
        sale_id=str(uuid.uuid4()),
        ticker=ticker.upper(),
        sold_at=sold_at,
        qty_sold=float(qty_sold),
        sale_price_local=float(sale_price_local),
        sale_currency=sale_currency.upper(),
        sale_fx_rate_eur=float(sale_fx_rate_eur or 1.0),
        sale_proceeds_eur=float(proceeds_eur),
        consumed_lots=consumed,
        cost_basis_eur=float(cost_basis_eur),
        realised_pnl_eur=float(realised_pnl_eur),
        holding_period_days=avg_holding_days,
        account=account,
    )

    # Persist updates
    _write(_LOTS_FILE, full)
    realised_df = _read(_REALISED_FILE)
    row = pd.DataFrame([{
        **trade.model_dump(exclude={"consumed_lots"}),
        "consumed_lots": str(consumed),
    }])
    _write(_REALISED_FILE,
           pd.concat([realised_df, row], ignore_index=True) if not realised_df.empty else row)
    return trade


# ---------------------------------------------------------------------------
# Aggregations
# ---------------------------------------------------------------------------
def annual_realised(year: int | None = None) -> pd.DataFrame:
    df = list_realised()
    if df.empty:
        return df
    df = df.copy()
    df["sold_at"] = pd.to_datetime(df["sold_at"], errors="coerce")
    df["year"] = df["sold_at"].dt.year
    if year is not None:
        df = df[df["year"] == year]
    agg = df.groupby("year").agg(
        n_sales=("sale_id", "count"),
        proceeds_eur=("sale_proceeds_eur", "sum"),
        cost_basis_eur=("cost_basis_eur", "sum"),
        realised_pnl_eur=("realised_pnl_eur", "sum"),
    ).reset_index()
    # French PFU 30% (12.8% IR + 17.2% prélèvements sociaux) — informational only.
    agg["tax_pfu_30pct_eur"] = agg["realised_pnl_eur"].clip(lower=0) * 0.30
    return agg
