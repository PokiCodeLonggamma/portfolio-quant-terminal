"""Historical post-earnings move analysis.

Given a ticker, queries yfinance for the trailing 8 earnings prints, then
computes the next-trading-day return on each release date.

Public API
----------
* `post_earnings_history(ticker, n_quarters=8) -> pd.DataFrame`
  Columns: ``quarter, eps_estimate, eps_actual, eps_surprise_pct,
  next_day_move_pct``.
* `avg_next_day_move(ticker, n_quarters=8) -> float | None`
  Convenience aggregate used by the earnings board.
"""
from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd

from src.utils.config import get_config
from src.utils.logging import get_logger

log = get_logger(__name__)


_COLUMNS = [
    "quarter", "eps_estimate", "eps_actual", "eps_surprise_pct",
    "next_day_move_pct",
]


def _safe_dataframe() -> pd.DataFrame:
    return pd.DataFrame(columns=_COLUMNS)


def _coerce_eps_table(raw: pd.DataFrame | None) -> pd.DataFrame:
    """Normalise a yfinance ``earnings_dates`` DataFrame.

    The columns differ across yfinance versions; we try several aliases.
    """
    if raw is None or raw.empty:
        return pd.DataFrame()

    df = raw.copy()
    df.columns = [str(c) for c in df.columns]
    rename: dict[str, str] = {}
    for col in df.columns:
        lc = col.lower()
        if "estimate" in lc:
            rename[col] = "eps_estimate"
        elif "reported" in lc or "actual" in lc:
            rename[col] = "eps_actual"
        elif "surprise(%)" in lc or "surprise %" in lc or "surprise_pct" in lc or "surprise" in lc:
            rename[col] = "eps_surprise_pct"
    df = df.rename(columns=rename)
    if "eps_estimate" not in df.columns:
        df["eps_estimate"] = np.nan
    if "eps_actual" not in df.columns:
        df["eps_actual"] = np.nan
    if "eps_surprise_pct" not in df.columns:
        df["eps_surprise_pct"] = np.nan
    df["eps_estimate"] = pd.to_numeric(df["eps_estimate"], errors="coerce")
    df["eps_actual"] = pd.to_numeric(df["eps_actual"], errors="coerce")
    df["eps_surprise_pct"] = pd.to_numeric(df["eps_surprise_pct"], errors="coerce")
    # ensure the index is a DatetimeIndex
    try:
        df.index = pd.to_datetime(df.index, errors="coerce", utc=False)
    except Exception:
        pass
    return df


def post_earnings_history(
    ticker: str, n_quarters: int = 8, *, yf_module=None,
) -> pd.DataFrame:
    """Return ≤``n_quarters`` rows of historical earnings + next-day moves.

    Parameters
    ----------
    ticker
        Universe ticker.
    n_quarters
        Maximum number of past quarters to include.
    yf_module
        Optional yfinance-like module override (used by tests).
    """
    cfg = get_config()
    yf_sym = cfg.yfinance_symbol(ticker) or ticker
    if yf_module is None:
        try:
            import yfinance as yf
            yf_module = yf
        except ImportError:
            log.error("yfinance not installed; cannot build post-earnings history")
            return _safe_dataframe()
    try:
        tk = yf_module.Ticker(yf_sym)
    except Exception as exc:
        log.debug("yfinance Ticker init failed for %s: %s", yf_sym, exc)
        return _safe_dataframe()

    # earnings_dates is the modern API; fall back to .earnings_history if missing
    raw: pd.DataFrame | None = None
    for attr in ("earnings_dates", "earnings_history", "get_earnings_dates"):
        try:
            value = getattr(tk, attr, None)
            if callable(value):
                value = value()
            if isinstance(value, pd.DataFrame) and not value.empty:
                raw = value
                break
        except Exception as exc:
            log.debug("yfinance.%s failed for %s: %s", attr, yf_sym, exc)

    eps_df = _coerce_eps_table(raw)
    if eps_df.empty:
        return _safe_dataframe()

    today = pd.Timestamp(date.today())
    past = eps_df[eps_df.index <= today]
    if past.empty:
        return _safe_dataframe()
    past = past.sort_index(ascending=False).head(n_quarters)

    # price history covering the earliest earnings date - 5d to today
    start = (past.index.min() - pd.Timedelta(days=10)).date()
    end = (today + pd.Timedelta(days=2)).date()
    try:
        hist = tk.history(start=start, end=end, auto_adjust=False)
    except Exception as exc:
        log.debug("yfinance.history failed for %s: %s", yf_sym, exc)
        hist = pd.DataFrame()
    if isinstance(hist, pd.DataFrame) and not hist.empty:
        try:
            hist.index = pd.to_datetime(hist.index).tz_localize(None)
        except (TypeError, AttributeError):
            hist.index = pd.to_datetime(hist.index)
        close = hist.get("Close")
    else:
        close = pd.Series(dtype=float)

    out_rows: list[dict] = []
    for ts, row in past.iterrows():
        try:
            ts_naive = pd.Timestamp(ts).tz_localize(None)
        except (TypeError, AttributeError):
            ts_naive = pd.Timestamp(ts)
        next_day_move = np.nan
        if isinstance(close, pd.Series) and not close.empty:
            # Look up the report-day close (or previous trading day) vs next-day close.
            try:
                pre_idx = close.index[close.index <= ts_naive]
                post_idx = close.index[close.index > ts_naive]
                if len(pre_idx) and len(post_idx):
                    pre_px = float(close.loc[pre_idx[-1]])
                    post_px = float(close.loc[post_idx[0]])
                    if pre_px > 0:
                        next_day_move = (post_px / pre_px) - 1.0
            except Exception as exc:
                log.debug("next-day move lookup failed for %s @ %s: %s", ticker, ts, exc)
        quarter = f"{ts_naive.year}Q{((ts_naive.month - 1) // 3) + 1}"
        out_rows.append({
            "quarter": quarter,
            "eps_estimate": (
                float(row["eps_estimate"]) if pd.notna(row.get("eps_estimate")) else None
            ),
            "eps_actual": (
                float(row["eps_actual"]) if pd.notna(row.get("eps_actual")) else None
            ),
            "eps_surprise_pct": (
                float(row["eps_surprise_pct"]) if pd.notna(row.get("eps_surprise_pct")) else None
            ),
            "next_day_move_pct": (
                float(next_day_move) if pd.notna(next_day_move) else None
            ),
        })
    return pd.DataFrame(out_rows, columns=_COLUMNS)


def avg_next_day_move(ticker: str, n_quarters: int = 8) -> float | None:
    """Mean of the absolute next-day moves over the last `n_quarters`."""
    df = post_earnings_history(ticker, n_quarters=n_quarters)
    if df.empty:
        return None
    moves = pd.to_numeric(df["next_day_move_pct"], errors="coerce").abs().dropna()
    if moves.empty:
        return None
    return float(moves.mean())
