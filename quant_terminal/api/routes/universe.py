"""Cross-asset universe endpoints (CDC §1).

Read-only — the universe is loaded from YAML at process start, cached in
memory via the ``lru_cache`` on ``src.universe.cross_asset.get_universe``.
No Redis needed for this surface.

Endpoints:

- ``GET /api/universe``                 → full universe
- ``GET /api/universe/{class_key}``     → one asset class
- ``GET /api/universe/contracts/{logical}`` → one contract
- ``GET /api/universe/resolve/{logical}?flavor=tradingview``
                                        → symbol resolution
"""
from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, HTTPException, Query

from api.models import (
    AssetClassResponse,
    ContractResponse,
    SymbolResolveResponse,
    UniverseResponse,
)
from src.universe.cross_asset import ContractSpec, get_universe, resolve_symbol

router = APIRouter(prefix="/api/universe", tags=["universe"])


def _contract_to_dict(c: ContractSpec) -> dict:
    return {
        "logical": c.logical, "name": c.name, "tier": c.tier, "root": c.root,
        "exchange": c.exchange, "asset_class": c.asset_class,
        "yfinance": c.yfinance, "alpaca": c.alpaca, "tradingview": c.tradingview,
        "multiplier": c.multiplier, "currency": c.currency,
        "tick_size": c.tick_size, "tick_value": c.tick_value,
        "option_market": c.option_market, "notes": c.notes,
    }


@router.get("", response_model=UniverseResponse)
async def get_universe_root() -> dict:
    u = get_universe()
    return {
        "asset_classes": [
            {
                "key": ac.key, "label": ac.label, "icon": ac.icon, "order": ac.order,
                "contracts": [_contract_to_dict(c) for c in ac.contracts],
            }
            for ac in u.asset_classes
        ],
        "theme_to_drivers": u.theme_to_drivers,
    }


@router.get("/{class_key}", response_model=AssetClassResponse)
async def get_asset_class(class_key: str) -> dict:
    u = get_universe()
    for ac in u.asset_classes:
        if ac.key == class_key:
            return {
                "key": ac.key, "label": ac.label, "icon": ac.icon, "order": ac.order,
                "contracts": [_contract_to_dict(c) for c in ac.contracts],
            }
    raise HTTPException(status_code=404, detail=f"Unknown asset class: {class_key}")


@router.get("/contracts/{logical}", response_model=ContractResponse)
async def get_contract(logical: str) -> dict:
    spec = get_universe().find(logical)
    if spec is None:
        raise HTTPException(status_code=404, detail=f"Unknown logical: {logical}")
    return _contract_to_dict(spec)


@router.get("/resolve/{logical}", response_model=SymbolResolveResponse)
async def resolve_symbol_endpoint(
    logical: str,
    flavor: Literal["yfinance", "alpaca", "tradingview", "logical"] = Query(
        "yfinance", description="Symbol flavor to resolve to."
    ),
) -> dict:
    symbol = resolve_symbol(logical, flavor=flavor)
    return {"logical": logical, "flavor": flavor, "symbol": symbol}
