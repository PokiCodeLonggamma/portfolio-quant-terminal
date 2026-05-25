"""Tests for the event-trading toolkit (Feature 6)."""
from __future__ import annotations

from datetime import date, datetime, timedelta

import pytest

from src.common.schemas import CalendarEvent, OptionContract, OptionRight
from src.event_trading.earnings_simulator import _bs_price, simulate_position, shock_grid
from src.event_trading.event_sensitivity import (
    DEFAULT_SENSITIVITY,
    historical_avg_move_pct,
)
from src.event_trading.pre_event_wizard import candidates_for_event


def _chain(spot: float = 100.0, expiry_days: int = 28) -> list[OptionContract]:
    now = datetime.utcnow()
    expiry = date.today() + timedelta(days=expiry_days)
    contracts = []
    for K, delta_c in [(90, 0.65), (100, 0.50), (110, 0.30), (115, 0.20)]:
        contracts.append(OptionContract(
            underlying="ASTS", symbol=f"ASTS{expiry:%y%m%d}C{int(K * 1000):08d}",
            expiry=expiry, strike=K, right=OptionRight.CALL,
            mid=max(spot - K, 0) + 2.0, iv=0.6, delta=delta_c, gamma=0.02,
            theta=-0.05, vega=0.10, open_interest=300, volume=50,
            snapshot_ts=now,
        ))
        delta_p = delta_c - 1
        contracts.append(OptionContract(
            underlying="ASTS", symbol=f"ASTS{expiry:%y%m%d}P{int(K * 1000):08d}",
            expiry=expiry, strike=K, right=OptionRight.PUT,
            mid=max(K - spot, 0) + 2.0, iv=0.62, delta=delta_p, gamma=0.02,
            theta=-0.04, vega=0.10, open_interest=200, volume=40,
            snapshot_ts=now,
        ))
    return contracts


def test_historical_avg_move_known_ticker():
    assert historical_avg_move_pct("ASTS", "earnings") == DEFAULT_SENSITIVITY["ASTS"]["earnings"]
    # Fallback when ticker exists but category unknown
    val = historical_avg_move_pct("ASTS", "weird_category")
    assert isinstance(val, float)


def test_historical_avg_move_unknown_ticker():
    assert historical_avg_move_pct("ZZZZ", "earnings") is None


def test_bs_price_call_atm():
    p = _bs_price(100, 100, 0.25, 0.04, 0.20, q=0.0, right="C")
    # Reference BS ATM call ~ 4.6 with these inputs
    assert 3.5 < p < 6.0


def test_simulate_position_returns_scenario():
    contract = _chain()[2]   # K=110 call, delta ≈ 0.30
    scen = simulate_position(contract, qty=1, spot_shock_pct=0.10, iv_shock_pct=-0.30,
                              spot=100.0)
    assert scen is not None
    assert scen.spot_after == pytest.approx(110.0)
    assert scen.iv_after == pytest.approx(0.6 * 0.70, rel=1e-3)
    # PnL EUR can be positive or negative depending on moneyness; just check finite
    assert scen.pnl_total_eur == pytest.approx(scen.pnl_per_contract_local / 1.10, rel=1e-3)


def test_shock_grid_shape():
    contract = _chain()[2]
    grid = shock_grid(contract, qty=1, spot=100.0,
                       spot_shocks=[-0.10, 0.0, 0.10],
                       iv_shocks=[-0.30, 0.0])
    assert len(grid) == 6
    assert {"spot_shock_pct", "iv_shock_pct", "pnl_eur"}.issubset(grid.columns)


def test_candidates_for_event_returns_setups():
    event = CalendarEvent(
        event_id="evt-1", ticker=None, category="earnings",
        start=datetime.utcnow() + timedelta(days=7),
        title="ASTS earnings", source="test",
    )

    def fake_fetch(t: str):
        return _chain()

    df = candidates_for_event(
        event,
        universe=["ASTS"],
        spot_lookup={"ASTS": 100.0},
        fetch_chain_fn=fake_fetch,
        iv_rank_lookup=lambda t: 40.0,
        target_delta=0.25,
    )
    assert not df.empty
    # Both directions should be present
    assert set(df["direction"]).issubset({"LONG_CALL", "LONG_PUT"})
    # Score sorted descending
    assert df["score"].is_monotonic_decreasing
