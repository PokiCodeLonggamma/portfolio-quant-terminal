"""Parse a Degiro positions export (CSV) into a normalised holdings DataFrame.

Degiro exports come in many flavours (FR / EN / quarterly statement / live
positions). We accept a permissive column mapping and require only:
  - a name/ticker column
  - a quantity column
  - a market-value-in-EUR column

The output schema is:
    symbol | name | quantity | value_eur | value_local | currency
"""
from __future__ import annotations

import io
from pathlib import Path

import pandas as pd

from src.utils.logging import get_logger

log = get_logger(__name__)

# Tolerant column aliases (lower-cased, accents stripped during matching)
NAME_ALIASES = {"produit", "product", "name", "symbol", "ticker", "instrument"}
SYMBOL_ALIASES = {
    "isin/symbole", "isin", "symbol", "ticker", "code",
    "ticker/isin", "isin / symbole", "ticker / isin",
}
QTY_ALIASES = {"unites", "unités", "quantité", "quantite", "quantity", "qty", "shares", "qte"}
VALUE_EUR_ALIASES = {
    "valeur en eur", "value (eur)", "value eur", "market value (eur)", "value",
    "montant en eur", "montant eur", "amount in eur", "amount eur",
}
PRICE_ALIASES = {
    "prix", "price", "prix de cloture", "close price", "close",
    "clôture", "cloture", "prix de clôture",
}
CCY_ALIASES = {"devise", "currency", "ccy"}


_ACCENTS = str.maketrans({
    "é": "e", "è": "e", "ê": "e", "ë": "e",
    "à": "a", "â": "a", "ä": "a",
    "î": "i", "ï": "i",
    "ô": "o", "ö": "o",
    "ù": "u", "û": "u", "ü": "u",
    "ç": "c",
})


def _normalise(s: str) -> str:
    return s.strip().lower().translate(_ACCENTS)


def _find_col(columns: list[str], aliases: set[str]) -> str | None:
    norm_aliases = {_normalise(a) for a in aliases}
    for c in columns:
        if _normalise(c) in norm_aliases:
            return c
    return None


def _to_float(series: pd.Series) -> pd.Series:
    # Degiro uses comma decimals + sometimes thousands separators
    if series.dtype.kind in "fi":
        return series.astype(float)
    cleaned = (
        series.astype(str)
        .str.replace(" ", "", regex=False)
        .str.replace(" ", "", regex=False)
        .str.replace(",", ".", regex=False)
        .str.replace("EUR", "", regex=False)
        .str.replace("USD", "", regex=False)
    )
    return pd.to_numeric(cleaned, errors="coerce")


def parse_degiro(source: str | Path | io.IOBase) -> pd.DataFrame:
    """Read Degiro CSV/XLSX, return normalised positions.

    Auto-detects separator (`,` or `;`) and decimal.
    """
    if hasattr(source, "read"):
        raw = source.read()
        buf: io.IOBase = io.BytesIO(raw) if isinstance(raw, bytes) else io.StringIO(raw)
        df = _read_any(buf, name=getattr(source, "name", "uploaded"))
    else:
        path = Path(source)
        df = _read_any(path, name=str(path))

    cols = list(df.columns)
    name_col = _find_col(cols, NAME_ALIASES) or cols[0]
    symbol_col = _find_col(cols, SYMBOL_ALIASES)
    qty_col = _find_col(cols, QTY_ALIASES)
    value_eur_col = _find_col(cols, VALUE_EUR_ALIASES)
    price_col = _find_col(cols, PRICE_ALIASES)
    ccy_col = _find_col(cols, CCY_ALIASES)

    if qty_col is None or value_eur_col is None:
        raise ValueError(
            f"Degiro export must contain quantity and EUR market value columns. Saw: {cols}"
        )

    raw_symbol = (
        df[symbol_col].astype(str).str.strip()
        if symbol_col
        else df[name_col].astype(str).str.strip()
    )
    out = pd.DataFrame({
        "name": df[name_col].astype(str).str.strip(),
        "symbol": raw_symbol,
        "quantity": _to_float(df[qty_col]),
        "value_eur": _to_float(df[value_eur_col]),
        "price_local": _to_float(df[price_col]) if price_col else pd.NA,
        "currency": df[ccy_col].astype(str).str.strip() if ccy_col else "EUR",
    })
    # Drop CASH / settlement rows: they have no ticker AND no quantity.
    cash_mask = (
        out["symbol"].isin({"", "nan", "NaN", "None"})
        | out["symbol"].isna()
        | out["quantity"].isna()
        | (out["quantity"] == 0)
    )
    cash_total = float(out.loc[cash_mask, "value_eur"].sum())
    out = out[~cash_mask].reset_index(drop=True)
    out = out.dropna(subset=["value_eur"]).reset_index(drop=True)
    log.info(
        "DEGIRO parsed: %d positions, gross EUR=%.0f, cash EUR=%.0f",
        len(out), out["value_eur"].sum(), cash_total,
    )
    out.attrs["cash_eur"] = cash_total
    return out


def _read_any(src: Path | io.IOBase, name: str) -> pd.DataFrame:
    if isinstance(src, Path):
        if src.suffix.lower() in {".xlsx", ".xls"}:
            return pd.read_excel(src)
        return _read_csv_smart(src)
    else:
        # bytes/text buffer
        if name.lower().endswith((".xlsx", ".xls")):
            return pd.read_excel(src)
        return _read_csv_smart(src)


def _read_csv_smart(src: Path | io.IOBase) -> pd.DataFrame:
    for sep in (",", ";", "\t"):
        try:
            if hasattr(src, "seek"):
                src.seek(0)
            df = pd.read_csv(src, sep=sep, engine="python")
            if df.shape[1] >= 3:
                return df
        except Exception:
            continue
    raise ValueError("Could not parse Degiro file: no separator yielded >=3 columns")
