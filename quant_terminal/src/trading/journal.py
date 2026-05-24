"""Trade journal — parquet-persisted open/closed trades + live mark-to-market.

File layout: `data/trading_journal/trades.parquet` (single flat file). Each row
is a `JournalTradeRow`. We deliberately do NOT use the `cache` module — the
journal is the source of truth and must survive cache wipes.

API
---
* `add_trade(ticket, qty, notes=None) -> trade_id`
* `close_trade(trade_id, exit_credit_eur, ts=None) -> JournalTradeRow`
* `list_open() -> DataFrame`
* `list_all()  -> DataFrame`
* `mark_to_market(open_rows, fetch_chain_fn) -> DataFrame` — adds
  `mtm_credit_eur`, `mtm_pnl_eur`, `mtm_pct`.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime
from pathlib import Path
from typing import Callable

import pandas as pd

from src.common.schemas import JournalTradeRow, OptionContract, OptionRight, TradeTicket
from src.data.fx import to_eur
from src.utils.config import get_config
from src.utils.logging import get_logger

log = get_logger(__name__)


# ---------------------------------------------------------------------------
# Path discovery / overrides
# ---------------------------------------------------------------------------
_JOURNAL_DIR_OVERRIDE: Path | None = None


def set_journal_dir(path: Path | str | None) -> None:
    """Test hook — override the journal directory (e.g. point to tmp_path)."""
    global _JOURNAL_DIR_OVERRIDE
    _JOURNAL_DIR_OVERRIDE = Path(path) if path is not None else None


def _journal_path() -> Path:
    if _JOURNAL_DIR_OVERRIDE is not None:
        base = _JOURNAL_DIR_OVERRIDE
    else:
        base = get_config().data_dir / "trading_journal"
    base.mkdir(parents=True, exist_ok=True)
    return base / "trades.parquet"


# ---------------------------------------------------------------------------
# Serialisation helpers (Pydantic <-> parquet-friendly dict)
# ---------------------------------------------------------------------------
_COLUMNS = [
    "trade_id", "opened_ts", "closed_ts", "ticker", "direction",
    "contract_symbol", "strike", "expiry", "debit_eur", "qty",
    "exit_credit_eur", "pnl_eur", "notes", "catalyst_event_id",
]


def _row_to_dict(row: JournalTradeRow) -> dict:
    d = row.model_dump()
    d["opened_ts"] = pd.Timestamp(row.opened_ts)
    d["closed_ts"] = pd.Timestamp(row.closed_ts) if row.closed_ts else pd.NaT
    d["expiry"] = pd.Timestamp(row.expiry)
    return d


def _df_from_rows(rows: list[JournalTradeRow]) -> pd.DataFrame:
    if not rows:
        return pd.DataFrame(columns=_COLUMNS)
    return pd.DataFrame([_row_to_dict(r) for r in rows])[_COLUMNS]


def _load_df() -> pd.DataFrame:
    path = _journal_path()
    if not path.exists():
        return pd.DataFrame(columns=_COLUMNS)
    try:
        return pd.read_parquet(path)
    except Exception as exc:
        log.error("Failed to read journal %s: %s", path, exc)
        return pd.DataFrame(columns=_COLUMNS)


def _save_df(df: pd.DataFrame) -> None:
    df.to_parquet(_journal_path(), index=False)


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------
def add_trade(
    ticket: TradeTicket, qty: int = 1, *,
    notes: str | None = None, catalyst_event_id: str | None = None,
) -> str:
    """Insert a new open trade. Returns the generated `trade_id`."""
    if qty <= 0:
        raise ValueError("qty must be positive")
    if ticket.refused_reasons:
        raise ValueError(
            f"Cannot journal a refused ticket: {'; '.join(ticket.refused_reasons)}"
        )
    trade_id = f"t_{uuid.uuid4().hex[:12]}"
    row = JournalTradeRow(
        trade_id=trade_id,
        opened_ts=datetime.utcnow(),
        closed_ts=None,
        ticker=ticket.ticker,
        direction=ticket.direction,
        contract_symbol=ticket.contract_symbol,
        strike=ticket.strike,
        expiry=ticket.expiry,
        debit_eur=ticket.debit_eur,
        qty=qty,
        exit_credit_eur=None,
        pnl_eur=None,
        notes=notes,
        catalyst_event_id=catalyst_event_id,
    )
    df = _load_df()
    new_row = pd.DataFrame([_row_to_dict(row)])[_COLUMNS]
    out = pd.concat([df, new_row], ignore_index=True) if not df.empty else new_row
    _save_df(out)
    log.info("Journaled trade %s for %s (%s)", trade_id, ticket.ticker, ticket.direction)
    return trade_id


def open_trade(
    ticket: TradeTicket, *, qty: int = 1, notes: str | None = None,
) -> JournalTradeRow:
    """Alias kept for Phase 1 plan compatibility."""
    trade_id = add_trade(ticket, qty=qty, notes=notes)
    df = _load_df()
    return _row_from_dict(df[df["trade_id"] == trade_id].iloc[0].to_dict())


def close_trade(
    trade_id: str, exit_credit_eur: float, *, ts: datetime | None = None,
) -> JournalTradeRow:
    """Mark an open trade closed; compute realised pnl."""
    df = _load_df()
    if df.empty or trade_id not in set(df["trade_id"]):
        raise KeyError(f"trade_id {trade_id} not found")
    mask = df["trade_id"] == trade_id
    closed_ts = ts or datetime.utcnow()
    debit = float(df.loc[mask, "debit_eur"].iloc[0])
    qty = int(df.loc[mask, "qty"].iloc[0])
    pnl = (float(exit_credit_eur) - debit) * qty
    df.loc[mask, "closed_ts"] = pd.Timestamp(closed_ts)
    df.loc[mask, "exit_credit_eur"] = float(exit_credit_eur)
    df.loc[mask, "pnl_eur"] = pnl
    _save_df(df)
    log.info("Closed trade %s — pnl %.2f EUR", trade_id, pnl)
    return _row_from_dict(df.loc[mask].iloc[0].to_dict())


def list_open() -> pd.DataFrame:
    df = _load_df()
    if df.empty:
        return df
    return df[df["closed_ts"].isna()].reset_index(drop=True)


def list_all() -> pd.DataFrame:
    return _load_df()


def load_journal() -> pd.DataFrame:
    """Alias for backwards-compat with the Phase 1 plan."""
    return list_all()


# ---------------------------------------------------------------------------
# Mark-to-market
# ---------------------------------------------------------------------------
def _row_from_dict(d: dict) -> JournalTradeRow:
    rec = dict(d)
    # parquet -> Pydantic coercion
    opened = rec.get("opened_ts")
    closed = rec.get("closed_ts")
    expiry = rec.get("expiry")
    rec["opened_ts"] = pd.Timestamp(opened).to_pydatetime() if opened is not None else datetime.utcnow()
    rec["closed_ts"] = (
        pd.Timestamp(closed).to_pydatetime()
        if closed is not None and pd.notna(closed) else None
    )
    if isinstance(expiry, pd.Timestamp):
        rec["expiry"] = expiry.date()
    elif isinstance(expiry, str):
        rec["expiry"] = date.fromisoformat(expiry)
    rec["qty"] = int(rec.get("qty") or 0)
    if pd.isna(rec.get("exit_credit_eur")):
        rec["exit_credit_eur"] = None
    if pd.isna(rec.get("pnl_eur")):
        rec["pnl_eur"] = None
    if pd.isna(rec.get("notes")):
        rec["notes"] = None
    if pd.isna(rec.get("catalyst_event_id")):
        rec["catalyst_event_id"] = None
    return JournalTradeRow(**rec)


def _lookup_current_mid_eur(
    row: pd.Series, fetch_chain_fn: Callable[..., list[OptionContract]],
) -> float | None:
    """Walk the chain to find the same contract; return its current EUR mid."""
    try:
        chain = fetch_chain_fn(row["ticker"])
    except Exception as exc:
        log.debug("MTM chain fetch failed for %s: %s", row["ticker"], exc)
        return None
    for c in chain:
        if c.symbol == row["contract_symbol"]:
            px = c.mid or (
                0.5 * ((c.bid or 0.0) + (c.ask or 0.0))
                if (c.bid is not None and c.ask is not None) else None
            ) or c.last
            if px is None or px <= 0:
                return None
            ccy = (get_config().currency_of(row["ticker"]) or "USD").upper()
            return to_eur(px * 100.0, ccy)
    return None


def mark_to_market(
    open_trades_df: pd.DataFrame,
    fetch_chain_fn: Callable[..., list[OptionContract]] | None = None,
) -> pd.DataFrame:
    """Append `mtm_credit_eur`, `mtm_pnl_eur`, `mtm_pct` to the open-trades df.

    `fetch_chain_fn` defaults to `src.trading.options_chain.fetch_chain` but
    can be injected by tests / dashboards for deterministic snapshots.
    """
    if open_trades_df is None or open_trades_df.empty:
        return open_trades_df
    if fetch_chain_fn is None:
        from src.trading.options_chain import fetch_chain as _fc
        fetch_chain_fn = _fc

    df = open_trades_df.copy()
    mtm_credit, mtm_pnl, mtm_pct = [], [], []
    for _, row in df.iterrows():
        credit = _lookup_current_mid_eur(row, fetch_chain_fn)
        if credit is None:
            mtm_credit.append(None)
            mtm_pnl.append(None)
            mtm_pct.append(None)
            continue
        debit = float(row["debit_eur"])
        qty = int(row["qty"])
        pnl = (credit - debit) * qty
        pct = (credit - debit) / debit if debit > 0 else 0.0
        mtm_credit.append(credit)
        mtm_pnl.append(pnl)
        mtm_pct.append(pct)
    df["mtm_credit_eur"] = mtm_credit
    df["mtm_pnl_eur"] = mtm_pnl
    df["mtm_pct"] = mtm_pct
    return df


# Silence the unused-import linter (OptionRight is re-exported for callers).
__all__ = [
    "OptionRight", "add_trade", "open_trade", "close_trade",
    "list_open", "list_all", "load_journal", "mark_to_market",
    "set_journal_dir",
]
