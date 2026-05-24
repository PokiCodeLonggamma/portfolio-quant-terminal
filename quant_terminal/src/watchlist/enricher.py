"""Live-price enrichment for watchlist rows.

`add_live_prices(df, start, end)` adds:

    last_close_eur, ret_1d, ret_1w, ret_1m, ret_3m, ret_ytd,
    last_close_date, price_currency

It batch-downloads via `src.data.loaders.download_prices` (which uses the
yfinance fallback for tickers not present in universe.yaml) and FX-normalises
each per-ticker series to EUR through `src.data.fx.series_to_eur`.

Rows flagged `private=True` are left untouched (no live price available).
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Iterable

import numpy as np
import pandas as pd

from src.data.fx import series_to_eur
from src.data.loaders import download_prices
from src.utils.logging import get_logger

log = get_logger(__name__)

# Columns added by this enricher (declared once for the dashboards layer).
ENRICHED_COLUMNS: tuple[str, ...] = (
    "last_close_eur",
    "ret_1d",
    "ret_1w",
    "ret_1m",
    "ret_3m",
    "ret_ytd",
    "last_close_date",
    "price_currency",
)


def _safe_last(series: pd.Series) -> float | None:
    if series is None or series.empty:
        return None
    last = series.dropna()
    if last.empty:
        return None
    val = float(last.iloc[-1])
    if not np.isfinite(val):
        return None
    return val


def _return_over(
    series: pd.Series, *, days: int | None = None, since_year_start: bool = False
) -> float | None:
    """Pct change from N business days ago (or YTD)."""
    if series is None or series.empty:
        return None
    s = series.dropna()
    if s.empty:
        return None
    end_val = float(s.iloc[-1])
    if since_year_start:
        end_ts = s.index[-1]
        year_start = pd.Timestamp(year=end_ts.year, month=1, day=1)
        prior = s.loc[s.index >= year_start]
        if prior.empty:
            return None
        start_val = float(prior.iloc[0])
    else:
        if days is None or days < 1 or len(s) <= days:
            return None
        start_val = float(s.iloc[-days - 1])
    if start_val == 0 or not np.isfinite(start_val) or not np.isfinite(end_val):
        return None
    return end_val / start_val - 1.0


def _enrich_one(
    series_listing_ccy: pd.Series, currency: str
) -> dict[str, float | None | pd.Timestamp | str]:
    """Compute the per-ticker block of enriched values."""
    eur = series_to_eur(series_listing_ccy, currency)
    out: dict[str, float | None | pd.Timestamp | str] = {
        "last_close_eur": _safe_last(eur),
        "ret_1d": _return_over(eur, days=1),
        "ret_1w": _return_over(eur, days=5),
        "ret_1m": _return_over(eur, days=21),
        "ret_3m": _return_over(eur, days=63),
        "ret_ytd": _return_over(eur, since_year_start=True),
        "last_close_date": eur.dropna().index[-1] if not eur.dropna().empty else None,
        "price_currency": currency,
    }
    return out


def add_live_prices(
    watchlist_df: pd.DataFrame,
    start: datetime | str | None = None,
    end: datetime | str | None = None,
    *,
    price_panel: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Return a new DataFrame with the enriched columns appended.

    Parameters
    ----------
    watchlist_df: output of `load_watchlist(...)`. Must contain `symbol`
        and `currency` columns.
    start / end: passed through to `download_prices` when `price_panel`
        is not provided.
    price_panel: optional pre-fetched wide price panel (rows=date,
        cols=universe_key). Useful for tests and for sharing a single
        fetch across multiple watchlists.
    """
    if watchlist_df is None or watchlist_df.empty:
        for col in ENRICHED_COLUMNS:
            watchlist_df[col] = None
        return watchlist_df

    df = watchlist_df.copy()

    # Resolve symbols to fetch (skip private rows; they have no listing).
    if "private" in df.columns:
        public_mask = ~df["private"].astype(bool)
    else:
        public_mask = pd.Series([True] * len(df), index=df.index)

    if not public_mask.any():
        for col in ENRICHED_COLUMNS:
            df[col] = None
        return df

    public_syms: list[str] = (
        df.loc[public_mask, "symbol"].astype(str).unique().tolist()
    )

    # Default lookback = ~14 months so YTD + 12M comparisons always work.
    if end is None:
        end = datetime.utcnow()
    if isinstance(end, str):
        end = datetime.fromisoformat(end)
    if start is None:
        start = end - timedelta(days=430)
    if isinstance(start, str):
        start = datetime.fromisoformat(start)

    if price_panel is None:
        try:
            price_panel = download_prices(public_syms, start=start, end=end)
        except Exception as exc:  # noqa: BLE001 — never crash the dashboard
            log.warning("download_prices failed for watchlist symbols: %s", exc)
            price_panel = pd.DataFrame()

    enriched: dict[str, dict] = {}
    for sym in public_syms:
        currency = (
            df.loc[df["symbol"] == sym, "currency"].iloc[0]
            if (df["symbol"] == sym).any()
            else "USD"
        )
        if price_panel is None or price_panel.empty or sym not in price_panel.columns:
            enriched[sym] = {col: None for col in ENRICHED_COLUMNS}
            continue
        enriched[sym] = _enrich_one(price_panel[sym], str(currency))

    for col in ENRICHED_COLUMNS:
        df[col] = df["symbol"].map(lambda s, c=col: (enriched.get(str(s)) or {}).get(c))

    return df


def fetch_panel_for_lists(
    list_dfs: Iterable[pd.DataFrame],
    start: datetime | str | None = None,
    end: datetime | str | None = None,
) -> pd.DataFrame:
    """Convenience: one shared price fetch across multiple watchlists."""
    syms: set[str] = set()
    for df in list_dfs:
        if df is None or df.empty:
            continue
        if "private" in df.columns:
            sub = df.loc[~df["private"].astype(bool), "symbol"]
        else:
            sub = df["symbol"]
        syms.update(sub.astype(str).tolist())
    if not syms:
        return pd.DataFrame()
    return download_prices(sorted(syms), start=start, end=end)
