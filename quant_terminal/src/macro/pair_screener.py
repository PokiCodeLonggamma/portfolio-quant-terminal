"""Pair-trade screener — Engle-Granger cointegration + momentum gap.

Inputs:
    * a wide price panel (date x ticker)
    * (optionally) a candidate-pool list — defaults to all columns

Outputs:
    * a ranked DataFrame of pair candidates
    * a typed list[PairCandidate] via ``screen_pairs``

A pair (A, B) is considered when:
    * both series have at least ``MIN_SAMPLE`` non-null rows in the window
    * Engle-Granger p-value is below ``pvalue_threshold``
    * we rank by a composite: p-value (lower better) + |momentum_gap| (larger
      better as a divergence signal)

The momentum gap is 12M-1M of A minus 12M-1M of B (intuition: long the laggard,
short the leader when they are cointegrated).
"""
from __future__ import annotations

from itertools import combinations

import numpy as np
import pandas as pd

from src.common.schemas import PairCandidate
from src.utils.cache import read as cache_read, write as cache_write
from src.utils.logging import get_logger

log = get_logger(__name__)

NAMESPACE = "pair"
MIN_SAMPLE = 60
DEFAULT_LOOKBACK = 252
DEFAULT_PVALUE = 0.05


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _momentum_12_1(price: pd.Series) -> float:
    """12M minus 1M return on a daily price series."""
    s = price.dropna()
    if len(s) < 252:
        return float("nan")
    try:
        twelve = s.iloc[-1] / s.iloc[-252] - 1.0
        one = s.iloc[-1] / s.iloc[-21] - 1.0
        return float(twelve - one)
    except (ZeroDivisionError, IndexError):
        return float("nan")


def _engle_granger_pvalue(y: pd.Series, x: pd.Series) -> float:
    """statsmodels ``coint`` p-value, NaN on failure."""
    try:
        from statsmodels.tsa.stattools import coint
    except ImportError:
        log.warning("statsmodels not installed; cannot run cointegration")
        return float("nan")
    aligned = pd.concat([y, x], axis=1).dropna()
    if len(aligned) < MIN_SAMPLE:
        return float("nan")
    try:
        _t, pvalue, _crit = coint(aligned.iloc[:, 0].values, aligned.iloc[:, 1].values)
        return float(pvalue)
    except Exception as exc:
        log.debug("coint failed: %s", exc)
        return float("nan")


