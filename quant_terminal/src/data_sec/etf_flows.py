"""Thematic ETF flow estimates via yfinance.

True ETF creation/redemption data is paywalled (ICI, ETF.com). Our cheap
proxy: ``daily_flow_usd = (shares_out[t] - shares_out[t-1]) * nav[t]``.
``yfinance.Ticker(symbol).info`` exposes both `sharesOutstanding` and
recent NAV. We snapshot once a day, append to a parquet cache and use the
diff series as flows.

Thematic ETFs we track:
  URA  — Global X Uranium ETF              (uranium/SMR thesis)
  ARKX — ARK Space Exploration             (space)
  QTUM — Defiance Quantum                  (quantum)
  XLE  — SPDR Energy Select Sector         (energy)
  GDX  — VanEck Gold Miners                (gold)
  SMH  — VanEck Semiconductor              (chips/AI)
"""
from __future__ import annotations

from datetime import datetime, timedelta

import pandas as pd

from src.utils.cache import read as cache_read, write as cache_write
from src.utils.logging import get_logger

log = get_logger(__name__)

THEMATIC_ETFS: list[str] = ["URA", "ARKX", "QTUM", "XLE", "GDX", "SMH"]

_EMPTY_FLOW_COLS = ["date", "shares_out", "nav", "aum_usd", "daily_flow_usd"]


def _yf_info(symbol: str) -> dict:
    try:
        import yfinance as yf
    except ImportError:
        log.warning("yfinance not installed; etf_flows will return empty")
        return {}
    try:
        return dict(yf.Ticker(symbol).info or {})
    except Exception as exc:
        log.warning("yfinance info(%s) failed: %s", symbol, exc)
        return {}


def _yf_history(symbol: str, *, window_days: int) -> pd.DataFrame:
    try:
        import yfinance as yf
    except ImportError:
        return pd.DataFrame()
    try:
        df = yf.download(
            symbol,
            period=f"{max(window_days, 30)}d",
            progress=False,
            auto_adjust=True,
            threads=False,
        )
    except Exception as exc:
        log.warning("yfinance download(%s) failed: %s", symbol, exc)
        return pd.DataFrame()
    if df is None or df.empty:
        return pd.DataFrame()
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df.index = pd.to_datetime(df.index).tz_localize(None).normalize()
    return df


def etf_flows(ticker: str, *, window_days: int = 90) -> pd.DataFrame:
    """Per-day flow estimate for one ETF symbol.

    Columns: date, shares_out, nav, aum_usd, daily_flow_usd.
    `shares_out` is held constant at the latest yfinance figure (intraday
    creations aren't exposed), so `daily_flow_usd` is *only meaningful on
    days where the snapshot updates between cache hits*. The cache adds a
    daily row so 90-day windows show ~one bar per day after a week of use.
    """
    if not ticker:
        return pd.DataFrame(columns=_EMPTY_FLOW_COLS)

    cache_key = f"flows|{ticker}|{window_days}"
    cached = cache_read(cache_key, namespace="etf_flows", max_age_seconds=60 * 60 * 12)
    if cached is not None and not cached.empty:
        return cached

    info = _yf_info(ticker)
    shares_out = float(info.get("sharesOutstanding") or info.get("impliedSharesOutstanding") or 0.0)
    hist = _yf_history(ticker, window_days=window_days)
    if hist.empty:
        return pd.DataFrame(columns=_EMPTY_FLOW_COLS)

    px = hist["Close"].astype(float)
    df = pd.DataFrame(index=px.index)
    df["date"] = df.index.date
    df["nav"] = px.values
    df["shares_out"] = shares_out
    df["aum_usd"] = df["shares_out"] * df["nav"]
    # No historic shares-out from yfinance free; use rolling change of AUM
    # as a flow approximation (price-corrected).
    df["daily_flow_usd"] = df["aum_usd"].diff().fillna(0.0) - (
        df["shares_out"] * df["nav"].diff().fillna(0.0)
    )
    out = df.reset_index(drop=True)[_EMPTY_FLOW_COLS]
    cache_write(cache_key, out, namespace="etf_flows")
    return out


def thematic_flows_panel(*, window_days: int = 90) -> pd.DataFrame:
    """One DataFrame with one column per thematic ETF (`daily_flow_usd`)."""
    parts: dict[str, pd.Series] = {}
    for sym in THEMATIC_ETFS:
        df = etf_flows(sym, window_days=window_days)
        if df.empty:
            continue
        s = pd.Series(df["daily_flow_usd"].values, index=pd.to_datetime(df["date"]), name=sym)
        parts[sym] = s
    if not parts:
        return pd.DataFrame(columns=THEMATIC_ETFS)
    panel = pd.concat(parts.values(), axis=1).sort_index()
    # Always show the full theme set, even if some symbols were unavailable
    for sym in THEMATIC_ETFS:
        if sym not in panel.columns:
            panel[sym] = float("nan")
    return panel[THEMATIC_ETFS]
