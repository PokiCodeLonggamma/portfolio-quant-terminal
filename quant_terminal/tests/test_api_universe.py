"""Phase 0 — /api/universe endpoint tests.

The CDC §1 spec coverage tests (CDC required tickers etc.) live in
``tests/test_cross_asset.py`` — those exercise the loader. This file
exercises the FastAPI surface above the loader.
"""
from __future__ import annotations

from fastapi.testclient import TestClient

from api.main import app

client = TestClient(app)


# ---------------------------------------------------------------------------
# GET /api/universe
# ---------------------------------------------------------------------------
def test_get_universe_returns_all_asset_classes():
    r = client.get("/api/universe")
    assert r.status_code == 200
    body = r.json()
    assert "asset_classes" in body
    keys = {ac["key"] for ac in body["asset_classes"]}
    for must_have in (
        "us_indices", "volatility", "us_rates", "energy", "metals",
        "crypto", "eu_futures", "us_sector_etfs", "thematic_etfs",
        "benchmarks",
    ):
        assert must_have in keys, f"missing class {must_have}"


def test_get_universe_includes_theme_to_drivers():
    r = client.get("/api/universe")
    assert r.status_code == 200
    body = r.json()
    assert "theme_to_drivers" in body
    assert "Space" in body["theme_to_drivers"]
    assert "ARKX" in body["theme_to_drivers"]["Space"]["hedge_etfs"]


def test_get_universe_contracts_are_complete_pydantic_objects():
    r = client.get("/api/universe")
    body = r.json()
    one = body["asset_classes"][0]["contracts"][0]
    for k in ("logical", "name", "tier", "root", "exchange", "asset_class",
              "multiplier", "currency", "tick_size", "tick_value",
              "option_market"):
        assert k in one, f"contract missing key {k}"


# ---------------------------------------------------------------------------
# GET /api/universe/{class_key}
# ---------------------------------------------------------------------------
def test_get_us_indices_returns_full_class():
    r = client.get("/api/universe/us_indices")
    assert r.status_code == 200
    body = r.json()
    assert body["key"] == "us_indices"
    logicals = {c["logical"] for c in body["contracts"]}
    for must_have in ("ES", "MES", "NQ", "MNQ"):
        assert must_have in logicals


def test_get_unknown_class_returns_404():
    r = client.get("/api/universe/no_such_class")
    assert r.status_code == 404
    assert "Unknown asset class" in r.json()["detail"]


# ---------------------------------------------------------------------------
# GET /api/universe/contracts/{logical}
# ---------------------------------------------------------------------------
def test_get_contract_by_logical_es():
    r = client.get("/api/universe/contracts/ES")
    assert r.status_code == 200
    body = r.json()
    assert body["logical"] == "ES"
    assert body["exchange"] == "CME"
    assert body["tradingview"] == "CME_MINI:ES1!"
    assert body["yfinance"] == "ES=F"
    assert body["option_market"] is True


def test_get_unknown_contract_returns_404():
    r = client.get("/api/universe/contracts/NOPE")
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# GET /api/universe/resolve/{logical}?flavor=...
# ---------------------------------------------------------------------------
def test_resolve_yfinance_for_es():
    r = client.get("/api/universe/resolve/ES?flavor=yfinance")
    assert r.status_code == 200
    body = r.json()
    assert body["logical"] == "ES"
    assert body["flavor"] == "yfinance"
    assert body["symbol"] == "ES=F"


def test_resolve_tradingview_for_cl():
    r = client.get("/api/universe/resolve/CL?flavor=tradingview")
    assert r.status_code == 200
    assert r.json()["symbol"] == "NYMEX:CL1!"


def test_resolve_alpaca_for_etf():
    r = client.get("/api/universe/resolve/SPY?flavor=alpaca")
    assert r.status_code == 200
    assert r.json()["symbol"] == "SPY"


def test_resolve_invalid_flavor_returns_422():
    r = client.get("/api/universe/resolve/ES?flavor=NOPE")
    assert r.status_code == 422  # Pydantic validation


def test_resolve_unknown_logical_returns_input_as_symbol():
    """resolve_symbol never raises — returns input as fallback."""
    r = client.get("/api/universe/resolve/DOES_NOT_EXIST?flavor=yfinance")
    assert r.status_code == 200
    assert r.json()["symbol"] == "DOES_NOT_EXIST"
