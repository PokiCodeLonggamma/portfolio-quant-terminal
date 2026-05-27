"""Regime service — wraps the HMM module and price-history loader.

Returns Pydantic DTOs (:class:`HMMRegime`) suitable for the FastAPI surface
(``/api/regime/hmm``) and Streamlit dashboards.

Network is dependency-injected so tests pass a stub price series.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Callable

import numpy as np
import pandas as pd

from src.regime.hmm import fit_volatility_hmm
from src.services.schemas import HMMRegime


# ---------------------------------------------------------------------------
# Default price-history fetcher — yfinance daily Close, 600 days
# ---------------------------------------------------------------------------
def _yfinance_history_fetcher(ticker: str, *, period: str = "600d") -> pd.Series:
    """Production fetcher — daily Close series, log-returns ready.

    Returns an empty Series if anything goes wrong.
    """
    try:
        import yfinance as yf
        hist = yf.download(
            ticker, period=period, progress=False,
            auto_adjust=True, threads=False,
        )
        if hist is None or hist.empty:
            return pd.Series(dtype=float)
        if isinstance(hist.columns, pd.MultiIndex):
            hist.columns = hist.columns.get_level_values(0)
        return hist["Close"].dropna()
    except Exception:
        return pd.Series(dtype=float)


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------
@dataclass
class RegimeService:
    """Pure orchestration over the HMM volatility regime engine."""
    history_fetch_fn: Callable[[str], pd.Series] = _yfinance_history_fetcher

    # -------------------------------------------------------------------------
    # fit_hmm
    # -------------------------------------------------------------------------
    def fit_hmm(
        self,
        ticker: str,
        *,
        n_states: int = 3,
        min_observations: int = 60,
    ) -> HMMRegime | None:
        """Fit a Gaussian HMM and return a small DTO.

        Returns ``None`` when:
        - The price series is empty
        - There are fewer than ``min_observations`` log-returns
        - The HMM fit raises (e.g. hmmlearn convergence error)

        FastAPI handler should map ``None`` to a 503.
        """
        prices = self.history_fetch_fn(ticker)
        if prices is None or prices.empty:
            return None
        log_returns = np.log(prices / prices.shift(1)).dropna()
        if len(log_returns) < min_observations:
            return None
        try:
            res = fit_volatility_hmm(log_returns, n_states=n_states)
        except Exception:
            return None
        return HMMRegime(
            ticker=ticker,
            current_label=res.current_label,
            current_probs={k: float(v) for k, v in res.current_probs.items()},
            n_states=res.n_states,
            sample_size=len(log_returns),
            asof=datetime.utcnow(),
        )

    # -------------------------------------------------------------------------
    # availability
    # -------------------------------------------------------------------------
    def history_available(self, ticker: str, *, min_observations: int = 60) -> bool:
        """Cheap check — enough price history to even attempt a fit?"""
        try:
            prices = self.history_fetch_fn(ticker)
        except Exception:
            return False
        return prices is not None and len(prices) >= min_observations
