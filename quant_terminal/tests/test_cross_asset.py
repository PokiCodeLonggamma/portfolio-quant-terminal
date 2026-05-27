"""CDC §1 — Cross-asset universe loader + symbol resolver tests."""
from __future__ import annotations

import pytest

from src.universe.cross_asset import (
    ContractSpec,
    CrossAssetUniverse,
    drivers_for_theme,
    get_universe,
    reload_universe,
    resolve_many,
    resolve_symbol,
)


# ---------------------------------------------------------------------------
# Loader smoke tests
# ---------------------------------------------------------------------------
def test_universe_loads_without_error():
    u = get_universe()
    assert isinstance(u, CrossAssetUniverse)
    assert len(u.asset_classes) > 0


def test_universe_has_expected_classes():
    u = get_universe()
    keys = {ac.key for ac in u.asset_classes}
    must_have = {
        "us_indices", "volatility", "us_rates",
        "energy", "metals", "crypto",
        "eu_futures", "us_sector_etfs", "thematic_etfs", "benchmarks",
    }
    missing = must_have - keys
    assert not missing, f"Missing asset classes: {missing}"


def test_classes_are_sorted_by_order():
    u = get_universe()
    orders = [ac.order for ac in u.asset_classes]
    assert orders == sorted(orders)


def test_no_duplicate_logicals_within_class():
    u = get_universe()
    for ac in u.asset_classes:
        logicals = [c.logical for c in ac.contracts]
        assert len(logicals) == len(set(logicals)), \
            f"Duplicate logicals in {ac.key}"


# ---------------------------------------------------------------------------
# Contract spec coverage — CDC must-haves
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("logical", [
    # CDC §1.1 indices
    "ES", "MES", "NQ", "MNQ", "YM", "MYM", "RTY", "M2K", "EMD",
    # CDC §1.2 vol
    "VX", "VXM", "VIX",
    # CDC §1.3 rates
    "ZT", "ZF", "ZN", "ZB",
    # CDC §1.4 energy
    "CL", "MCL", "NG", "MNG", "B", "HO", "RB",
    # CDC §1.5 metals
    "GC", "MGC", "SI", "SIL", "HG", "MHG", "PL", "PA",
    # CDC §1.6 crypto
    "BTC", "MBT", "ETH", "MET",
    # CDC §1.7 EU futures
    "FESX", "FDAX", "FDXM", "FDXS", "FCE", "Z", "FSMI",
    # CDC §1.8 sector ETFs
    "XLK", "XLF", "XLE", "XLV", "XLI", "XLY", "XLP", "XLB", "XLU", "XLRE", "XLC",
    # CDC §1.9 thematic ETFs
    "SMH", "SOXX", "ARKX", "ITA", "QTUM", "URA", "URNM", "GDX", "USO", "ARKK",
    # CDC §1.10 benchmarks
    "SPY", "QQQ", "IWM", "DIA", "SPX", "NDX", "RUT", "DXY",
])
def test_cdc_required_contract_is_present(logical):
    u = get_universe()
    spec = u.find(logical)
    assert spec is not None, f"CDC requires {logical} but it's missing"
    assert isinstance(spec, ContractSpec)
    assert spec.logical == logical
    assert spec.name
    assert spec.exchange
    assert spec.currency in {"USD", "EUR", "GBP", "CHF", "CAD"}
    assert spec.multiplier > 0
    assert spec.tick_size > 0


# ---------------------------------------------------------------------------
# Symbol resolver tests
# ---------------------------------------------------------------------------
def test_resolve_symbol_yfinance_for_known_future():
    assert resolve_symbol("ES", "yfinance") == "ES=F"
    assert resolve_symbol("NQ", "yfinance") == "NQ=F"
    assert resolve_symbol("CL", "yfinance") == "CL=F"
    assert resolve_symbol("GC", "yfinance") == "GC=F"
    assert resolve_symbol("VX", "yfinance") == "VX=F"


def test_resolve_symbol_tradingview_format():
    assert resolve_symbol("ES", "tradingview") == "CME_MINI:ES1!"
    assert resolve_symbol("NQ", "tradingview") == "CME_MINI:NQ1!"
    assert resolve_symbol("CL", "tradingview") == "NYMEX:CL1!"
    assert resolve_symbol("FDAX", "tradingview") == "EUREX:FDAX1!"
    assert resolve_symbol("VIX", "tradingview") == "CBOE:VIX"


