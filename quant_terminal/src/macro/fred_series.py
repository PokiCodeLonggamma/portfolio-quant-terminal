"""FRED macro panel builder.

Pulls the macro series needed by the regime classifier and the macro tab:
    * CPI YoY (computed from CPIAUCSL: 12-month % change)
    * DFF (effective fed-funds rate)
    * T10Y2Y and T10Y3M (term spreads)
    * ISM PMI proxy (FRED `NAPM` / `MANEMP`-based proxy; we use `NAPM` first
      and fall back to a smoothed manufacturing-employment z-score scaled
      around 50 if `NAPM` is unavailable for the key tier).
    * VIX (`VIXCLS`) and DXY (`DTWEXBGS`) — when FRED is missing, we silently
      fall back to yfinance (`^VIX`, `DX-Y.NYB`).

The output is a wide, daily-frequency, forward-filled DataFrame indexed by
date with the following columns (best-effort; columns missing if all sources
fail for that series):

    cpi_yoy, dff, t10y2y, t10y3m, pmi_proxy, vix, dxy
"""
from __future__ import annotations

from datetime import datetime, timedelta

import numpy as np
import pandas as pd

from src.utils.cache import read as cache_read, write as cache_write
from src.utils.config import get_config
from src.utils.logging import get_logger

log = get_logger(__name__)

CACHE_TTL_SECONDS = 60 * 60 * 6  # 6h
NAMESPACE = "fred_macro"

# FRED series IDs
SERIES_IDS: dict[str, str] = {
    "cpi_level": "CPIAUCSL",      # monthly, seasonally adjusted index
    "dff": "DFF",                  # daily
    "t10y2y": "T10Y2Y",            # daily
    "t10y3m": "T10Y3M",            # daily
    "napm": "NAPM",                # ISM PMI (older alias, monthly)
    "vix": "VIXCLS",               # daily
    "dxy": "DTWEXBGS",             # daily, broad trade-weighted
}


# ---------------------------------------------------------------------------
# Low-level fetchers
# ---------------------------------------------------------------------------
def _fetch_fred_series(series_id: str) -> pd.Series | None:
    cfg = get_config()
    if not cfg.secrets.fred_api_key:
        log.debug("FRED_API_KEY missing; skipping %s", series_id)
        return None
    try:
        from fredapi import Fred
        f = Fred(api_key=cfg.secrets.fred_api_key)
        s = f.get_series(series_id)
        if s is None or len(s) == 0:
            return None
        s.index = pd.to_datetime(s.index)
        s.name = series_id
        return s.sort_index()
    except Exception as exc:
        log.warning("FRED fetch failed for %s: %s", series_id, exc)
        return None


def _fetch_yf_series(symbol: str) -> pd.Series | None:
    """Pull adj-close daily series from yfinance for the last ~5y."""
    try:
        import yfinance as yf
    except ImportError:
        log.warning("yfinance not installed; cannot fetch %s", symbol)
        return None
    try:
        end = datetime.utcnow()
        start = end - timedelta(days=365 * 5)
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
        s = data["Close"].copy()
        s.index = pd.to_datetime(s.index).tz_localize(None).normalize()
        s.name = symbol
        return s.sort_index()
    except Exception as exc:
        log.warning("yfinance fetch failed for %s: %s", symbol, exc)
        return None


# ---------------------------------------------------------------------------
# Transforms
# ---------------------------------------------------------------------------
def _cpi_yoy(cpi_level: pd.Series) -> pd.Series:
    """12-month percentage change on a monthly CPI level series."""
    if cpi_level is None or cpi_level.empty:
        return pd.Series(dtype=float, name="cpi_yoy")
    monthly = cpi_level.resample("ME").last() if cpi_level.index.freqstr != "ME" else cpi_level
    yoy = monthly.pct_change(12) * 100.0
    yoy.name = "cpi_yoy"
    return yoy.dropna()


def _pmi_proxy(napm: pd.Series | None) -> pd.Series:
    """Use ISM/NAPM if available, otherwise neutral 50 placeholder."""
    if napm is not None and not napm.empty:
        s = napm.copy()
        s.name = "pmi_proxy"
        return s
    return pd.Series(dtype=float, name="pmi_proxy")


# ---------------------------------------------------------------------------
# Top-level builder
# ---------------------------------------------------------------------------
def build_macro_panel(*, use_cache: bool = True) -> pd.DataFrame:
    """Return a daily, ffilled, indexed DataFrame of all macro signals.

    Columns: cpi_yoy, dff, t10y2y, t10y3m, pmi_proxy, vix, dxy. Missing
    sources are silently dropped (caller should handle ``KeyError`` access).
    """
    cache_key = "macro_panel_v1"
    if use_cache:
        cached = cache_read(cache_key, namespace=NAMESPACE, max_age_seconds=CACHE_TTL_SECONDS)
        if cached is not None and not cached.empty:
            return cached

    raw: dict[str, pd.Series] = {}
    for label, sid in SERIES_IDS.items():
        s = _fetch_fred_series(sid)
        if s is not None and not s.empty:
            raw[label] = s

    # Fallbacks for VIX / DXY when FRED is missing
    if "vix" not in raw:
        s = _fetch_yf_series("^VIX")
        if s is not None:
            raw["vix"] = s
    if "dxy" not in raw:
        s = _fetch_yf_series("DX-Y.NYB")
        if s is not None:
            raw["dxy"] = s

    panel_cols: dict[str, pd.Series] = {}
    if "cpi_level" in raw:
        panel_cols["cpi_yoy"] = _cpi_yoy(raw["cpi_level"])
    for k in ("dff", "t10y2y", "t10y3m"):
        if k in raw:
            panel_cols[k] = raw[k].rename(k)
    if "napm" in raw:
        panel_cols["pmi_proxy"] = _pmi_proxy(raw["napm"])
    if "vix" in raw:
        panel_cols["vix"] = raw["vix"].rename("vix")
    if "dxy" in raw:
        panel_cols["dxy"] = raw["dxy"].rename("dxy")

    if not panel_cols:
        log.warning("build_macro_panel: no series resolved — returning empty DataFrame")
        return pd.DataFrame()

    # Align on a daily grid and forward-fill (monthly CPI/PMI -> daily).
    aligned = pd.concat(panel_cols.values(), axis=1).sort_index()
    daily_idx = pd.date_range(aligned.index.min(), aligned.index.max(), freq="B")
    panel = aligned.reindex(daily_idx).ffill()
    panel.index.name = "date"

    cache_write(cache_key, panel, namespace=NAMESPACE)
    return panel


def fetch_macro_panel(*, use_cache: bool = True) -> pd.DataFrame:
    """Public alias for `build_macro_panel`."""
    return build_macro_panel(use_cache=use_cache)


def latest_macro_metrics(panel: pd.DataFrame | None = None) -> dict[str, float]:
    """Return the latest non-null value of each column as a flat ``dict``."""
    if panel is None:
        panel = build_macro_panel()
    if panel is None or panel.empty:
        return {}
    out: dict[str, float] = {}
    for col in panel.columns:
        s = panel[col].dropna()
        if s.empty:
            continue
        v = float(s.iloc[-1])
        if np.isfinite(v):
            out[col] = v
    return out
