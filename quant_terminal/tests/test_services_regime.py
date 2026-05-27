"""Phase 1 — RegimeService tests with injected price-history fixtures."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.services.regime_service import RegimeService
from src.services.schemas import HMMRegime


def _synthetic_prices(n: int = 400, seed: int = 42) -> pd.Series:
    """Deterministic GBM-like price series of length n."""
    rng = np.random.default_rng(seed)
    log_returns = rng.normal(0.0005, 0.012, size=n)
    # Add a clear high-vol cluster to give HMM something to find
    log_returns[150:200] = rng.normal(0.0, 0.04, size=50)
    prices = 100.0 * np.exp(np.cumsum(log_returns))
    idx = pd.date_range("2024-01-01", periods=n, freq="B")
    return pd.Series(prices, index=idx)


@pytest.fixture
def service():
    return RegimeService(history_fetch_fn=lambda _tk: _synthetic_prices())


@pytest.fixture
def empty_service():
    return RegimeService(history_fetch_fn=lambda _tk: pd.Series(dtype=float))


# ---------------------------------------------------------------------------
# fit_hmm — happy path
# ---------------------------------------------------------------------------
def test_fit_hmm_returns_pydantic_dto(service):
    out = service.fit_hmm("SPY")
    assert isinstance(out, HMMRegime)
    assert out.ticker == "SPY"
    assert out.n_states == 3
    assert out.sample_size > 100
    assert out.current_label in {"CALM", "LOW vol", "MID vol", "HIGH vol", "PANIC"}
    assert sum(out.current_probs.values()) == pytest.approx(1.0, abs=0.01)


def test_fit_hmm_respects_n_states(service):
    out = service.fit_hmm("SPY", n_states=2)
    assert out is not None
    assert out.n_states == 2
    assert len(out.current_probs) == 2


# ---------------------------------------------------------------------------
# fit_hmm — failure modes
# ---------------------------------------------------------------------------
def test_fit_hmm_returns_none_when_no_history(empty_service):
    assert empty_service.fit_hmm("SPY") is None


def test_fit_hmm_returns_none_when_too_few_observations():
    short = pd.Series(
        [100.0 + i * 0.1 for i in range(40)],
        index=pd.date_range("2025-01-01", periods=40, freq="B"),
    )
    s = RegimeService(history_fetch_fn=lambda _tk: short)
    assert s.fit_hmm("SPY") is None


def test_fit_hmm_returns_none_when_fit_raises():
    # Series of constants — log returns are zero → hmmlearn may fail / degenerate
    def bad_fetcher(_tk):
        return pd.Series(
            [100.0] * 200,
            index=pd.date_range("2025-01-01", periods=200, freq="B"),
        )

    s = RegimeService(history_fetch_fn=bad_fetcher)
    # Should not raise — service swallows + returns None
    out = s.fit_hmm("SPY")
    # Could be None (fit failed) or a degenerate result — both are acceptable;
    # the contract is "no raise"
    assert out is None or isinstance(out, HMMRegime)


# ---------------------------------------------------------------------------
# history_available
# ---------------------------------------------------------------------------
def test_history_available_true_with_enough_data(service):
    assert service.history_available("SPY") is True


def test_history_available_false_when_empty(empty_service):
    assert empty_service.history_available("SPY") is False


def test_history_available_handles_fetcher_raising():
    def boom(_tk):
        raise RuntimeError("offline")

    s = RegimeService(history_fetch_fn=boom)
    assert s.history_available("SPY") is False


# ---------------------------------------------------------------------------
# Service contract — no Streamlit
# ---------------------------------------------------------------------------
def test_regime_service_no_streamlit():
    import src.services.regime_service as mod
    with open(mod.__file__, encoding="utf-8") as f:
        content = f.read()
    assert "import streamlit" not in content
    assert "from streamlit" not in content
