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
        # Build a lookup from common symbol forms to universe key
        keys = list(cfg.instruments.keys())
        lookup: dict[str, str] = {}
        for k in keys:
            meta = cfg.instruments[k]
            for alias in {k, meta.get("alpaca", ""), meta.get("yfinance", "")}:
                if alias:
                    lookup[alias.upper()] = k

        def resolve(sym: str) -> str:
            return lookup.get(str(sym).upper(), str(sym))

        df["universe_key"] = df["symbol"].map(resolve)
        df["theme"] = df["universe_key"].map(lambda k: cfg.theme_of(k))
        df["region"] = df["universe_key"].map(lambda k: cfg.region_of(k))
        if "currency" not in df.columns or df["currency"].isna().any():
            df["currency"] = df["universe_key"].map(lambda k: cfg.currency_of(k))
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
    """Build a Portfolio directly from a Degiro-parsed DataFrame."""
    needed = positions_df.copy()
    if "name" not in needed.columns:
        needed["name"] = needed["symbol"]
    return Portfolio(holdings=needed)
