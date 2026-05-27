"""Cross-asset universe loader + symbol resolver (CDC §1).

Loads `config/universe_cross_asset.yaml` and exposes typed access:

    from src.universe import get_universe, resolve_symbol

    u = get_universe()
    es = u.find("ES")               # → ContractSpec
    es.tradingview                  # → "CME_MINI:ES1!"
    u.by_class("us_indices")        # → [ContractSpec, ...]
    resolve_symbol("ES", "yfinance")# → "ES=F"

The same loader honors the existing `config/universe.yaml` for equities — it
only ADDS the new cross-asset taxonomy without altering the legacy schema.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Iterable, Literal

import yaml

from src.utils.config import CONFIG_DIR, PROJECT_ROOT  # noqa: F401 (re-export)
from src.utils.logging import get_logger

log = get_logger(__name__)

# ---------------------------------------------------------------------------
# Type aliases
# ---------------------------------------------------------------------------
Tier = Literal["standard", "mini", "micro"]
Exchange = Literal[
    "CME", "CBOT", "NYMEX", "COMEX", "CBOE",
    "Eurex", "Euronext", "ICE_EU", "MATIF",
    "NYSE", "NASDAQ", "NYSE_ARCA", "AMEX", "BATS",
    "TSX", "LSE", "XETR", "STOXX", "SP", "TVC",
    "COINBASE", "INDEX",
]
SymbolFlavor = Literal["yfinance", "alpaca", "tradingview", "logical"]


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class ContractSpec:
    """One row of the cross-asset universe.

    All fields are required by the YAML schema; defaults exist only for
    forwards-compatibility when older YAMLs are loaded.
    """
    logical: str
    name: str
    tier: Tier
    root: str
    exchange: str
    asset_class: str           # injected by the loader (parent key)
    yfinance: str = ""
    alpaca: str = ""
    tradingview: str = ""
    multiplier: float = 1.0
    currency: str = "USD"
    tick_size: float = 0.01
    tick_value: float = 0.01
    option_market: bool = False
    notes: str = ""

    @property
    def is_future(self) -> bool:
        return self.tier in ("standard", "mini", "micro") and self.exchange in {
            "CME", "CBOT", "NYMEX", "COMEX", "CBOE", "Eurex",
            "Euronext", "ICE_EU", "MATIF",
        } and not self.yfinance.startswith("^")

    @property
    def is_etf(self) -> bool:
        return self.exchange in {"NYSE_ARCA", "NASDAQ", "AMEX", "BATS"}

    @property
    def is_spot_index(self) -> bool:
        return self.yfinance.startswith("^") or self.tradingview.startswith(("INDEX:", "TVC:", "SP:"))


@dataclass(frozen=True, slots=True)
class AssetClass:
    """A logical bucket grouping contracts (e.g. us_indices, energy)."""
    key: str
    label: str
    icon: str
    order: int
    contracts: tuple[ContractSpec, ...]

    def find(self, logical: str) -> ContractSpec | None:
        for c in self.contracts:
            if c.logical == logical:
                return c
        return None


@dataclass(frozen=True, slots=True)
class CrossAssetUniverse:
    """Top-level container — sorted by asset_class.order."""
    asset_classes: tuple[AssetClass, ...] = field(default_factory=tuple)
    theme_to_drivers: dict[str, dict[str, list[str]]] = field(default_factory=dict)

    # ----- lookup helpers --------------------------------------------------
    def by_class(self, key: str) -> tuple[ContractSpec, ...]:
        for ac in self.asset_classes:
            if ac.key == key:
                return ac.contracts
        return ()

    def find(self, logical: str) -> ContractSpec | None:
        for ac in self.asset_classes:
            hit = ac.find(logical)
            if hit is not None:
                return hit
        return None

    def all_contracts(self) -> list[ContractSpec]:
        return [c for ac in self.asset_classes for c in ac.contracts]

    def all_logicals(self) -> list[str]:
        return [c.logical for c in self.all_contracts()]

    def filter(self, *,
               asset_class: str | None = None,
               tier: Tier | None = None,
               exchange: str | None = None,
               option_market: bool | None = None) -> list[ContractSpec]:
        rows = self.all_contracts()
        if asset_class:
            rows = [c for c in rows if c.asset_class == asset_class]
        if tier:
            rows = [c for c in rows if c.tier == tier]
        if exchange:
            rows = [c for c in rows if c.exchange == exchange]
        if option_market is not None:
            rows = [c for c in rows if c.option_market == option_market]
        return rows


# ---------------------------------------------------------------------------
# Loader
# ---------------------------------------------------------------------------
_DEFAULT_PATH = CONFIG_DIR / "universe_cross_asset.yaml"


def _coerce_contract(row: dict, asset_class_key: str) -> ContractSpec | None:
    try:
        return ContractSpec(
            logical=str(row["logical"]),
            name=str(row.get("name", row["logical"])),
            tier=row.get("tier", "standard"),  # type: ignore[arg-type]
            root=str(row.get("root", row["logical"])),
            exchange=str(row.get("exchange", "")),
            asset_class=asset_class_key,
            yfinance=str(row.get("yfinance") or ""),
            alpaca=str(row.get("alpaca") or ""),
            tradingview=str(row.get("tradingview") or ""),
            multiplier=float(row.get("multiplier", 1.0)),
            currency=str(row.get("currency", "USD")),
            tick_size=float(row.get("tick_size", 0.01)),
            tick_value=float(row.get("tick_value", 0.01)),
            option_market=bool(row.get("option_market", False)),
            notes=str(row.get("notes") or ""),
        )
    except (KeyError, TypeError, ValueError) as exc:
        log.warning("Skipping malformed contract row in %s: %s — %s",
                    asset_class_key, row, exc)
        return None


def _load_universe(path: Path | None = None) -> CrossAssetUniverse:
    p = path or _DEFAULT_PATH
    if not p.exists():
        log.warning("universe_cross_asset.yaml not found at %s — returning empty universe", p)
        return CrossAssetUniverse()
    with p.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    classes: list[AssetClass] = []
    for key, ac in (data.get("asset_classes") or {}).items():
        contracts = []
        for row in ac.get("contracts") or []:
            cs = _coerce_contract(row, key)
            if cs is not None:
                contracts.append(cs)
        classes.append(AssetClass(
            key=key,
            label=str(ac.get("label", key)),
            icon=str(ac.get("icon", "")),
            order=int(ac.get("order", 999)),
            contracts=tuple(contracts),
        ))
    classes.sort(key=lambda a: a.order)
    return CrossAssetUniverse(
        asset_classes=tuple(classes),
        theme_to_drivers=(data.get("theme_to_drivers") or {}),
    )


@lru_cache(maxsize=1)
def get_universe() -> CrossAssetUniverse:
    """Lazy-cached singleton."""
    return _load_universe()


def reload_universe() -> CrossAssetUniverse:
    """Bust the lru_cache (useful in tests / hot-reload UIs)."""
    get_universe.cache_clear()
    return get_universe()


# ---------------------------------------------------------------------------
# Symbol resolver
# ---------------------------------------------------------------------------
def resolve_symbol(logical: str, flavor: SymbolFlavor = "yfinance") -> str:
    """Return the symbol for `flavor`, falling back gracefully.

    Resolution order when the asked flavor is empty:
      yfinance → tradingview → alpaca → logical
      alpaca   → yfinance    → tradingview → logical
      tradingview → yfinance → alpaca     → logical
      logical  → returned as-is
    """
    u = get_universe()
    spec = u.find(logical)
    if spec is None:
        return logical
    if flavor == "logical":
        return spec.logical
    direct = getattr(spec, flavor, "") or ""
    if direct:
        return direct
    chain: tuple[str, ...] = {
        "yfinance": ("tradingview", "alpaca"),
        "alpaca": ("yfinance", "tradingview"),
        "tradingview": ("yfinance", "alpaca"),
    }.get(flavor, ())
    for alt in chain:
        v = getattr(spec, alt, "") or ""
        if v:
            return v
    return spec.logical


def resolve_many(
    logicals: Iterable[str], flavor: SymbolFlavor = "yfinance"
) -> dict[str, str]:
    """Bulk resolve. Returns {logical: resolved_symbol}."""
    return {lg: resolve_symbol(lg, flavor) for lg in logicals}


# ---------------------------------------------------------------------------
# Convenience: drivers from theme (used by §3/§5 later)
# ---------------------------------------------------------------------------
def drivers_for_theme(theme: str) -> dict[str, list[str]]:
    """Return {'primary_futures': [...], 'hedge_etfs': [...]} for a theme.

    Empty dict if theme is not declared in the YAML.
    """
    return get_universe().theme_to_drivers.get(theme, {})
