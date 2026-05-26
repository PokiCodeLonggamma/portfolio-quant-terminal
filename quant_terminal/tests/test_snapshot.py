"""Tests for the snapshot module (Feature 5a)."""
from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from src.snapshot import store as snap_store
from src.snapshot.capture import capture
from src.snapshot.store import history_table, list_dates, load, save
from src.portfolio.holdings import Portfolio


@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch):
    monkeypatch.setattr(snap_store, "_BASE", tmp_path)
    yield


@pytest.fixture
def stock_portfolio() -> Portfolio:
    df = pd.DataFrame({
        "symbol": ["GOOG", "CCJ"],
        "name": ["Alphabet C", "Cameco"],
        "quantity": [4, 30],
        "value_eur": [1_300.0, 720.0],
        "currency": ["USD", "USD"],
    })
    return Portfolio(holdings=df)


def test_capture_returns_meta_and_positions(stock_portfolio):
    prices = pd.DataFrame({
        "GOOG": [350.0, 355.0],
        "CCJ":  [27.0, 28.0],
    }, index=pd.date_range("2026-05-01", periods=2))
    bundle = capture(stock_portfolio, prices)
    assert bundle["meta"].n_positions == 2
    assert bundle["meta"].gross_long_eur == pytest.approx(2_020.0)
    assert "last_price_eur" in bundle["positions"].columns


def test_save_and_load_round_trip(stock_portfolio):
    prices = pd.DataFrame({"GOOG": [350.0], "CCJ": [27.0]},
                          index=pd.date_range("2026-05-01", periods=1))
    bundle = capture(stock_portfolio, prices, asof=date(2026, 5, 1))
    save(bundle)
    assert date(2026, 5, 1) in list_dates()
    loaded = load(date(2026, 5, 1))
    assert loaded is not None
    assert loaded["meta"].asof == date(2026, 5, 1)
    assert loaded["meta"].n_positions == 2
    assert not loaded["positions"].empty


def test_history_table_includes_saved_snapshots(stock_portfolio):
    for d in [date(2026, 5, 1), date(2026, 5, 2)]:
        save(capture(stock_portfolio, pd.DataFrame(), asof=d))
    h = history_table()
    assert len(h) == 2
    assert set(h["asof"]) == {"2026-05-01", "2026-05-02"}


def test_capture_empty_portfolio_returns_zero_meta():
    bundle = capture(None, None, asof=date(2026, 6, 1))
    assert bundle["meta"].n_positions == 0
    assert bundle["meta"].net_value_eur == 0
