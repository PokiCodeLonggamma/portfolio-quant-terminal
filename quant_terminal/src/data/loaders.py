"""Multi-provider price loader.

Resolution order per ticker key:
  1. Alpaca (if credentials available AND the universe declares an alpaca symbol)
  2. yfinance silent fallback (used for EU ETPs, TSX, ETCs, or whenever Alpaca
     misses the symbol)

The loader operates in batch over a list of universe keys, returns a wide
DataFrame indexed by trading day with one column per key, in the **listing
currency** of the instrument. FX normalisation lives in
`src.portfolio.analytics` / `src.data.fx`.

A parquet cache (24h TTL) sits in front to avoid hammering APIs during dev.
"""
from __future__ import annotations

from datetime import datetime, timedelta

import pandas as pd

from src.utils.cache import read as cache_read, write as cache_write
from src.utils.config import get_config
from src.utils.logging import get_logger

log = get_logger(__name__)

CACHE_TTL_SECONDS = 60 * 60 * 24  # 24h


def _alpaca_history(symbol: str, start: datetime, end: datetime) -> pd.Series | None:
    """Return Adj Close series via Alpaca, or None on any failure (silent fallback)."""
    cfg = get_config()
    if not cfg.secrets.has_alpaca or not symbol:
        return None
    try:
        from alpaca.data.historical import StockHistoricalDataClient
        from alpaca.data.requests import StockBarsRequest
        from alpaca.data.timeframe import TimeFrame
    except ImportError:
        log.warning("alpaca-py not installed; skipping Alpaca for %s", symbol)
        return None

    try:
        client = StockHistoricalDataClient(cfg.secrets.alpaca_key_id, cfg.secrets.alpaca_secret_key)
        req = StockBarsRequest(
            symbol_or_symbols=symbol,
            timeframe=TimeFrame.Day,
            start=start,
            end=end,
        )
        bars = client.get_stock_bars(req)
        df = bars.df
        if df is None or df.empty:
            return None
        # Multi-index (symbol, timestamp) -> flatten
        if isinstance(df.index, pd.MultiIndex):
            df = df.xs(symbol, level=0)
        close = df["close"].copy()
        close.index = pd.to_datetime(close.index).tz_localize(None).normalize()
        close.name = symbol
        return close.sort_index()
    except Exception as exc:
        log.info("Alpaca failed for %s: %s -- falling back", symbol, exc)
        return None


def _yfinance_history(symbol: str, start: datetime, end: datetime) -> pd.Series | None:
    if not symbol:
        return None
    try:
        import yfinance as yf
    except ImportError:
        log.error("yfinance not installed; cannot fallback for %s", symbol)
        return None
    try:
        data = yf.download(
            symbol,
            start=start.strftime("%Y-%m-%d"),
            end=end.strftime("%Y-%m-%d"),
            progress=False,
            auto_adjust=True,
            threads=False,
        )
        if data is None or data.empty:
            return None
        if isinstance(data.columns, pd.MultiIndex):
            data.columns = data.columns.get_level_values(0)
        close = data["Close"].copy()
        close.index = pd.to_datetime(close.index).tz_localize(None).normalize()
        close.name = symbol
        return close.sort_index()
    except Exception as exc:
        log.warning("yfinance failed for %s: %s", symbol, exc)
        return None


def load_one(universe_key: str, start: datetime, end: datetime) -> pd.Series | None:
    """Load a single ticker (Alpaca first, yfinance fallback) with cache."""
    cache_key = f"{universe_key}|{start.date()}|{end.date()}"
    cached = cache_read(cache_key, namespace="prices", max_age_seconds=CACHE_TTL_SECONDS)
    if cached is not None and not cached.empty:
        return cached.iloc[:, 0]

    cfg = get_config()
    alpaca_sym = cfg.alpaca_symbol(universe_key)
    yf_sym = cfg.yfinance_symbol(universe_key)

    series: pd.Series | None = None
    if alpaca_sym:
        series = _alpaca_history(alpaca_sym, start, end)
    if series is None or series.empty:
        series = _yfinance_history(yf_sym, start, end)

    if series is None or series.empty:
        log.warning("No data resolved for %s (alpaca=%s, yf=%s)", universe_key, alpaca_sym, yf_sym)
        return None

    series.name = universe_key
    cache_write(cache_key, series.to_frame(), namespace="prices")
    return series


def download_prices(
    universe_keys: list[str],
    start: datetime | str | None = None,
    end: datetime | str | None = None,
) -> pd.DataFrame:
    """Batch loader. Returns wide DataFrame (date x universe_key) in listing currency."""
    if end is None:
        end = datetime.utcnow()
    if isinstance(end, str):
        end = datetime.fromisoformat(end)
    if start is None:
        years = int(get_config().settings.get("history_years", 3))
        start = end - timedelta(days=365 * years)
    if isinstance(start, str):
        start = datetime.fromisoformat(start)

    series_list: list[pd.Series] = []
    for key in universe_keys:
        s = load_one(key, start, end)
        if s is not None:
            series_list.append(s)
    if not series_list:
        return pd.DataFrame()
    return pd.concat(series_list, axis=1).sort_index()
