"""Tests for the Cluster 2 liquidity stack (ADV, slippage, borrow)."""
from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest

from src.liquidity import adv, borrow
from src.liquidity.adv import adv_snapshot, rolling_adv
from src.liquidity.slippage import (
    days_to_liquidate,
    expected_slippage_bps,
    slippage_cost,
    slippage_panel,
)


# ---------------------------------------------------------------------------
# ADV
# ---------------------------------------------------------------------------
def test_rolling_adv_window_mean():
    idx = pd.date_range("2024-01-01", periods=40, freq="B")
    # $-vol constant at 1e6 per day -> rolling mean = 1e6
    df = pd.DataFrame({"A": np.full(40, 1_000_000.0)}, index=idx)
    roll = rolling_adv(df, window_days=20)
    assert roll.iloc[-1]["A"] == pytest.approx(1_000_000.0)


def test_adv_snapshot_returns_named_series():
    idx = pd.date_range("2024-01-01", periods=40, freq="B")
    df = pd.DataFrame({
        "A": np.full(40, 1_000_000.0),
        "B": np.full(40, 2_500_000.0),
    }, index=idx)
    snap = adv_snapshot(df, window_days=20)
    assert isinstance(snap, pd.Series)
    assert snap.name == "adv_usd"
    assert snap["A"] == pytest.approx(1_000_000.0)
    assert snap["B"] == pytest.approx(2_500_000.0)


def test_adv_snapshot_empty_input():
    empty = pd.DataFrame()
    snap = adv_snapshot(empty)
    assert isinstance(snap, pd.Series)
    assert snap.empty


# ---------------------------------------------------------------------------
# Slippage scalars
# ---------------------------------------------------------------------------
def test_expected_slippage_bps_basic():
    # k * sigma * sqrt(trade/adv) = 0.1 * 0.02 * sqrt(0.01) = 0.0002 -> 2 bps
    bps = expected_slippage_bps(adv_usd=1e8, trade_usd=1e6, vol_daily=0.02, k=0.1)
    assert bps == pytest.approx(2.0, abs=1e-6)


def test_expected_slippage_bps_zero_trade():
    assert expected_slippage_bps(1e8, 0.0, 0.02) == 0.0


def test_expected_slippage_bps_zero_adv_is_infinite():
    assert math.isinf(expected_slippage_bps(0.0, 1e6, 0.02))
    assert math.isinf(expected_slippage_bps(float("nan"), 1e6, 0.02))


def test_expected_slippage_bps_monotonic_in_trade_size():
    small = expected_slippage_bps(1e8, 1e5, 0.02)
    medium = expected_slippage_bps(1e8, 1e6, 0.02)
    large = expected_slippage_bps(1e8, 1e7, 0.02)
    assert small < medium < large


def test_days_to_liquidate_zero_adv_is_infinite():
    assert math.isinf(days_to_liquidate(1e6, 0.0))


def test_days_to_liquidate_simple_math():
    # 1m / (10m * 10%) = 1 day
    assert days_to_liquidate(1_000_000, 10_000_000, participation=0.10) == pytest.approx(1.0)


def test_slippage_cost_monotonic_in_weight():
    a = slippage_cost(weight_usd=1e5, adv_usd=1e8, sigma_daily=0.02)
    b = slippage_cost(weight_usd=1e6, adv_usd=1e8, sigma_daily=0.02)
    c = slippage_cost(weight_usd=1e7, adv_usd=1e8, sigma_daily=0.02)
    assert a < b < c


# ---------------------------------------------------------------------------
# Slippage panel (vectorised)
# ---------------------------------------------------------------------------
def test_slippage_panel_columns_and_shape():
    weights = pd.Series({"A": 100_000.0, "B": 50_000.0, "C": 25_000.0})
    advs = pd.Series({"A": 1e8, "B": 5e7, "C": 1e7})
    vols = pd.Series({"A": 0.02, "B": 0.03, "C": 0.04})
    panel = slippage_panel(weights, advs, vols, trade_size_pct=0.01)
    assert set(["ticker", "weight_usd", "adv_usd", "slippage_bps",
                "days_to_liq_10pct", "days_to_liq_20pct"]).issubset(panel.columns)
    assert len(panel) == 3
    assert (panel["days_to_liq_20pct"] <= panel["days_to_liq_10pct"]).all()


