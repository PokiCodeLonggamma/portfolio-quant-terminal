"""CSV importer for tax lots.

Expected columns (English or French headers OK):
    date,ticker,qty,price_local,currency,fx_rate_eur,account,notes
or  date,ticker,qty,price,devise,taux_eur,compte,notes

Lines with side="SELL" / sens="VENTE" are routed to `record_sale` instead.
"""
from __future__ import annotations

import io
from datetime import date
from pathlib import Path

import pandas as pd

from src.tax.lots import add_lot, record_sale
from src.utils.logging import get_logger

log = get_logger(__name__)

_ALIASES = {
    "date":         {"date", "trade_date"},
    "ticker":       {"ticker", "symbol", "produit"},
    "qty":          {"qty", "quantite", "quantité", "shares", "units"},
    "price_local":  {"price_local", "price", "prix"},
    "currency":     {"currency", "devise", "ccy"},
    "fx_rate_eur":  {"fx_rate_eur", "taux_eur", "fx", "fx_rate"},
    "account":      {"account", "compte"},
    "side":         {"side", "sens", "direction"},
    "notes":        {"notes", "comment", "remarque"},
}


def _normalise_columns(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    lower = {c.lower().strip(): c for c in df.columns}
    new_cols = {}
    for canon, aliases in _ALIASES.items():
        for a in aliases:
            if a in lower:
                new_cols[lower[a]] = canon
                break
    return df.rename(columns=new_cols)


def import_csv(source: str | Path | io.IOBase) -> tuple[int, int]:
    """Import a CSV/Excel of transactions. Returns (n_buys, n_sells)."""
    if hasattr(source, "read"):
        try:
            df = pd.read_csv(source)
        except Exception:
            source.seek(0)
            df = pd.read_excel(source)
    else:
        p = Path(source)
        if p.suffix.lower() in {".xlsx", ".xls"}:
            df = pd.read_excel(p)
        else:
            df = pd.read_csv(p)
    df = _normalise_columns(df)
    if "ticker" not in df.columns or "qty" not in df.columns:
        raise ValueError(f"missing required columns; saw {list(df.columns)}")

    buys = sells = 0
    for _, row in df.iterrows():
        ticker = str(row["ticker"]).upper()
        qty = float(row["qty"])
        try:
            acq = pd.to_datetime(row["date"]).date()
        except Exception:
            acq = date.today()
        price = float(row.get("price_local", row.get("price", 0.0)) or 0.0)
        ccy = str(row.get("currency", "USD")).upper()
        fx = float(row.get("fx_rate_eur", 1.0) or 1.0)
        account = str(row.get("account", "CTO"))
        notes = str(row.get("notes", ""))
        side = str(row.get("side", "BUY")).upper()
        if side in {"SELL", "VENTE", "S"}:
            rec = record_sale(ticker, qty, acq, price, ccy, fx, account=account)
            sells += 1 if rec else 0
        else:
            add_lot(ticker, qty, acq, price, ccy, fx, account=account, notes=notes)
            buys += 1
    log.info("Tax lot import: %d buys, %d sells", buys, sells)
    return buys, sells