def test_resolve_symbol_alpaca_for_equity_etf():
    assert resolve_symbol("SPY", "alpaca") == "SPY"
    assert resolve_symbol("QQQ", "alpaca") == "QQQ"
    assert resolve_symbol("XLE", "alpaca") == "XLE"


def test_resolve_symbol_unknown_returns_input():
    """Resolver is a no-op on unknown logicals — never raises."""
    assert resolve_symbol("DOES_NOT_EXIST") == "DOES_NOT_EXIST"


def test_resolve_symbol_falls_back_when_alpaca_empty():
    # ES has no alpaca symbol but has yfinance and tradingview.
    s = resolve_symbol("ES", "alpaca")
    # Should fall back to yfinance or TV, not return ""
    assert s != ""
    assert s in {"ES=F", "CME_MINI:ES1!", "ES"}


def test_resolve_many():
    out = resolve_many(["ES", "NQ", "CL"], "tradingview")
    assert out == {
        "ES": "CME_MINI:ES1!",
        "NQ": "CME_MINI:NQ1!",
        "CL": "NYMEX:CL1!",
    }


# ---------------------------------------------------------------------------
# Tier coverage — CDC requires standard/mini/micro for headline contracts
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("root,expected_tiers", [
    ("SP", {"standard", "mini", "micro"}),  # SP, ES, MES
    ("ND", {"standard", "mini", "micro"}),  # ND, NQ, MNQ
    ("DJ", {"standard", "mini", "micro"}),  # DJ, YM, MYM
    ("CL", {"standard", "mini", "micro"}),  # CL, QM, MCL
    ("GC", {"standard", "mini", "micro"}),  # GC, QO, MGC
    ("NG", {"standard", "mini", "micro"}),  # NG, QG, MNG
])
def test_tier_coverage_per_root(root, expected_tiers):
    u = get_universe()
    contracts = [c for c in u.all_contracts() if c.root == root]
    tiers = {c.tier for c in contracts}
    assert expected_tiers.issubset(tiers), \
        f"Root {root}: expected tiers {expected_tiers} but only found {tiers}"


# ---------------------------------------------------------------------------
# Filter helpers
# ---------------------------------------------------------------------------
def test_filter_by_class():
    u = get_universe()
    indices = u.filter(asset_class="us_indices")
    assert len(indices) >= 10
    for c in indices:
        assert c.asset_class == "us_indices"


def test_filter_by_tier_micro():
    u = get_universe()
    micros = u.filter(tier="micro")
    # CDC mandates MES, MNQ, MYM, M2K, MCL, MNG, MGC, MBT, MET, FDXS at minimum
    logicals = {c.logical for c in micros}
    must_have_micros = {"MES", "MNQ", "MYM", "M2K", "MCL", "MNG", "MGC", "MBT", "MET", "FDXS"}
    missing = must_have_micros - logicals
    assert not missing, f"Missing micro contracts: {missing}"


def test_filter_options_market():
    u = get_universe()
    with_opts = u.filter(option_market=True)
    assert len(with_opts) >= 20
    # Top liquidity contracts must have option_market=True
    must_have = {"ES", "NQ", "RTY", "VX", "CL", "GC", "BTC", "SPY", "QQQ"}
    found = {c.logical for c in with_opts}
    missing = must_have - found
    assert not missing, f"Expected option markets missing: {missing}"


# ---------------------------------------------------------------------------
# Theme drivers (used by §3 and §5 later)
# ---------------------------------------------------------------------------
def test_theme_to_drivers_loaded():
    u = get_universe()
    assert u.theme_to_drivers, "theme_to_drivers should not be empty"
    # CDC mentions Space, Semis, Uranium, Energy explicitly
    for theme in ("Space", "Semis", "Uranium", "Energy"):
        assert theme in u.theme_to_drivers, f"Theme {theme} missing"


def test_drivers_for_theme_returns_lists():
    drivers = drivers_for_theme("Space")
    assert "primary_futures" in drivers
    assert "hedge_etfs" in drivers
    assert isinstance(drivers["primary_futures"], list)
    assert isinstance(drivers["hedge_etfs"], list)
    assert "ARKX" in drivers["hedge_etfs"]


def test_drivers_for_unknown_theme_returns_empty():
    assert drivers_for_theme("NOT_A_THEME") == {}


# ---------------------------------------------------------------------------
# Reload safety
# ---------------------------------------------------------------------------
def test_reload_universe_returns_fresh_instance():
    u1 = get_universe()
    u2 = reload_universe()
    # cache busted, but data should be identical
    assert len(u1.asset_classes) == len(u2.asset_classes)
    assert u1.all_logicals() == u2.all_logicals()
