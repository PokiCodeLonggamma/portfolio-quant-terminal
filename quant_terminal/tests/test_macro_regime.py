"""Tests for the Cluster 2 macro / régime stack."""
from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd
import pytest

from src.common.schemas import RegimeSnapshot, PairCandidate
from src.macro.correlations import (
    corr_regime_changes,
    rolling_corr_matrix,
    rolling_corr_vs_benchmarks,
)
from src.macro.pair_screener import screen_pairs_df, screen_pairs
from src.macro.regime import (
    _classify_growth,
    _classify_inflation,
    _classify_policy,
    classify_regime_from_panel,
    regime_history,
)


# ---------------------------------------------------------------------------
# Per-axis primitives
# ---------------------------------------------------------------------------
def test_classify_inflation_thresholds():
    assert _classify_inflation(4.5) == "high"
    assert _classify_inflation(2.0) == "low"
    assert _classify_inflation(None) == "low"
    assert _classify_inflation(float("nan")) == "low"


def test_classify_growth_pmi_priority():
    assert _classify_growth(48.0, 0.5) == "low"   # PMI dominates
    assert _classify_growth(55.0, -0.2) == "high"
    assert _classify_growth(None, -0.1) == "low"  # fallback to inverted curve
    assert _classify_growth(None, 0.5) == "high"
    assert _classify_growth(None, None) == "high"


def test_classify_policy_uses_six_month_delta():
    assert _classify_policy(5.0, 4.0) == "tight"
    assert _classify_policy(2.5, 4.0) == "loose"
    assert _classify_policy(None, 4.0) == "loose"
    assert _classify_policy(5.0, None) == "loose"


# ---------------------------------------------------------------------------
# classify_regime_from_panel
# ---------------------------------------------------------------------------
def _synthetic_panel(*, cpi: float, pmi: float, dff_now: float, dff_then: float) -> pd.DataFrame:
    """Build a 200-row daily panel that yields the requested 'now' regime."""
    idx = pd.date_range("2024-01-01", periods=200, freq="B")
    # Constant CPI / PMI; DFF ramps linearly so that the value 6m (≈180d) before
    # the last point equals ``dff_then`` and the last point equals ``dff_now``.
    df = pd.DataFrame(index=idx)
    df["cpi_yoy"] = cpi
    df["pmi_proxy"] = pmi
    df["t10y3m"] = 1.0
    df["t10y2y"] = 0.5
    df["dff"] = np.linspace(dff_then, dff_now, num=len(idx))
    df.index.name = "date"
    return df


def test_classify_regime_stagflation():
    panel = _synthetic_panel(cpi=6.0, pmi=46.0, dff_now=5.5, dff_then=4.5)
    snap = classify_regime_from_panel(panel)
    assert isinstance(snap, RegimeSnapshot)
    assert snap.inflation == "high"
    assert snap.growth == "low"
    assert snap.policy == "tight"
    assert snap.label == "Stagflation"
    assert 0.0 < snap.confidence <= 1.0


def test_classify_regime_goldilocks():
    panel = _synthetic_panel(cpi=2.0, pmi=55.0, dff_now=2.0, dff_then=3.0)
    snap = classify_regime_from_panel(panel)
    assert snap.inflation == "low"
    assert snap.growth == "high"
    assert snap.policy == "loose"
    assert snap.label == "Goldilocks"


def test_classify_regime_empty_panel_returns_zero_confidence():
    snap = classify_regime_from_panel(pd.DataFrame())
    assert isinstance(snap, RegimeSnapshot)
    assert snap.confidence == 0.0
    assert snap.label == "Goldilocks"  # deterministic fallback


def test_regime_history_returns_dataframe_with_required_columns():
    panel = _synthetic_panel(cpi=2.0, pmi=55.0, dff_now=2.0, dff_then=3.0)
    hist = regime_history(panel, freq="W")
    assert isinstance(hist, pd.DataFrame)
    assert not hist.empty
    for c in ("date", "inflation", "growth", "policy", "label", "confidence"):
        assert c in hist.columns


# ---------------------------------------------------------------------------
# Correlations
# ---------------------------------------------------------------------------
def test_rolling_corr_matrix_shape_and_diagonal():
    rng = np.random.default_rng(0)
    idx = pd.date_range("2024-01-01", periods=120, freq="B")
    df = pd.DataFrame(rng.normal(0, 0.01, size=(120, 4)),
                      index=idx, columns=["A", "B", "C", "D"])
    m = rolling_corr_matrix(df, window_days=60)
    assert m.shape == (4, 4)
    # Diagonal correlations are 1
    for c in df.columns:
        assert pytest.approx(1.0, abs=1e-9) == m.at[c, c]
    # Symmetric
    assert (m.values == m.values.T).all()


