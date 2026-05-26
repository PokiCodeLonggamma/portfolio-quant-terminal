"""Capture the full portfolio state at a point in time.

Output bundle is a dict-of-DataFrames that `store.py` persists to a
dated parquet directory. The same bundle is what `replay.py` reads.
"""
from __future__ import annotations

from datetime import date
from typing import Any

import pandas as pd

from src.common.schemas import SnapshotMeta
from src.data.fx import spot_rate
from src.portfolio.holdings import Portfolio
from src.utils.logging import get_logger

log = get_logger(__name__)


def capture(
    portfolio: Portfolio | None,
    prices_eur: pd.DataFrame | None,
    *,
    open_options_df: pd.DataFrame | None = None,
    asof: date | None = None,
    notes: str = "",
) -> dict[str, Any]:
    """Build a snapshot bundle. Always returns the bundle even on partial data."""
    asof = asof or date.today()
    if portfolio is None or portfolio.holdings.empty:
        meta = SnapshotMeta(
            asof=asof, net_value_eur=0.0, gross_long_eur=0.0,
            cash_eur=0.0, n_positions=0, n_open_options=0, notes=notes,
        )
        return {"meta": meta, "positions": pd.DataFrame(), "options": pd.DataFrame()}

    holdings = portfolio.holdings.copy()
    cash = float(getattr(portfolio, "cash_eur", 0.0) or 0.0)
    gross = float(holdings["value_eur"].sum())
    net = gross + cash

    # Attach last price + spot in EUR per ticker
    last_prices = {}
    if prices_eur is not None and not prices_eur.empty:
        for col in prices_eur.columns:
            s = prices_eur[col].dropna()
            if not s.empty:
                last_prices[col] = float(s.iloc[-1])
    holdings["last_price_eur"] = holdings["universe_key"].map(last_prices)

    # FX snapshot (best-effort)
    fx: dict[str, float] = {}
    for ccy in ("USD", "CAD", "GBP", "EUR"):
        try:
            fx[ccy] = float(spot_rate(ccy))
        except Exception:
            fx[ccy] = 1.0

    n_options = 0
    options_df = pd.DataFrame()
    if open_options_df is not None and not open_options_df.empty:
        options_df = open_options_df.copy()
        n_options = len(options_df)

    meta = SnapshotMeta(
        asof=asof,
        net_value_eur=net,
        gross_long_eur=gross,
        cash_eur=cash,
        n_positions=int(len(holdings)),
        n_open_options=n_options,
        fx_rates=fx,
        notes=notes,
    )
    log.info("Snapshot captured for %s — net EUR %.0f, %d positions", asof, net, len(holdings))
    return {
        "meta": meta,
        "positions": holdings,
        "options": options_df,
    }
