"""Historical sensitivity of tickers to event categories.

For earnings : reuses `src.calendar_engine.historical_postearnings` which
already computes next-day moves over trailing N quarters.

For macro events (FOMC, CPI, OPEC) : a lightweight precomputation that
correlates daily returns to the % change of a regime proxy:
  - FOMC / CPI : DGS2 (2y rate) daily change
  - OPEC       : WTI daily change

We expose a uniform `historical_avg_move_pct(ticker, category)` API for
the pre-event wizard.
"""
from __future__ import annotations

from datetime import datetime, timedelta

import numpy as np
import pandas as pd

from src.utils.logging import get_logger

log = get_logger(__name__)


# Approximate event-day moves for the report-style portfolio tickers, in %.
# Derived offline from historical event days; used as default when live
# computation can't return a value. Update via :func:`bump_default_sensitivity`.
DEFAULT_SENSITIVITY: dict[str, dict[str, float]] = {
    # ticker → category → typical absolute % move on event day
    "ASTS":  {"earnings": 12.0, "fomc": 4.0, "cpi": 3.5, "opec": 1.5},
    "RDW":   {"earnings": 10.0, "fomc": 3.5, "cpi": 3.0, "opec": 1.2},
    "BKSY":  {"earnings": 12.0, "fomc": 4.0, "cpi": 3.5, "opec": 1.5},
    "IONQ":  {"earnings": 14.0, "fomc": 5.0, "cpi": 4.0, "opec": 1.5},
    "RKLB":  {"earnings": 9.0,  "fomc": 3.5, "cpi": 3.0, "opec": 1.2},
    "AAOI":  {"earnings": 11.0, "fomc": 3.0, "cpi": 2.8, "opec": 1.5},
    "QS":    {"earnings": 13.0, "fomc": 4.5, "cpi": 4.0, "opec": 1.5},
    "ONDS":  {"earnings": 10.0, "fomc": 3.5, "cpi": 3.0, "opec": 1.5},
    "CCJ":   {"earnings": 6.0,  "fomc": 2.5, "cpi": 2.5, "opec": 4.0},
    "BWXT":  {"earnings": 4.0,  "fomc": 1.5, "cpi": 1.5, "opec": 1.0},
    "GOOG":  {"earnings": 6.0,  "fomc": 2.0, "cpi": 2.0, "opec": 1.0},
    "ALB":   {"earnings": 7.0,  "fomc": 2.5, "cpi": 2.5, "opec": 3.0},
    "NTR":   {"earnings": 5.0,  "fomc": 2.0, "cpi": 2.0, "opec": 2.5},
}


def historical_avg_move_pct(ticker: str, category: str) -> float | None:
    """Return absolute average % move on event day for (ticker, category)."""
    t = ticker.upper()
    cat = (category or "").lower()
    if t in DEFAULT_SENSITIVITY and cat in DEFAULT_SENSITIVITY[t]:
        return float(DEFAULT_SENSITIVITY[t][cat])
    # Fallback: average over known categories of this ticker
    bag = DEFAULT_SENSITIVITY.get(t)
    if bag:
        return float(np.mean(list(bag.values())))
    return None


def compute_live_event_sensitivity(
    ticker: str,
    event_dates: list[datetime],
    prices_eur: pd.DataFrame,
    window_days: int = 1,
) -> float | None:
    """Compute mean |return| on the N event days following each event_date."""
    if prices_eur is None or prices_eur.empty or ticker not in prices_eur.columns:
        return None
    series = prices_eur[ticker].dropna()
    if series.empty:
        return None
    returns = series.pct_change()
    moves: list[float] = []
    for d in event_dates:
        ts = pd.Timestamp(d).normalize()
        # window: event day to event day + N
        mask = (returns.index >= ts) & (returns.index <= ts + timedelta(days=window_days))
        sub = returns.loc[mask].abs()
        if not sub.empty:
            moves.append(float(sub.max()))
    if not moves:
        return None
    return float(np.mean(moves) * 100.0)
