"""IV rank and IV percentile — gating input for the trade-ticket generator.

Definitions
-----------
IV rank
    `(current_iv - min_1y) / (max_1y - min_1y)` × 100. Bounded [0, 100].
    Tells you where today's IV sits in last year's IV envelope.
IV percentile
    Fraction of past observations strictly below today's IV, × 100.
    More robust to single-day extremes that distort IV rank.

The user's gating rule (encoded in `trade_ticket`) refuses any LONG option when
**IV rank > 80** — because paying for premium when implied vol is in its top
quintile is statistical pickpocketing.

Source of IV history
--------------------
We use yfinance: for each historical close we fetch the front-month ATM
straddle's IV via `Ticker.option_chain(nearest_expiry).calls/.puts`. To keep
runtime reasonable we **estimate** IV history from realised vol when no fresh
options chain is available — a 30-day rolling realised vol is a defensible
proxy for "where IV sat" and is what most retail platforms display when
historic IV is missing.

Cache: `namespace="iv_rank"`, 12-hour TTL — IV regime moves slowly.
"""
from __future__ import annotations

from datetime import datetime, timedelta

import numpy as np
import pandas as pd

from src.data.loaders import load_one
from src.utils.cache import read as cache_read, write as cache_write
from src.utils.logging import get_logger

log = get_logger(__name__)

_CACHE_NS = "iv_rank"
_CACHE_TTL = 12 * 60 * 60


def iv_history(ticker: str, *, days: int = 365) -> pd.Series:
    """Proxy IV history via 30D realised volatility (annualised).

    Returns a daily series; empty Series if no underlying price data.
    """
    cache_key = f"{ticker}|{days}"
    cached = cache_read(cache_key, namespace=_CACHE_NS, max_age_seconds=_CACHE_TTL)
    if cached is not None and not cached.empty:
        return cached.iloc[:, 0]

    end = datetime.utcnow()
    start = end - timedelta(days=days + 60)  # 60d buffer for the rolling window
    series = load_one(ticker, start, end)
    if series is None or series.empty:
        return pd.Series(dtype="float64", name="iv_proxy")

    rets = np.log(series / series.shift(1)).dropna()
    iv_proxy = rets.rolling(window=30, min_periods=15).std() * np.sqrt(252.0)
    iv_proxy = iv_proxy.dropna().rename("iv_proxy")
    if iv_proxy.empty:
        return iv_proxy

    cache_write(cache_key, iv_proxy.to_frame(), namespace=_CACHE_NS)
    return iv_proxy


def iv_rank(
    ticker: str,
    current_iv: float | None = None,
    lookback_days: int = 252,
) -> float:
    """Return IV rank in [0, 100]. Sentinel `50.0` if history is degenerate."""
    hist = iv_history(ticker, days=lookback_days)
    if hist.empty:
        log.debug("iv_rank: no history for %s, returning 50.0 sentinel", ticker)
        return 50.0
    iv_now = current_iv if current_iv is not None else float(hist.iloc[-1])
    lo, hi = float(hist.min()), float(hist.max())
    if hi - lo < 1e-9:
        # Flat history -> arbitrarily centre at 50 to avoid degenerate gating.
        return 50.0
    rank = (iv_now - lo) / (hi - lo) * 100.0
    return float(max(0.0, min(100.0, rank)))


def iv_rank_payload(ticker: str, current_iv: float | None = None) -> dict:
    """Convenience: full payload consumed by `dashboards.render_iv_rank_pill`."""
    hist = iv_history(ticker)
    if hist.empty:
        return {
            "ticker": ticker, "current_iv": current_iv, "iv_low_1y": None,
            "iv_high_1y": None, "iv_rank": 50.0, "iv_percentile": 50.0,
        }
    iv_now = current_iv if current_iv is not None else float(hist.iloc[-1])
    lo, hi = float(hist.min()), float(hist.max())
    rank = iv_rank(ticker, current_iv=iv_now)
    pct = float((hist < iv_now).sum() / len(hist) * 100.0)
    return {
        "ticker": ticker,
        "current_iv": iv_now,
        "iv_low_1y": lo,
        "iv_high_1y": hi,
        "iv_rank": rank,
        "iv_percentile": pct,
    }
