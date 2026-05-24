"""Short-interest / borrow proxy via yfinance metadata.

yfinance exposes a sparse and stale ``Ticker.info`` dict that occasionally
includes:
    * ``shortRatio``          -> days to cover (volume-based)
    * ``sharesShort``         -> absolute shares short
    * ``shortPercentOfFloat`` -> SI / free float (decimal, e.g. 0.18)
    * ``floatShares``         -> free float

We never raise on missing fields — returning ``None`` lets the dashboard render
a "n/a" cell. A 24h cache keeps us out of yfinance's rate-limit window.
"""
from __future__ import annotations

import pandas as pd

from src.utils.cache import read as cache_read, write as cache_write
from src.utils.config import get_config
from src.utils.logging import get_logger

log = get_logger(__name__)

NAMESPACE = "borrow"
CACHE_TTL_SECONDS = 60 * 60 * 24  # 24h


# ---------------------------------------------------------------------------
# Per-ticker fetch
# ---------------------------------------------------------------------------
def _yf_info(symbol: str) -> dict:
    try:
        import yfinance as yf
    except ImportError:
        log.warning("yfinance not installed; borrow info unavailable")
        return {}
    if not symbol:
        return {}
    try:
        info = yf.Ticker(symbol).info
        return info if isinstance(info, dict) else {}
    except Exception as exc:
        log.debug("yfinance.info failed for %s: %s", symbol, exc)
        return {}


def short_interest(universe_key: str) -> dict:
    """Return a normalised dict of short-interest metrics.

    Keys: ticker, short_interest_pct, days_to_cover, shares_short, float_shares,
          borrow_estimate, source.

    Any field unavailable is ``None``. ``borrow_estimate`` is a coarse bucket:
    "available" if SI% < 10, "hard_to_borrow" if SI% >= 20, else "watch",
    "n/a" if SI% is missing.
    """
    cache_key = f"si|{universe_key}"
    cached = cache_read(cache_key, namespace=NAMESPACE, max_age_seconds=CACHE_TTL_SECONDS)
    if cached is not None and not cached.empty:
        return cached.iloc[0].to_dict()

    cfg = get_config()
    yf_sym = cfg.yfinance_symbol(universe_key)
    info = _yf_info(yf_sym)

    si_pct = info.get("shortPercentOfFloat")
    days_cover = info.get("shortRatio")
    shares_short = info.get("sharesShort")
    float_shares = info.get("floatShares")

    if isinstance(si_pct, (int, float)):
        si_pct = float(si_pct)
        # yfinance returns either a fraction (0.18) or percent (18). Normalise to %.
        if abs(si_pct) <= 1.0:
            si_pct = si_pct * 100.0
    else:
        si_pct = None

    if isinstance(days_cover, (int, float)):
        days_cover = float(days_cover)
    else:
        days_cover = None

    if isinstance(shares_short, (int, float)):
        shares_short = float(shares_short)
    else:
        shares_short = None

    if isinstance(float_shares, (int, float)):
        float_shares = float(float_shares)
    else:
        float_shares = None

    if si_pct is None:
        borrow_estimate = "n/a"
    elif si_pct >= 20:
        borrow_estimate = "hard_to_borrow"
    elif si_pct >= 10:
        borrow_estimate = "watch"
    else:
        borrow_estimate = "available"

    row = {
        "ticker": universe_key,
        "short_interest_pct": si_pct,
        "days_to_cover": days_cover,
        "shares_short": shares_short,
        "float_shares": float_shares,
        "borrow_estimate": borrow_estimate,
        "source": "yfinance.info (estimate)",
    }
    try:
        cache_write(cache_key, pd.DataFrame([row]), namespace=NAMESPACE)
    except Exception as exc:
        log.debug("borrow cache write failed for %s: %s", universe_key, exc)
    return row


def borrow_rate(universe_key: str) -> float | None:
    """Best-effort borrow rate proxy (None — yfinance doesn't expose it).

    Kept for API compatibility with the architect plan; callers should treat
    ``None`` as "unknown" and avoid quoting it.
    """
    return None


def borrow_panel(universe_keys: list[str]) -> pd.DataFrame:
    """Per-ticker borrow snapshot as a DataFrame (one row per key)."""
    rows = [short_interest(k) for k in universe_keys]
    return pd.DataFrame(rows)