def test_rolling_corr_matrix_too_short_returns_empty():
    idx = pd.date_range("2024-01-01", periods=10, freq="B")
    df = pd.DataFrame(np.zeros((10, 2)), index=idx, columns=["A", "B"])
    assert rolling_corr_matrix(df, window_days=60).empty


def test_rolling_corr_vs_benchmarks_long_form():
    rng = np.random.default_rng(1)
    idx = pd.date_range("2024-01-01", periods=180, freq="B")
    port = pd.DataFrame(rng.normal(0, 0.01, size=(180, 2)),
                        index=idx, columns=["TICK1", "TICK2"])
    bench = pd.DataFrame(rng.normal(0, 0.01, size=(180, 2)),
                         index=idx, columns=["SPY", "QQQ"])
    out = rolling_corr_vs_benchmarks(port, bench, window=30)
    assert isinstance(out, pd.DataFrame)
    assert not out.empty
    assert set(out.columns) == {"SPY", "QQQ"}
    assert out.index.names == ["date", "ticker"]


def test_corr_regime_changes_detects_synthetic_shift():
    # Build a 200-row series where A and B are perfectly correlated in the
    # first half and anti-correlated in the second half.
    n = 200
    rng = np.random.default_rng(7)
    base = rng.normal(0, 0.01, size=n)
    a = base.copy()
    b = np.empty(n)
    b[: n // 2] = base[: n // 2]               # corr ≈ +1
    b[n // 2:] = -base[n // 2:]                # corr ≈ -1
    idx = pd.date_range("2024-01-01", periods=n, freq="B")
    df = pd.DataFrame({"A": a, "B": b}, index=idx)
    alerts = corr_regime_changes(df, window=60, threshold=0.5)
    assert not alerts.empty
    assert abs(float(alerts.iloc[0]["delta"])) >= 0.5


def test_corr_regime_changes_no_change_returns_empty():
    rng = np.random.default_rng(0)
    idx = pd.date_range("2024-01-01", periods=200, freq="B")
    # Two independent series — no significant correlation shift
    df = pd.DataFrame(rng.normal(0, 0.01, size=(200, 2)),
                      index=idx, columns=["A", "B"])
    alerts = corr_regime_changes(df, window=60, threshold=0.9)
    assert alerts.empty


# ---------------------------------------------------------------------------
# Pair screener
# ---------------------------------------------------------------------------
def test_pair_screener_returns_dataframe_with_pvalues():
    # Two cointegrated series: B = 0.8 * A + small noise
    n = 400
    rng = np.random.default_rng(3)
    idx = pd.date_range("2023-01-01", periods=n, freq="B")
    # Random walk for A
    a = 100 + np.cumsum(rng.normal(0, 0.5, size=n))
    noise = rng.normal(0, 0.5, size=n)
    b = 0.8 * a + 20 + noise
    # An unrelated random-walk pair
    c = 50 + np.cumsum(rng.normal(0, 0.5, size=n))
    prices = pd.DataFrame({"A": a, "B": b, "C": c}, index=idx)

    df = screen_pairs_df(prices, pvalue_threshold=0.10, lookback_days=300)
    assert isinstance(df, pd.DataFrame)
    assert not df.empty, "A/B should be cointegrated"
    assert "coint_pvalue" in df.columns
    assert (df["coint_pvalue"] <= 0.10).all()
    # The cointegrated pair (A, B) ranks first
    first = df.iloc[0]
    assert {first["long_ticker"], first["short_ticker"]} == {"A", "B"}


def test_pair_screener_typed_wrapper_returns_pair_candidates():
    n = 400
    rng = np.random.default_rng(4)
    idx = pd.date_range("2023-01-01", periods=n, freq="B")
    a = 100 + np.cumsum(rng.normal(0, 0.5, size=n))
    b = 0.8 * a + 20 + rng.normal(0, 0.5, size=n)
    prices = pd.DataFrame({"A": a, "B": b}, index=idx)
    pairs = screen_pairs(prices, pvalue_threshold=0.10, lookback_days=300)
    assert isinstance(pairs, list)
    assert pairs
    assert isinstance(pairs[0], PairCandidate)


def test_pair_screener_empty_input_returns_empty_dataframe():
    out = screen_pairs_df(pd.DataFrame())
    assert isinstance(out, pd.DataFrame)
    assert out.empty
