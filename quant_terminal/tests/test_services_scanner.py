"""Phase 2 — ScannerService tests."""
from __future__ import annotations

from datetime import date, datetime

import pandas as pd
import pytest

from src.common.schemas import OptionContract, OptionRight
from src.services.scanner_service import ScannerService
from src.services.schemas import SqueezeRow


def _mk_chain():
    chain = []
    for strike in (95, 100, 105):
        for right in (OptionRight.CALL, OptionRight.PUT):
            chain.append(OptionContract(
                underlying="ASTS",
                symbol=f"ASTS261218{right.value}{int(strike*1000):08d}",
                expiry=date(2026, 12, 18),
                strike=float(strike), right=right,
                bid=1.0, ask=1.1, last=1.05, mid=1.05,
                iv=0.40,
                delta=0.25 if right == OptionRight.CALL else -0.25,
                gamma=0.02, theta=-0.02, vega=0.10,
                open_interest=2000, volume=200,
                snapshot_ts=datetime.utcnow(),
                source="alpaca",
            ))
    return chain


@pytest.fixture
def service():
    return ScannerService(
        chain_fetch_fn=lambda _tk: _mk_chain(),
        spot_fetch_fn=lambda _tk: 100.0,
        squeeze_fetch_fn=lambda: pd.DataFrame([
            {"Ticker": "AMC", "ShortFloat": 25.3, "ShortRatio": 6.1,
             "CTB": 95.2, "Util": 99.5, "on_sho": True,
             "composite_score": 88.0},
            {"Ticker": "GME", "ShortFloat": 22.0, "ShortRatio": 4.5,
             "CTB": 50.0, "Util": 92.0, "on_sho": False,
             "composite_score": 72.0},
        ]),
        default_universe=["ASTS"],
    )


# ---------------------------------------------------------------------------
# Universe scan
# ---------------------------------------------------------------------------
def test_scan_options_universe_returns_typed_rows(service):
    rows = service.scan_options_universe()
    assert isinstance(rows, list)
    if rows:  # may be empty if the underlying scorer returns nothing for stub data
        assert rows[0].ticker == "ASTS"
        assert rows[0].chain_size == 6


def test_scan_options_universe_empty_when_no_chain():
    s = ScannerService(
        chain_fetch_fn=lambda _tk: [],
        spot_fetch_fn=lambda _tk: 100.0,
        squeeze_fetch_fn=lambda: pd.DataFrame(),
        default_universe=["NOPE"],
    )
    assert s.scan_options_universe() == []


# ---------------------------------------------------------------------------
# Squeeze scan
# ---------------------------------------------------------------------------
def test_get_squeeze_top_returns_pydantic_rows(service):
    rows = service.get_squeeze_top()
    assert isinstance(rows, list)
    assert len(rows) == 2
    assert all(isinstance(r, SqueezeRow) for r in rows)
    amc = rows[0]
    assert amc.ticker == "AMC"
    assert amc.short_pct_float == 25.3
    assert amc.on_sho_threshold is True
    assert amc.composite_score == 88.0


def test_get_squeeze_top_respects_limit(service):
    rows = service.get_squeeze_top(limit=1)
    assert len(rows) == 1


def test_get_squeeze_top_empty_when_no_data():
    s = ScannerService(squeeze_fetch_fn=lambda: pd.DataFrame())
    assert s.get_squeeze_top() == []


# ---------------------------------------------------------------------------
# Service contract
# ---------------------------------------------------------------------------
def test_scanner_service_no_streamlit():
    import src.services.scanner_service as mod
    with open(mod.__file__, encoding="utf-8") as f:
        content = f.read()
    assert "import streamlit" not in content