def _spread_zscore_and_halflife(y: pd.Series, x: pd.Series) -> tuple[float, float]:
    """OLS spread, last z-score and OU half-life (days)."""
    aligned = pd.concat([y, x], axis=1).dropna()
    if len(aligned) < MIN_SAMPLE:
        return float("nan"), float("nan")
    yv = aligned.iloc[:, 0].values.astype(float)
    xv = aligned.iloc[:, 1].values.astype(float)
    # Hedge ratio via OLS without an intercept (simple, robust)
    denom = float((xv * xv).sum())
    if denom <= 0:
        return float("nan"), float("nan")
    beta = float((xv * yv).sum() / denom)
    spread = yv - beta * xv
    mu = float(np.mean(spread))
    sigma = float(np.std(spread, ddof=1))
    z = (spread[-1] - mu) / sigma if sigma > 0 else float("nan")

    # Half-life via AR(1): ds_t = lam * (s_{t-1} - mu) + eps; halflife = -ln(2)/lam
    try:
        s_lag = spread[:-1] - mu
        ds = np.diff(spread)
        var_lag = float((s_lag * s_lag).sum())
        if var_lag <= 0:
            halflife = float("nan")
        else:
            lam = float((s_lag * ds).sum() / var_lag)
            halflife = float(-np.log(2.0) / lam) if lam < 0 else float("nan")
    except Exception:
        halflife = float("nan")
    return z, halflife


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def screen_pairs_df(
    prices: pd.DataFrame,
    candidate_pool: list[str] | None = None,
    *,
    lookback_days: int = DEFAULT_LOOKBACK,
    pvalue_threshold: float = DEFAULT_PVALUE,
    max_pairs: int = 50,
) -> pd.DataFrame:
    """Return a ranked DataFrame of pair candidates.

    Columns: long_ticker, short_ticker, coint_pvalue, halflife_days, spread_z,
             momentum_gap, rationale, rank_score
    """
    if prices is None or prices.empty:
        return pd.DataFrame(columns=[
            "long_ticker", "short_ticker", "coint_pvalue", "halflife_days",
            "spread_z", "momentum_gap", "rationale", "rank_score",
        ])

    pool = candidate_pool or list(prices.columns)
    pool = [c for c in pool if c in prices.columns]
    if len(pool) < 2:
        return pd.DataFrame()

    window = prices[pool].tail(lookback_days).copy()

    rows: list[dict] = []
    for a, b in combinations(pool, 2):
        ya = window[a]
        yb = window[b]
        if ya.dropna().empty or yb.dropna().empty:
            continue
        pvalue = _engle_granger_pvalue(ya, yb)
        if not np.isfinite(pvalue) or pvalue > pvalue_threshold:
            continue
        z, halflife = _spread_zscore_and_halflife(ya, yb)
        mom_a = _momentum_12_1(prices[a])
        mom_b = _momentum_12_1(prices[b])
        momentum_gap = (mom_a - mom_b) if np.isfinite(mom_a) and np.isfinite(mom_b) else float("nan")

        # Convention: short the leader, long the laggard
        if np.isfinite(momentum_gap) and momentum_gap >= 0:
            long_t, short_t = b, a  # b lagged, a led
            mg_signed = -momentum_gap
        else:
            long_t, short_t = a, b
            mg_signed = momentum_gap if np.isfinite(momentum_gap) else 0.0

        rationale_parts = [
            f"coint p={pvalue:.3f}",
            f"halflife={halflife:.0f}d" if np.isfinite(halflife) else "halflife=n/a",
            f"z={z:+.2f}" if np.isfinite(z) else "z=n/a",
            f"12m-1m gap={momentum_gap:+.2%}" if np.isfinite(momentum_gap) else "",
        ]
        rationale = " | ".join(p for p in rationale_parts if p)

        rank_score = pvalue - 0.5 * (abs(momentum_gap) if np.isfinite(momentum_gap) else 0.0)

        rows.append({
            "long_ticker": long_t,
            "short_ticker": short_t,
            "coint_pvalue": round(pvalue, 4),
            "halflife_days": round(halflife, 1) if np.isfinite(halflife) else float("nan"),
            "spread_z": round(z, 3) if np.isfinite(z) else float("nan"),
            "momentum_gap": round(mg_signed, 4) if np.isfinite(mg_signed) else float("nan"),
            "rationale": rationale,
            "rank_score": round(rank_score, 4),
        })

    out = pd.DataFrame(rows)
    if out.empty:
        return out
    out = out.sort_values(["rank_score", "coint_pvalue"], ascending=[True, True]).reset_index(drop=True)
    return out.head(max_pairs)


def screen_pairs(
    prices: pd.DataFrame,
    candidate_pool: list[str] | None = None,
    *,
    lookback_days: int = DEFAULT_LOOKBACK,
    pvalue_threshold: float = DEFAULT_PVALUE,
    max_pairs: int = 50,
) -> list[PairCandidate]:
    """Typed wrapper around ``screen_pairs_df``."""
    df = screen_pairs_df(
        prices,
        candidate_pool,
        lookback_days=lookback_days,
        pvalue_threshold=pvalue_threshold,
        max_pairs=max_pairs,
    )
    out: list[PairCandidate] = []
    for _, r in df.iterrows():
        out.append(PairCandidate(
            long_ticker=str(r["long_ticker"]),
            short_ticker=str(r["short_ticker"]),
            coint_pvalue=float(r["coint_pvalue"]),
            halflife_days=float(r["halflife_days"]) if pd.notna(r["halflife_days"]) else None,
            spread_z=float(r["spread_z"]) if pd.notna(r["spread_z"]) else None,
            momentum_gap=float(r["momentum_gap"]) if pd.notna(r["momentum_gap"]) else None,
            rationale=str(r["rationale"]),
        ))
    return out
