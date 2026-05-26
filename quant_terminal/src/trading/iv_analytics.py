"""IV analytics — term structure, volatility smile, realised vs implied vol.

Realised vol uses the Yang-Zhang estimator (Yang & Zhang 2000): combines
overnight + open-to-close variance and the "drift-free" Rogers-Satchell
component. Stable when intraday and overnight regimes differ.
"""
from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd

from src.common.schemas import OptionContract, OptionRight
from src.utils.logging import get_logger

log = get_logger(__name__)


# ---------------------------------------------------------------------------
# IV term structure — ATM IV per expiry
# ---------------------------------------------------------------------------
def iv_term_structure(contracts: list[OptionContract], spot: float) -> pd.DataFrame:
    """For each expiry, return the IV of the closest-to-ATM call and put.

    Output columns: expiry, dte_days, atm_call_iv, atm_put_iv, atm_iv_avg.
    """
    if not contracts or spot <= 0:
        return pd.DataFrame()
    rows = []
    today = date.today()
    for exp in sorted({c.expiry for c in contracts}):
        same = [c for c in contracts if c.expiry == exp and c.iv is not None]
        calls = [c for c in same if c.right == OptionRight.CALL]
        puts = [c for c in same if c.right == OptionRight.PUT]
        if not calls and not puts:
            continue
        atm_c = min(calls, key=lambda c: abs(c.strike - spot)) if calls else None
        atm_p = min(puts, key=lambda c: abs(c.strike - spot)) if puts else None
        c_iv = float(atm_c.iv) if atm_c else None
        p_iv = float(atm_p.iv) if atm_p else None
        avg = np.nanmean([v for v in (c_iv, p_iv) if v is not None]) if (c_iv or p_iv) else None
        rows.append({
            "expiry": exp,
            "dte_days": (exp - today).days,
            "atm_call_iv": c_iv,
            "atm_put_iv": p_iv,
            "atm_iv_avg": float(avg) if avg is not None else None,
        })
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Volatility smile — IV as a function of strike for a single expiry
# ---------------------------------------------------------------------------
def vol_smile(contracts: list[OptionContract], expiry: date, spot: float) -> pd.DataFrame:
    """All quoted IVs at a single expiry, separated by call/put.

    Output columns: strike, moneyness (= strike/spot - 1), call_iv, put_iv.
    """
    pool = [c for c in contracts if c.expiry == expiry and c.iv is not None]
    if not pool or spot <= 0:
        return pd.DataFrame()
    by_strike: dict[float, dict] = {}
    for c in pool:
        bucket = by_strike.setdefault(float(c.strike), {"strike": float(c.strike)})
        if c.right == OptionRight.CALL:
            bucket["call_iv"] = float(c.iv)
        else:
            bucket["put_iv"] = float(c.iv)
    rows = list(by_strike.values())
    for r in rows:
        r["moneyness"] = r["strike"] / spot - 1.0
    return pd.DataFrame(rows).sort_values("strike").reset_index(drop=True)


# ---------------------------------------------------------------------------
# Realised vol — Yang-Zhang estimator
# ---------------------------------------------------------------------------
def yang_zhang_rv(ohlc: pd.DataFrame, window: int = 20) -> pd.Series:
    """Annualised Yang-Zhang realised volatility on a rolling window.

    `ohlc` must have columns ``open, high, low, close``. The series is
    indexed by date and assumes 252 trading days per year.
    """
    needed = {"open", "high", "low", "close"}
    if not needed.issubset(ohlc.columns):
        raise ValueError(f"ohlc must contain {needed}; got {list(ohlc.columns)}")
    df = ohlc.copy()
    # Overnight log-return (yesterday's close to today's open)
    df["log_co"] = np.log(df["open"] / df["close"].shift(1))
    df["log_oc"] = np.log(df["close"] / df["open"])
    # Rogers-Satchell drift-free intraday component
    rs = (
        np.log(df["high"] / df["close"]) * np.log(df["high"] / df["open"])
        + np.log(df["low"] / df["close"]) * np.log(df["low"] / df["open"])
    )
    n = window
    co_var = df["log_co"].rolling(n).var(ddof=1)
    oc_var = df["log_oc"].rolling(n).var(ddof=1)
    rs_mean = rs.rolling(n).mean()
    k = 0.34 / (1.34 + (n + 1) / (n - 1))
    yz_var = co_var + k * oc_var + (1 - k) * rs_mean
    yz_var = yz_var.clip(lower=0)
    annualised = np.sqrt(yz_var * 252)
    annualised.name = f"rv_{window}d_yz"
    return annualised


def realised_vs_implied(
    close_or_ohlc: pd.DataFrame | pd.Series,
    atm_iv_now: float,
    *,
    window: int = 20,
) -> dict[str, float]:
    """Compare last-bar Yang-Zhang RV to the current ATM IV.

    If a close series is passed, falls back to a close-only Parkinson-like
    estimate (less accurate but better than nothing).
    """
    if isinstance(close_or_ohlc, pd.DataFrame):
        rv_series = yang_zhang_rv(close_or_ohlc, window=window)
    else:
        # Simple log-return std as a fallback estimator
        log_ret = np.log(close_or_ohlc / close_or_ohlc.shift(1))
        rv_series = log_ret.rolling(window).std() * np.sqrt(252)
    rv_series = rv_series.dropna()
    if rv_series.empty:
        return {"rv": 0.0, "iv": float(atm_iv_now or 0.0),
                "rv_minus_iv": 0.0, "iv_minus_rv": 0.0, "premium_pct": 0.0}
    rv_now = float(rv_series.iloc[-1])
    iv = float(atm_iv_now or 0.0)
    premium = (iv - rv_now) / rv_now if rv_now > 0 else 0.0
    return {
        "rv": rv_now,
        "iv": iv,
        "rv_minus_iv": rv_now - iv,
        "iv_minus_rv": iv - rv_now,
        "premium_pct": premium,
    }


def rv_iv_history(
    ohlc: pd.DataFrame,
    iv_atm_series: pd.Series,
    *,
    window: int = 20,
) -> pd.DataFrame:
    """Wide DataFrame indexed by date with columns rv, iv, premium."""
    if isinstance(ohlc, pd.DataFrame) and "close" in ohlc.columns:
        rv = yang_zhang_rv(ohlc, window=window)
    else:
        return pd.DataFrame()
    iv = pd.to_numeric(iv_atm_series, errors="coerce")
    common = rv.dropna().index.intersection(iv.dropna().index)
    if len(common) == 0:
        return pd.DataFrame()
    out = pd.DataFrame({
        "rv": rv.loc[common],
        "iv": iv.loc[common],
    })
    out["premium"] = (out["iv"] - out["rv"]) / out["rv"].replace(0, np.nan)
    return out
