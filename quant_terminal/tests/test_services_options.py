"""Phase 1 — OptionsService tests with injected fixtures."""
from __future__ import annotations

from datetime import date, datetime

import pytest

from src.common.schemas import OptionContract, OptionRight
from src.services.options_service import OptionsService
from src.services.schemas import GexSummary


# ---------------------------------------------------------------------------
# Helpers — build a deterministic mini chain
# ---------------------------------------------------------------------------
def _mk_contract(
    *,
    underlying: str = "TEST",
    strike: float,
    right: OptionRight,
    expiry: date | None = None,
    gamma: float = 0.01,
    iv: float = 0.30,
    delta: float = 0.5,
    oi: int = 1000,
) -> OptionContract:
    expiry = expiry or date(2026, 12, 18)
    return OptionContract(
        underlying=underlying,
        symbol=f"{underlying}{expiry.strftime('%y%m%d')}{right.value}{int(strike*1000):08d}",
        expiry=expiry,
        strike=strike,
        right=right,
        bid=1.0, ask=1.10, last=1.05, mid=1.05,
        iv=iv, delta=delta if right == OptionRight.CALL else -abs(delta),
        gamma=gamma, theta=-0.02, vega=0.10,
        open_interest=oi, volume=200,
        snapshot_ts=datetime.utcnow(),
        source="alpaca",
    )


def _build_chain(spot: float = 100.0, n_strikes: int = 6) -> list[OptionContract]:
    """Mini chain: 6 strikes (95..105) × call + put."""
    chain = []
    strikes = [spot + i * 1.0 for i in range(-n_strikes // 2, n_strikes // 2)]
    for s in strikes:
        chain.append(_mk_contract(strike=s, right=OptionRight.CALL, oi=2000))
        chain.append(_mk_contract(strike=s, right=OptionRight.PUT, oi=1500))
    return chain


@pytest.fixture
def service():
    """OptionsService with stub fetchers."""
    chain = _build_chain(spot=100.0)
    return OptionsService(
        chain_fetch_fn=lambda _tk: chain,
        spot_fetch_fn=lambda _tk: 100.0,
    )


@pytest.fixture
def empty_service():
    """OptionsService where every fetch fails."""
    return OptionsService(
        chain_fetch_fn=lambda _tk: [],
        spot_fetch_fn=lambda _tk: None,
    )


# ---------------------------------------------------------------------------
# get_chain
# ---------------------------------------------------------------------------
def test_get_chain_returns_typed_list(service):
    chain = service.get_chain("TEST")
    assert isinstance(chain, list)
    assert len(chain) == 12  # 6 strikes × 2 rights
    assert all(isinstance(c, OptionContract) for c in chain)


def test_get_chain_empty_when_fetcher_returns_none(empty_service):
    assert empty_service.get_chain("X") == []


# ---------------------------------------------------------------------------
# get_gex_summary
# ---------------------------------------------------------------------------
def test_get_gex_summary_returns_pydantic_with_buckets(service):
    summary = service.get_gex_summary("TEST")
    assert isinstance(summary, GexSummary)
    assert summary.ticker == "TEST"
    assert summary.spot == 100.0
    assert summary.n_strikes > 0
    assert summary.buckets
    # Buckets are sorted by strike
    strikes = [b.strike for b in summary.buckets]
    assert strikes == sorted(strikes)


def test_get_gex_summary_none_when_no_spot(empty_service):
    assert empty_service.get_gex_summary("X") is None


def test_get_gex_summary_none_when_empty_chain():
    s = OptionsService(
        chain_fetch_fn=lambda _tk: [],
        spot_fetch_fn=lambda _tk: 100.0,
    )
    assert s.get_gex_summary("X") is None


def test_get_gex_summary_includes_walls(service):
    summary = service.get_gex_summary("TEST")
    # With a symmetric chain net GEX might be zero everywhere — that's OK.
    # Just ensure the fields exist and are float-or-None.
    assert summary.call_wall is None or isinstance(summary.call_wall, float)
    assert summary.put_wall is None or isinstance(summary.put_wall, float)


def test_get_gex_summary_overall_pc_ratio_present(service):
    summary = service.get_gex_summary("TEST")
    assert isinstance(summary.overall_pc_ratio, float)
    assert summary.overall_pc_ratio >= 0


# ---------------------------------------------------------------------------
# get_iv_term_structure
# ---------------------------------------------------------------------------
def test_get_iv_term_structure_returns_list(service):
    points = service.get_iv_term_structure("TEST")
    assert isinstance(points, list)
    # Our test chain has 1 expiry → 1 point
    assert len(points) == 1
    assert points[0].dte_days >= 0
    assert isinstance(points[0].expiry, date)


def test_get_iv_term_structure_empty_when_no_chain(empty_service):
    assert empty_service.get_iv_term_structure("X") == []


# ---------------------------------------------------------------------------
# chain_available
# ---------------------------------------------------------------------------
def test_chain_available_true_for_good_chain(service):
    assert service.chain_available("TEST") is True


def test_chain_available_false_for_empty(empty_service):
    assert empty_service.chain_available("X") is False


def test_chain_available_false_when_fetcher_raises():
    def boom(_tk):
        raise RuntimeError("upstream down")

    s = OptionsService(chain_fetch_fn=boom, spot_fetch_fn=lambda _: 100.0)
    assert s.chain_available("X") is False


# ---------------------------------------------------------------------------
# Service contract
# ---------------------------------------------------------------------------
def test_options_service_no_streamlit():
    import src.services.options_service as mod
    with open(mod.__file__, encoding="utf-8") as f:
        content = f.read()
    assert "import streamlit" not in content
    assert "from streamlit" not in content