def test_slippage_panel_handles_zero_adv():
    weights = pd.Series({"A": 100_000.0, "B": 100_000.0})
    advs = pd.Series({"A": 1e8, "B": 0.0})
    vols = pd.Series({"A": 0.02, "B": 0.02})
    panel = slippage_panel(weights, advs, vols)
    b_row = panel[panel["ticker"] == "B"].iloc[0]
    assert math.isinf(b_row["slippage_bps"]) or math.isnan(b_row["slippage_bps"]) or b_row["slippage_bps"] > 1e6


# ---------------------------------------------------------------------------
# Borrow / short interest (degrades gracefully)
# ---------------------------------------------------------------------------
def test_borrow_short_interest_handles_empty_yf_info(monkeypatch):
    """Ensure short_interest never raises even when yfinance returns nothing."""
    monkeypatch.setattr(borrow, "_yf_info", lambda symbol: {})
    monkeypatch.setattr(borrow, "cache_read", lambda *a, **kw: None)
    monkeypatch.setattr(borrow, "cache_write", lambda *a, **kw: None)
    row = borrow.short_interest("MADE_UP_TICKER")
    assert isinstance(row, dict)
    assert row["ticker"] == "MADE_UP_TICKER"
    assert row["short_interest_pct"] is None
    assert row["days_to_cover"] is None
    assert row["borrow_estimate"] == "n/a"


def test_borrow_short_interest_normalises_fraction(monkeypatch):
    monkeypatch.setattr(borrow, "_yf_info",
                        lambda symbol: {"shortPercentOfFloat": 0.25, "shortRatio": 4.5,
                                        "sharesShort": 5_000_000, "floatShares": 20_000_000})
    monkeypatch.setattr(borrow, "cache_read", lambda *a, **kw: None)
    monkeypatch.setattr(borrow, "cache_write", lambda *a, **kw: None)
    row = borrow.short_interest("FOO")
    # 0.25 was a fraction -> normalised to 25%
    assert row["short_interest_pct"] == pytest.approx(25.0)
    assert row["days_to_cover"] == pytest.approx(4.5)
    assert row["borrow_estimate"] == "hard_to_borrow"


def test_borrow_panel_returns_dataframe(monkeypatch):
    monkeypatch.setattr(borrow, "_yf_info", lambda symbol: {})
    monkeypatch.setattr(borrow, "cache_read", lambda *a, **kw: None)
    monkeypatch.setattr(borrow, "cache_write", lambda *a, **kw: None)
    df = borrow.borrow_panel(["A", "B", "C"])
    assert isinstance(df, pd.DataFrame)
    assert len(df) == 3
    assert {"ticker", "short_interest_pct", "borrow_estimate"}.issubset(df.columns)


def test_borrow_rate_returns_none():
    # yfinance doesn't expose actual borrow rates; ensure stable contract
    assert borrow.borrow_rate("AAPL") is None


# ---------------------------------------------------------------------------
# download_volume — patched fetchers to avoid network
# ---------------------------------------------------------------------------
def test_download_volume_with_mocked_ohlcv(monkeypatch):
    idx = pd.date_range("2024-01-01", periods=30, freq="B")
    fake = pd.DataFrame({
        "Open": np.full(30, 100.0),
        "High": np.full(30, 101.0),
        "Low": np.full(30, 99.0),
        "Close": np.full(30, 100.0),
        "Volume": np.full(30, 10_000.0),
    }, index=idx)

    monkeypatch.setattr(adv, "_yf_ohlcv", lambda symbol, start, end: fake.copy())
    monkeypatch.setattr(adv, "cache_read", lambda *a, **kw: None)
    monkeypatch.setattr(adv, "cache_write", lambda *a, **kw: None)

    out = adv.download_volume(["AAA"])
    assert isinstance(out, pd.DataFrame)
    assert "AAA" in out.columns
    # $-vol = 100 * 10_000 = 1_000_000
    assert out["AAA"].iloc[-1] == pytest.approx(1_000_000.0)
