"""Watchlist YAML loader.

`load_watchlist("quantum" | "photonics" | "defense" | "pre_ipo")` returns a
Portfolio-compatible DataFrame:

    columns = [
        symbol, name, quantity, value_eur, currency, region, theme,
        asset_class, alpaca_symbol, yfinance_symbol, universe_key,
        sub_theme, conviction, catalyst, peers, list_name, isin, private,
    ]

Watchlist tickers do NOT need to live in config/universe.yaml; the embedded
universe metadata in watchlists.yaml lets the loader emit a full row without
ever calling Portfolio._enrich (which would otherwise lose unknown symbols).

The "pre_ipo" list_name is a thin proxy over `load_private_watchlist`
projected into the same column schema — private rows carry `private=True`,
`quantity=0`, `value_eur=0`, `symbol=name`.
"""
from __future__ import annotations

from typing import Literal

import pandas as pd
import yaml

from src.common.schemas import WatchlistEntry
from src.utils.config import CONFIG_DIR
from src.utils.logging import get_logger

log = get_logger(__name__)

WATCHLISTS_YAML = CONFIG_DIR / "watchlists.yaml"

ListName = Literal["quantum", "photonics", "defense", "pre_ipo"]

_PORTFOLIO_COLUMNS: tuple[str, ...] = (
    "symbol",
    "name",
    "quantity",
    "value_eur",
    "currency",
    "region",
    "theme",
    "asset_class",
    "alpaca_symbol",
    "yfinance_symbol",
    "universe_key",
    "sub_theme",
    "conviction",
    "catalyst",
    "peers",
    "list_name",
    "isin",
    "private",
)


def _read_yaml() -> dict:
    if not WATCHLISTS_YAML.exists():
        raise FileNotFoundError(f"Watchlists YAML not found: {WATCHLISTS_YAML}")
    with WATCHLISTS_YAML.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    if not isinstance(data, dict):
        raise ValueError(f"{WATCHLISTS_YAML} must be a YAML mapping at the top level")
    return data


def parse_entries(list_name: ListName) -> list[WatchlistEntry]:
    """Parse a list block into validated `WatchlistEntry` objects."""
    if list_name == "pre_ipo":
        # Private list is loaded by `src.watchlist.private`. Provide stubs
        # here so callers that only want the WatchlistEntry shape get one.
        from src.watchlist.private import load_private_watchlist

        priv = load_private_watchlist()
        out: list[WatchlistEntry] = []
        for _, row in priv.iterrows():
            out.append(
                WatchlistEntry(
                    universe_key=str(row["symbol"]),
                    sub_theme=str(row.get("sub_theme", "")),
                    list_name="pre_ipo",
                    conviction="private",
                    catalyst=row.get("catalyst") or None,
                    peers=list(row.get("listed_proxies") or []),
                    private=True,
                    notes=row.get("notes") or None,
                    yfinance=None,
                    alpaca=None,
                    currency="USD",
                    region="Private",
                    theme="Pre_IPO",
                    asset_class="private",
                )
            )
        return out

    raw = _read_yaml().get(list_name, {}) or {}
    if not isinstance(raw, dict):
        log.warning("watchlists.yaml::%s is not a mapping; got %r", list_name, type(raw))
        return []

    entries: list[WatchlistEntry] = []
    for sym, meta in raw.items():
        meta = dict(meta or {})
        # `universe_key` defaults to the YAML key.
        entry = WatchlistEntry(
            universe_key=str(sym),
            sub_theme=str(meta.get("sub_theme", "Unclassified")),
            list_name=list_name,
            conviction=meta.get("conviction", "medium"),
            catalyst=meta.get("catalyst"),
            peers=list(meta.get("peers") or []),
            private=False,
            notes=meta.get("notes"),
            yfinance=meta.get("yfinance") or str(sym),
            alpaca=meta.get("alpaca", ""),
            isin=meta.get("isin"),
            name_hints=list(meta.get("name_hints") or []),
            currency=str(meta.get("currency", "USD")),
            region=str(meta.get("region", "US")),
            theme=meta.get("theme"),
            asset_class=str(meta.get("asset_class", "equity")),
        )
        entries.append(entry)
    return entries


def _entry_to_row(entry: WatchlistEntry) -> dict:
    """Project a WatchlistEntry into a Portfolio-stub row."""
    return {
        "symbol": entry.universe_key,
        "name": entry.universe_key,
        "quantity": 0.0 if entry.private else 1.0,
        "value_eur": 0.0 if entry.private else 1.0,
        "currency": entry.currency,
        "region": entry.region,
        "theme": entry.theme or "Unclassified",
        "asset_class": entry.asset_class,
        "alpaca_symbol": entry.alpaca or "",
        "yfinance_symbol": entry.yfinance or entry.universe_key,
        "universe_key": entry.universe_key,
        "sub_theme": entry.sub_theme,
        "conviction": entry.conviction,
        "catalyst": entry.catalyst,
        "peers": list(entry.peers),
        "list_name": entry.list_name,
        "isin": entry.isin,
        "private": entry.private,
    }


def load_watchlist(list_name: ListName) -> pd.DataFrame:
    """Return a Portfolio-compatible DataFrame for the requested watchlist."""
    entries = parse_entries(list_name)
    if not entries:
        return pd.DataFrame(columns=list(_PORTFOLIO_COLUMNS))
    rows = [_entry_to_row(e) for e in entries]
    df = pd.DataFrame(rows)
    # Guarantee column order + presence of every expected column.
    for col in _PORTFOLIO_COLUMNS:
        if col not in df.columns:
            df[col] = None
    return df[list(_PORTFOLIO_COLUMNS)]


def list_all_lists() -> list[ListName]:
    """Helper for dashboards — list configured watchlist keys."""
    return ["quantum", "photonics", "defense", "pre_ipo"]
