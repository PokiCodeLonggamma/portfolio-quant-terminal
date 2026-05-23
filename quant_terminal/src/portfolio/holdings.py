"""Portfolio holdings representation.

The `Portfolio` wraps a holdings DataFrame and enriches it with metadata
from `config/universe.yaml` (theme, region, currency, alpaca/yfinance symbols).
All financial figures are in EUR.
"""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from src.utils.config import get_config
from src.utils.logging import get_logger

log = get_logger(__name__)

REQUIRED_COLS = {"symbol", "quantity", "value_eur"}


@dataclass
class Portfolio:
    """A wrapper around a normalised holdings DataFrame.

    Expected columns:
        symbol, name, quantity, value_eur, currency,
        theme, region, asset_class, alpaca_symbol, yfinance_symbol
    """

    holdings: pd.DataFrame

    def __post_init__(self) -> None:
        missing = REQUIRED_COLS - set(self.holdings.columns)
        if missing:
            raise ValueError(f"Portfolio holdings missing required columns: {missing}")
        self.holdings = self._enrich(self.holdings.copy())

    @staticmethod
    def _enrich(df: pd.DataFrame) -> pd.DataFrame:
        cfg = get_config()
        keys = list(cfg.instruments.keys())

        # Exact-match lookup: ticker, alpaca symbol, yfinance symbol, ISIN.
        exact: dict[str, str] = {}
        # Substring-match lookup: name_hints -> universe_key
        hint_pairs: list[tuple[str, str]] = []
        for k in keys:
            meta = cfg.instruments[k]
            for alias in {k, meta.get("alpaca", ""), meta.get("yfinance", ""), meta.get("isin", "")}:
                if alias:
                    exact[str(alias).upper()] = k
            for hint in meta.get("name_hints", []) or []:
                if hint:
                    hint_pairs.append((str(hint).lower(), k))

        def resolve(row: pd.Series) -> str:
            sym = str(row.get("symbol", "")).upper()
            if sym in exact:
                return exact[sym]
            name = str(row.get("name", "")).lower()
            for hint, k in hint_pairs:
                if hint in name:
                    return k
            # Last resort: keep the raw symbol so the user sees what wasn't mapped.
            return sym or name.upper() or "UNKNOWN"

        df["universe_key"] = df.apply(resolve, axis=1)
        df["theme"] = df["universe_key"].map(lambda k: cfg.theme_of(k))
        df["region"] = df["universe_key"].map(lambda k: cfg.region_of(k))
        if "currency" not in df.columns:
            df["currency"] = df["universe_key"].map(lambda k: cfg.currency_of(k))
        else:
            # If the parser left blanks, fill them from the universe.
            df["currency"] = df["currency"].where(
                df["currency"].astype(str).str.strip().ne(""),
                df["universe_key"].map(lambda k: cfg.currency_of(k)),
            )
        df["asset_class"] = df["universe_key"].map(
            lambda k: cfg.instruments.get(k, {}).get("asset_class", "equity")
        )
        df["alpaca_symbol"] = df["universe_key"].map(lambda k: cfg.alpaca_symbol(k))
        df["yfinance_symbol"] = df["universe_key"].map(lambda k: cfg.yfinance_symbol(k))
        return df

    # --- aggregates ---------------------------------------------------------
    @property
    def total_value_eur(self) -> float:
        return float(self.holdings["value_eur"].sum())

    @property
    def weights(self) -> pd.Series:
        w = self.holdings.set_index("universe_key")["value_eur"]
        total = w.sum()
        return w / total if total else w

    def by_theme(self) -> pd.Series:
        return (
            self.holdings.groupby("theme")["value_eur"].sum().sort_values(ascending=False)
        )

    def by_region(self) -> pd.Series:
        return (
            self.holdings.groupby("region")["value_eur"].sum().sort_values(ascending=False)
        )

    def by_currency(self) -> pd.Series:
        return (
            self.holdings.groupby("currency")["value_eur"].sum().sort_values(ascending=False)
        )

    def by_asset_class(self) -> pd.Series:
        return (
            self.holdings.groupby("asset_class")["value_eur"].sum().sort_values(ascending=False)
        )

    @property
    def universe_keys(self) -> list[str]:
        return self.holdings["universe_key"].unique().tolist()


def from_degiro(positions_df: pd.DataFrame) -> Portfolio:
    """Build a Portfolio directly from a Degiro-parsed DataFrame.

    Propagates the cash_eur sidecar (set by `parse_degiro`) onto the Portfolio
    instance so the UI can surface a margin / cash balance separately.
    """
    needed = positions_df.copy()
    if "name" not in needed.columns:
        needed["name"] = needed["symbol"]
    cash_eur = float(positions_df.attrs.get("cash_eur", 0.0))
    pf = Portfolio(holdings=needed)
    pf.cash_eur = cash_eur  # type: ignore[attr-defined]
    return pf
