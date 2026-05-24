"""Average daily $-volume (ADV) per holding.

Pulls daily volume + close from yfinance (Alpaca lacks volume on many EU
listings), computes a 20D rolling $-volume (in listing currency), and
optionally converts to EUR via the existing FX layer.

Cached at the ``adv`` namespace.
"""
from __future__ import annotations

from datetime import datetime, timedelta

import numpy as np
import pandas as pd

from src.utils.cache import read as cache_read, write as cache_write
from src.utils.config import get_config
from src.utils.logging import get_logger

log = get_logger(__name__)

NAMESPACE = "adv"
CACHE_TTL_SECONDS = 60 * 60 * 24  # 24h
DEFAULT_WINDOW = 20


# ---------------------------------------------------------------------------
# Raw OHLCV puller (yfinance only — needs volume column)
# ---------------------------------------------------------------------------
def _yf_ohlcv(symbol: str, start: datetime, end: datetime) -> pd.DataFrame | None:
    try:
        import yfinance as yf
    except ImportError:
        log.error("yfinance not installed; cannot fetch volume for %s", symbol)
        return None
    if not symbol:
        return None
    try:
        data = yf.download(
            symbol,
            start=start.strftime("%Y-%m-%d"),
            end=end.strftime("%Y-%m-%d"),
            progress=False,
            auto_adjust=False,
            threads=False,
        )
        if data is None or data.empty:
            return None
        if isinstance(data.columns, pd.MultiIndex):
            data.columns = data.columns.get_level_values(0)
        data.index = pd.to_datetime(data.index).tz_localize(None).normalize()
        return data.sort_index()
    except Exception as exc:
        log.warning("yfinance OHLCV failed for %s: %s", symbol, exc)
        return None


def download_volume(
    universe_keys: list[str],
    start: datetime | None = None,
    end: datetime | None = None,
) -> pd.DataFrame:
    """Wide DataFrame (date x universe_key) of ``Close * Volume`` in listing ccy."""
    cfg = get_config()
    if end is None:
        end = datetime.utcnow()
    if start is None:
        start = end - timedelta(days=120)

    series: list[pd.Series] = []
    for key in universe_keys:
        cache_key = f"vol|{key}|{start.date()}|{end.date()}"
        cached = cache_read(cache_key, namespace=NAMESPACE, max_age_seconds=CACHE_TTL_SECONDS)
        if cached is not None and not cached.empty:
            series.append(cached.iloc[:, 0].rename(key))
            continue

        yf_sym = cfg.yfinance_symbol(key)
        ohlcv = _yf_ohlcv(yf_sym, start, end)
        if ohlcv is None or ohlcv.empty:
            log.warning("download_volume: no OHLCV for %s", key)
            continue
        if "Close" not in ohlcv.columns or "Volume" not in ohlcv.columns:
            continue
        dollar_vol = (ohlcv["Close"] * ohlcv["Volume"]).rename(key)
        cache_write(cache_key, dollar_vol.to_frame(), namespace=NAMESPACE)
        series.append(dollar_vol)

    if not series:
        return pd.DataFrame()
    return pd.concat(series, axis=1).sort_index()


# ---------------------------------------------------------------------------
# Aggregates
# ---------------------------------------------------------------------------
def rolling_adv(dollar_vol_panel: pd.DataFrame, window_days: int = DEFAULT_WINDOW) -> pd.DataFrame:
    """Rolling mean of $-volume."""
    if dollar_vol_panel is None or dollar_vol_panel.empty:
        return pd.DataFrame()
    return dollar_vol_panel.rolling(window=window_days, min_periods=max(5, window_days // 2)).mean()


def adv_snapshot(
    dollar_vol_panel: pd.DataFrame,
    window_days: int = DEFAULT_WINDOW,
) -> pd.Series:
    """Latest rolling ADV per ticker (Series indexed by universe_key)."""
    roll = rolling_adv(dollar_vol_panel, window_days=window_days)
    if roll.empty:
        return pd.Series(dtype=float, name="adv_usd")
    last = roll.dropna(how="all").iloc[-1]
    last.name = "adv_usd"
    return last


def adv_panel(
    universe_keys: list[str],
    window_days: int = DEFAULT_WINDOW,
    *,
    start: datetime | None = None,
    end: datetime | None = None,
) -> pd.DataFrame:
    """End-to-end: pull volumes, compute rolling ADV, return per-ticker row.

    Returns columns: ticker, adv_local (listing ccy), adv_usd (=adv_local for
    USD-listed equities; for non-USD we leave the conversion to the caller),
    last_px_local, currency.
    """
    cfg = get_config()
    vol = download_volume(universe_keys, start=start, end=end)
    snap = adv_snapshot(vol, window_days=window_days)
    rows: list[dict] = []
    for key in universe_keys:
        adv_local = float(snap.get(key, np.nan)) if key in snap.index else float("nan")
        currency = cfg.currency_of(key)
        rows.append({
            "ticker": key,
            "adv_local": adv_local,
            "currency": currency,
            "adv_usd": adv_local if currency.upper() == "USD" else float("nan"),
        })
    return pd.DataFrame(rows)
