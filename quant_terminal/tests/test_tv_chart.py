"""CDC §1 — TradingView component tests.

We don't render Streamlit (no live app), so we test the pure-Python helpers:
symbol resolution + heuristic mapping.
"""
from __future__ import annotations

import pytest

from src.viz.tv_chart import _heuristic_tv_symbol, _YF_FUTURES_TO_TV, tv_symbol_for


# ---------------------------------------------------------------------------
# tv_symbol_for goes through cross_asset YAML first
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("logical, expected", [
    ("ES",   "CME_MINI:ES1!"),
    ("NQ",   "CME_MINI:NQ1!"),
    ("MES",  "CME_MINI:MES1!"),
    ("CL",   "NYMEX:CL1!"),
    ("MCL",  "NYMEX:MCL1!"),
    ("GC",   "COMEX:GC1!"),
    ("VX",   "CBOE:VX1!"),
    ("BTC",  "CME:BTC1!"),
    ("FDAX", "EUREX:FDAX1!"),
    ("FCE",  "MATIF:FCE1!"),
    ("SPY",  "AMEX:SPY"),
    ("QQQ",  "NASDAQ:QQQ"),
    ("VIX",  "CBOE:VIX"),
])
def test_tv_symbol_for_known_logical(logical, expected):
    assert tv_symbol_for(logical) == expected


# ---------------------------------------------------------------------------
# Heuristic fallback for symbols NOT in the YAML
# ---------------------------------------------------------------------------
def test_heuristic_recognises_yfinance_futures():
    """Quick spot-check on the static dict — used when caller passes 'ES=F'
    instead of 'ES'."""
    assert _heuristic_tv_symbol("ES=F") == "CME_MINI:ES1!"
    assert _heuristic_tv_symbol("CL=F") == "NYMEX:CL1!"
    assert _heuristic_tv_symbol("GC=F") == "COMEX:GC1!"
    assert _heuristic_tv_symbol("^VIX") == "CBOE:VIX"


def test_heuristic_crypto_pair():
    assert _heuristic_tv_symbol("BTC-USD") == "COINBASE:BTCUSD"
    assert _heuristic_tv_symbol("ETH-USD") == "COINBASE:ETHUSD"


def test_heuristic_european_listings():
    assert _heuristic_tv_symbol("ENGI.PA") == "EURONEXT:ENGI"
    assert _heuristic_tv_symbol("SAP.DE") == "XETR:SAP"
    assert _heuristic_tv_symbol("3OIL.L") == "LSE:3OIL"
    assert _heuristic_tv_symbol("AII.TO") == "TSX:AII"


def test_heuristic_us_equity_passthrough():
    """Bare US ticker is valid on TradingView — return as-is."""
    assert _heuristic_tv_symbol("AAPL") == "AAPL"
    assert _heuristic_tv_symbol("TSLA") == "TSLA"


def test_heuristic_empty_input():
    assert _heuristic_tv_symbol("") == ""
    assert _heuristic_tv_symbol("   ") == ""


# ---------------------------------------------------------------------------
# tv_symbol_for falls back to heuristic when not in YAML
# ---------------------------------------------------------------------------
def test_tv_symbol_for_unknown_ticker_uses_heuristic():
    assert tv_symbol_for("AAPL") == "AAPL"
    assert tv_symbol_for("ENGI.PA") == "EURONEXT:ENGI"
    assert tv_symbol_for("BTC-USD") == "COINBASE:BTCUSD"


def test_tv_symbol_for_empty():
    assert tv_symbol_for("") == ""


# ---------------------------------------------------------------------------
# Sanity: the heuristic dict mirrors at least the key futures
# ---------------------------------------------------------------------------
def test_yf_futures_to_tv_covers_cdc_essentials():
    must_have = {"ES=F", "NQ=F", "CL=F", "GC=F", "VX=F", "BTC=F", "ETH=F", "ZN=F"}
    missing = must_have - set(_YF_FUTURES_TO_TV.keys())
    assert not missing, f"Heuristic missing futures: {missing}"
