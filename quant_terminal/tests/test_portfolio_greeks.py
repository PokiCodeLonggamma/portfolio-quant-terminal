"""Tests for portfolio Greeks aggregator (Feature 3)."""
from __future__ import annotations

from datetime import date, datetime, timedelta

import numpy as np
import pandas as pd
import pytest

from src.common.schemas import OptionContract, OptionRight
from src.portfolio.greeks import (
    aggregate_greeks,
    gamma_calendar,
    theta_decay_schedule,
)
from src.portfolio.holdings import Portfolio


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


@pytest.fixture
def synth_chain() -> list[OptionContract]:
    now = datetime.utcnow()
    expiry = date.today() + timedelta(days=30)
    return [
        OptionContract(
            underlying="ASTS", symbol="ASTS260619C00050000",
            expiry=expiry, strike=50.0, right=OptionRight.CALL,
            mid=2.50, iv=0.65, delta=0.25, gamma=0.020,
            theta=-0.04, vega=0.10, open_interest=500, volume=120,
            snapshot_ts=now, source="alpaca",
        ),
        OptionContract(
            underlying="ASTS", symbol="ASTS260619P00040000",
            expiry=expiry, strike=40.0, right=OptionRight.PUT,
            mid=1.80, iv=0.70, delta=-0.30, gamma=0.025,
            theta=-0.05, vega=0.12, open_interest=300, volume=80,
            snapshot_ts=now, source="alpaca",
        ),
    ]


def test_stock_only_delta_equals_market_value(stock_portfolio):
    pg = aggregate_greeks(
        portfolio=stock_portfolio,
        open_options_df=None,
        prices_eur=pd.DataFrame(),
    )
    assert pg.total_delta_eur == pytest.approx(1_300.0 + 720.0)
    assert pg.total_gamma_eur == 0.0
    assert pg.total_vega_eur == 0.0
    assert pg.total_theta_eur == 0.0
    assert pg.n_stock_positions == 2
    assert pg.n_option_positions == 0


def test_options_contribution(stock_portfolio, synth_chain):
    expiry = date.today() + timedelta(days=30)
    open_options = pd.DataFrame([
        {
            "trade_id": "t1", "ticker": "ASTS", "direction": "LONG_CALL",
            "contract_symbol": "ASTS260619C00050000",
            "strike": 50.0, "expiry": expiry, "qty": 2,
        },
    ])

    def fake_fetch(t):  # noqa: ANN001
        return synth_chain

    # Spot panel includes ASTS so delta uses real spot, not strike
    prices = pd.DataFrame({"ASTS": [40.0, 45.0, 50.0]}, index=pd.date_range("2026-04-01", periods=3))
    pg = aggregate_greeks(
        portfolio=stock_portfolio,
        open_options_df=open_options,
        prices_eur=prices,
        fetch_chain_fn=fake_fetch,
    )
    # Option delta = 0.25 × 2 × 100 × 50 = 2500 (USD), then to EUR (rate close to parity in stub)
    assert pg.n_option_positions == 1
    assert pg.total_gamma_eur > 0
    assert pg.total_vega_eur > 0
    # Long premium => theta is negative
    assert pg.total_theta_eur < 0
    # by_ticker carries both stocks and the option
    assert "kind" in pg.by_ticker.columns
    assert (pg.by_ticker["kind"] == "stock").sum() == 2
    assert (pg.by_ticker["kind"] == "LONG_CALL").sum() == 1


def test_theta_decay_schedule_zero_when_no_options():
    sched = theta_decay_schedule(None, days_ahead=10)
    assert sched.empty


def test_theta_decay_schedule_cumulative(synth_chain):
    expiry = date.today() + timedelta(days=30)
    open_options = pd.DataFrame([
        {
            "trade_id": "t1", "ticker": "ASTS", "direction": "LONG_CALL",
            "contract_symbol": "ASTS260619C00050000",
            "strike": 50.0, "expiry": expiry, "qty": 2,
        },
    ])

    def fake_fetch(t):  # noqa: ANN001
        return synth_chain

    sched = theta_decay_schedule(open_options, fetch_chain_fn=fake_fetch, days_ahead=5)
    assert len(sched) == 6  # day_offset 0..5 inclusive
    # Cumulative must be monotone (theta is constant negative each day)
    assert all(sched["cum_theta_eur"].diff().dropna() <= 0)


def test_gamma_calendar_returns_one_row_per_position(synth_chain):
    expiry = date.today() + timedelta(days=30)
    open_options = pd.DataFrame([
        {
            "trade_id": "t1", "ticker": "ASTS", "direction": "LONG_CALL",
            "contract_symbol": "ASTS260619C00050000",
            "strike": 50.0, "expiry": expiry, "qty": 2,
        },
        {
            "trade_id": "t2", "ticker": "ASTS", "direction": "LONG_PUT",
            "contract_symbol": "ASTS260619P00040000",
            "strike": 40.0, "expiry": expiry, "qty": 1,
        },
    ])

    def fake_fetch(t):  # noqa: ANN001
        return synth_chain

    cal = gamma_calendar(open_options, fetch_chain_fn=fake_fetch)
    assert len(cal) == 2
    assert {"ticker", "dte_days", "gamma_now", "days_to_half_gamma"}.issubset(cal.columns)
    # gamma_in_7d should be greater than gamma_now (gamma grows as expiry approaches)
    assert (cal["gamma_in_7d"] >= cal["gamma_now"]).all()


def test_beta_weighted_delta_uses_benchmark(stock_portfolio):
    # Synthetic prices with GOOG correlating to SPY but CCJ uncorrelated
    rng = np.random.default_rng(0)
    idx = pd.date_range("2026-01-01", periods=120, freq="B")
    spy_ret = pd.Series(rng.normal(0.0, 0.01, len(idx)), index=idx)
    spy_px = 100 * (1 + spy_ret).cumprod()
    goog_px = 100 * (1 + spy_ret * 1.4).cumprod()  # beta 1.4 vs SPY
    ccj_px = 100 * (1 + rng.normal(0, 0.02, len(idx))).cumprod()
    prices = pd.DataFrame({"GOOG": goog_px, "CCJ": ccj_px, "SPY": spy_px}, index=idx)
    pg = aggregate_greeks(
        portfolio=stock_portfolio,
        open_options_df=None,
        prices_eur=prices,
        benchmark_returns=spy_ret,
    )
    # GOOG beta ≈ 1.4 → β-weighted delta > raw delta
    assert pg.beta_weighted_delta_eur != pg.total_delta_eur
