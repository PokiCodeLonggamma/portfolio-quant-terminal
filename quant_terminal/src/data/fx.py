"""FX layer.

The portfolio is reported in EUR but instruments trade in USD / CAD / GBp / EUR.
Every market value, price series, and return computation goes through here
before reaching the risk engine.

Strategy:
  - Spot rates: yfinance pairs `EURUSD=X`, `EURCAD=X`, `EURGBP=X` (and identity
    for `EUREUR=X`).
  - History rates: same tickers, daily Close. Cached.
  - GBp (London penny) is normalised by /100 before applying EURGBP.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from functools import lru_cache

import pandas as pd

from src.utils.cache import read as cache_read, write as cache_write
from src.utils.logging import get_logger

log = get_logger(__name__)

SUPPORTED_CCYS = {"EUR", "USD", "CAD", "GBP", "GBp", "GBX"}


def _yf_ticker(base: str) -> str:
    """`USD` -> `EURUSD=X` (quote: how many <base> per 1 EUR)."""
    return f"EUR{base}=X"


@lru_cache(maxsize=8)
def spot_rate(target_ccy: str) -> float:
    """1 EUR = `spot_rate(ccy)` units of `ccy`. EUR returns 1.0."""
    target = target_ccy.upper()
    if target in {"EUR"}:
        return 1.0
    if target in {"GBP", "GBX", "GBp"}:
        base = "GBP"
    else:
        base = target
    try:
        import yfinance as yf
        data = yf.Ticker(_yf_ticker(base)).history(period="5d", auto_adjust=False)
        if data is None or data.empty:
            log.warning("FX spot empty for %s; defaulting to 1.0", target_ccy)
            return 1.0
        rate = float(data["Close"].dropna().iloc[-1])
        if target in {"GBX", "GBp"}:
            rate = rate * 100.0  # 1 EUR = X GBp (pence) = 100 * X GBP
        return rate
    except Exception as exc:
        log.warning("FX spot lookup failed for %s: %s; defaulting to 1.0", target_ccy, exc)
        return 1.0


def history_rates(target_ccy: str, start: datetime, end: datetime) -> pd.Series:
    """Daily 1 EUR -> target_ccy rate series. EUR returns ones."""
    target = target_ccy.upper()
    if target == "EUR":
        idx = pd.date_range(start, end, freq="B")
        return pd.Series(1.0, index=idx, name="EUREUR=X")
    base = "GBP" if target in {"GBP", "GBX", "GBP"} else target
    is_pence = target_ccy in {"GBp", "GBX"}

    cache_key = f"fx|{target_ccy}|{start.date()}|{end.date()}"
    cached = cache_read(cache_key, namespace="fx", max_age_seconds=60 * 60 * 24)
    if cached is not None and not cached.empty:
        return cached.iloc[:, 0]

    try:
        import yfinance as yf
        data = yf.download(
            _yf_ticker(base),
            start=start.strftime("%Y-%m-%d"),
            end=(end + timedelta(days=1)).strftime("%Y-%m-%d"),
            progress=False,
            auto_adjust=False,
            threads=False,
        )
        if data is None or data.empty:
            log.warning("FX history empty for %s; falling back to spot constant", target_ccy)
            return pd.Series(spot_rate(target_ccy), index=pd.date_range(start, end, freq="B"))
        if isinstance(data.columns, pd.MultiIndex):
            data.columns = data.columns.get_level_values(0)
        rates = data["Close"].dropna()
        rates.index = pd.to_datetime(rates.index).tz_localize(None).normalize()
        if is_pence:
            rates = rates * 100.0
        rates.name = _yf_ticker(base)
        cache_write(cache_key, rates.to_frame(), namespace="fx")
        return rates
    except Exception as exc:
        log.warning("FX history failed for %s: %s", target_ccy, exc)
        return pd.Series(spot_rate(target_ccy), index=pd.date_range(start, end, freq="B"))


def to_eur(value: float, source_ccy: str) -> float:
    """Convert a scalar from `source_ccy` to EUR using the latest spot."""
    if source_ccy.upper() == "EUR":
        return float(value)
    rate = spot_rate(source_ccy)
    if rate <= 0:
        return float(value)
    return float(value) / rate


def series_to_eur(series: pd.Series, source_ccy: str) -> pd.Series:
    """Convert a price series from `source_ccy` to EUR using daily history rates."""
    if source_ccy.upper() == "EUR":
        return series.copy()
    if series.empty:
        return series
    start, end = series.index.min(), series.index.max()
    rates = history_rates(source_ccy, start, end)
    rates = rates.reindex(series.index).ffill().bfill()
    return series / rates
