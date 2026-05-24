"""Cluster 7 — Backtest tests.

Each rule has a dedicated unit test on synthetic inputs. The engine,
metrics_diff and walk_forward have integration tests that assert
contract-level guarantees (monotone time, non-negative NAV, non-NaN
deltas, fold count).
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.backtest.engine import simulate
from src.backtest.metrics_diff import comparison_table, sharpe_delta
from src.backtest.optimizer import best_params, walk_forward
from src.backtest.rules import (
    MaxDrawdownTriggerRule,
    MaxSinglePositionRule,
    MaxThemeCapRule,
    MomentumEntryRule,
    StopLossRule,
)


# ---------------------------------------------------------------------------
# Synthetic fixtures
# ---------------------------------------------------------------------------
@pytest.fixture
def four_asset_weights() -> pd.Series:
    return pd.Series({"A": 0.55, "B": 0.20, "C": 0.15, "D": 0.10})


@pytest.fixture
def long_price_panel() -> pd.DataFrame:
    """500 trading-day panel, 4 assets, distinct drifts/vols.

    Asset D has a sharp drawdown in the middle to make stop-loss / DD-trigger
    rules observable.
    """
    rng = np.random.default_rng(seed=11)
    idx = pd.date_range("2023-01-02", periods=500, freq="B")
    drift = {"A": 0.0005, "B": 0.0003, "C": 0.0006, "D": 0.0001}
    vol = {"A": 0.012, "B": 0.018, "C": 0.014, "D": 0.030}
    data: dict[str, np.ndarray] = {}
    for c in ["A", "B", "C", "D"]:
        ret = rng.normal(drift[c], vol[c], size=len(idx))
        if c == "D":
            # Injected drawdown: -30% over bars [200..240], partial recovery after.
            ret[200:240] = ret[200:240] - 0.012
        prices = 100.0 * (1.0 + ret).cumprod()
        data[c] = prices
    return pd.DataFrame(data, index=idx)


# ---------------------------------------------------------------------------
# MaxSinglePositionRule
# ---------------------------------------------------------------------------
def test_max_single_position_caps_and_redistributes(four_asset_weights):
    rule = MaxSinglePositionRule(max_pct=0.30)
    # Use a dummy 1-row price panel and timestamp (rule does not depend on them).
    ts = pd.Timestamp("2024-01-02")
    prices = pd.DataFrame({"A": [1.0], "B": [1.0], "C": [1.0], "D": [1.0]}, index=[ts])
    adj = rule.evaluate(four_asset_weights, prices, ts)

    # All weights <= cap
    assert (adj <= 0.30 + 1e-9).all()
    # Cap on A was 0.55 - 0.30 = 0.25 to redistribute on (B, C, D)
    # weight sum is preserved (no cash leak unless every line is capped)
    assert np.isclose(adj.sum(), four_asset_weights.sum(), atol=1e-9)
    # The originally-uncapped names should have GAINED weight pro-rata
    assert adj["B"] > four_asset_weights["B"]
    assert adj["C"] > four_asset_weights["C"]
    assert adj["D"] > four_asset_weights["D"]


def test_max_single_position_rejects_bad_param():
    with pytest.raises(ValueError):
        MaxSinglePositionRule(max_pct=0.0)
    with pytest.raises(ValueError):
        MaxSinglePositionRule(max_pct=1.5)


# ---------------------------------------------------------------------------
# MaxDrawdownTriggerRule
# ---------------------------------------------------------------------------
def test_max_drawdown_trigger_derisks_when_nav_drops():
    rule = MaxDrawdownTriggerRule(threshold_pct=0.10, derisk_pct=0.5)
    weights = pd.Series({"A": 0.6, "B": 0.4})
    ts = pd.Timestamp("2024-06-30")
    prices = pd.DataFrame(
        {"A": [100.0, 105.0, 90.0], "B": [100.0, 102.0, 96.0]},
        index=pd.date_range("2024-06-28", periods=3, freq="B"),
    )

    # Provide NAV history with a 15% drawdown vs peak.
    weights.attrs["_nav_hint"] = [10_000.0, 11_000.0, 9_350.0]  # peak 11000, last 9350 -> -15%
    adj = rule.evaluate(weights, prices, ts)
    assert np.isclose(adj.sum(), weights.sum() * 0.5, atol=1e-9)


def test_max_drawdown_trigger_no_op_when_above_threshold():
    rule = MaxDrawdownTriggerRule(threshold_pct=0.10, derisk_pct=0.5)
    weights = pd.Series({"A": 0.6, "B": 0.4})
    ts = pd.Timestamp("2024-06-30")
    prices = pd.DataFrame(
        {"A": [100.0, 105.0], "B": [100.0, 102.0]},
        index=pd.date_range("2024-06-28", periods=2, freq="B"),
    )
    weights.attrs["_nav_hint"] = [10_000.0, 10_500.0]  # peak == last -> dd 0
    adj = rule.evaluate(weights, prices, ts)
    assert np.allclose(adj.values, weights.values)


# ---------------------------------------------------------------------------
# MaxThemeCapRule
# ---------------------------------------------------------------------------
def test_max_theme_cap_caps_theme():
    theme_map = {"A": "tech", "B": "tech", "C": "energy", "D": "energy"}
    rule = MaxThemeCapRule(theme_map=theme_map, max_pct=0.40)
    weights = pd.Series({"A": 0.30, "B": 0.30, "C": 0.20, "D": 0.10})  # tech=0.60
    ts = pd.Timestamp("2024-01-02")
    prices = pd.DataFrame(
        {k: [1.0] for k in weights.index}, index=[ts]
    )
    adj = rule.evaluate(weights, prices, ts)
    # Tech aggregate should be capped to 0.40
    tech_total = adj.loc[["A", "B"]].sum()
    energy_total = adj.loc[["C", "D"]].sum()
    assert np.isclose(tech_total, 0.40, atol=1e-9)
    # Energy untouched
    assert np.isclose(energy_total, 0.30, atol=1e-9)


# ---------------------------------------------------------------------------
# StopLossRule
# ---------------------------------------------------------------------------
def test_stop_loss_exits_after_drawdown():
    rule = StopLossRule(per_position_pct=0.15)
    idx = pd.date_range("2024-01-02", periods=5, freq="B")
    prices = pd.DataFrame(
        {
            "A": [100.0, 110.0, 115.0, 95.0, 92.0],  # peak 115, last 92 -> -20%
            "B": [50.0, 51.0, 52.0, 51.5, 53.0],     # no DD
        },
        index=idx,
    )
    weights = pd.Series({"A": 0.5, "B": 0.5})
    adj = rule.evaluate(weights, prices, idx[-1])
    assert adj["A"] == 0.0
    assert adj["B"] == 0.5


# ---------------------------------------------------------------------------
# MomentumEntryRule
# ---------------------------------------------------------------------------
def test_momentum_entry_flattens_when_below_threshold():
    rule = MomentumEntryRule(lookback_days=3, threshold=0.0)
    idx = pd.date_range("2024-01-02", periods=6, freq="B")
    prices = pd.DataFrame(
        {
            "A": [100.0, 101.0, 102.0, 103.0, 104.0, 105.0],  # up
            "B": [100.0, 99.0, 98.0, 97.0, 96.0, 95.0],       # down
        },
        index=idx,
    )
    weights = pd.Series({"A": 0.5, "B": 0.5})
    adj = rule.evaluate(weights, prices, idx[-1])
    assert adj["A"] == 0.5
    assert adj["B"] == 0.0


# ---------------------------------------------------------------------------
# engine.simulate — contract checks
# ---------------------------------------------------------------------------
def test_simulate_produces_monotone_time_and_nonneg_nav(long_price_panel, four_asset_weights):
    res = simulate(
        long_price_panel,
        initial_weights=four_asset_weights,
        rules=[MaxSinglePositionRule(max_pct=0.30)],
        rebalance_freq="M",
        initial_eur=10_000.0,
    )
    h = res.history
    assert not h.empty
    # Monotone increasing time index
    assert h.index.is_monotonic_increasing
    # NAV >= 0 always
    assert (h["nav_baseline"] >= 0).all()
    assert (h["nav_ruled"] >= 0).all()
    assert (h["cash_ruled"] >= 0).all()
    # Exposure between 0 and 1
    assert (h["exposure_ruled"] >= -1e-9).all()
    assert (h["exposure_ruled"] <= 1.0 + 1e-9).all()


def test_simulate_no_rules_equals_buy_and_hold_on_baseline(long_price_panel, four_asset_weights):
    res = simulate(
        long_price_panel,
        initial_weights=four_asset_weights,
        rules=None,
        rebalance_freq="never",
        initial_eur=10_000.0,
    )
    # With no rules and no rebalancing, ruled NAV must match baseline NAV.
    assert np.allclose(res.ruled_nav.values, res.baseline_nav.values, atol=1e-6)
    # Sanity: NAV started at initial_eur (within 1 bp).
    assert abs(res.ruled_nav.iloc[0] - 10_000.0) < 1.0


def test_simulate_empty_input_returns_empty():
    res = simulate(pd.DataFrame(), initial_weights=pd.Series(dtype=float))
    assert res.history.empty
    assert res.triggers.empty


def test_simulate_logs_triggers(long_price_panel, four_asset_weights):
    # Concentrated weights -> MaxSinglePositionRule(0.30) must fire on the
    # rebalance bars (the asset A is at 0.55).
    res = simulate(
        long_price_panel,
        initial_weights=four_asset_weights,
        rules=[MaxSinglePositionRule(max_pct=0.30)],
        rebalance_freq="M",
        initial_eur=10_000.0,
    )
    assert not res.triggers.empty
    assert "max_single_position" in set(res.triggers["rule"].unique())


# ---------------------------------------------------------------------------
# metrics_diff
# ---------------------------------------------------------------------------
def test_comparison_table_non_nan_sharpe_delta(long_price_panel, four_asset_weights):
    res = simulate(
        long_price_panel,
        initial_weights=four_asset_weights,
        rules=[MaxSinglePositionRule(max_pct=0.30)],
        rebalance_freq="M",
        initial_eur=10_000.0,
    )
    tbl = comparison_table(res.baseline_nav, res.ruled_nav)
    assert {"baseline", "ruled", "delta"} <= set(tbl.columns)
    sharpe_d = tbl.loc["Sharpe", "delta"]
    assert pd.notna(sharpe_d)
    assert isinstance(sharpe_delta(res.baseline_nav, res.ruled_nav), float)


# ---------------------------------------------------------------------------
# walk_forward
# ---------------------------------------------------------------------------
def test_walk_forward_returns_dataframe_with_at_least_one_fold(long_price_panel):
    wf = walk_forward(
        long_price_panel,
        base_rule_factory=lambda max_pct: MaxSinglePositionRule(max_pct=max_pct),
        param_grid={"max_pct": [0.20, 0.40]},
        train_window_days=120,
        test_window_days=60,
    )
    assert isinstance(wf, pd.DataFrame)
    assert not wf.empty
    assert "fold" in wf.columns
    assert wf["fold"].nunique() >= 1
    # Each fold ran both param values
    assert wf["max_pct"].nunique() == 2
    # OOS sharpe must be finite
    assert wf["oos_sharpe"].apply(np.isfinite).all()


def test_walk_forward_best_params(long_price_panel):
    wf = walk_forward(
        long_price_panel,
        base_rule_factory=lambda max_pct: MaxSinglePositionRule(max_pct=max_pct),
        param_grid={"max_pct": [0.20, 0.40]},
        train_window_days=120,
        test_window_days=60,
    )
    bp = best_params(wf)
    assert "max_pct" in bp
    assert bp["max_pct"] in {0.20, 0.40}


def test_walk_forward_too_short_history_returns_empty():
    idx = pd.date_range("2024-01-02", periods=30, freq="B")
    df = pd.DataFrame({"A": np.linspace(100, 105, 30)}, index=idx)
    wf = walk_forward(
        df,
        base_rule_factory=lambda max_pct: MaxSinglePositionRule(max_pct=max_pct),
        param_grid={"max_pct": [0.20]},
        train_window_days=252,
        test_window_days=63,
    )
    assert wf.empty
