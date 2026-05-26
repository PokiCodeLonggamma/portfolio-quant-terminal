"""Rolling correlations + regime-change alerts.

Two flavours:
    * ``rolling_corr_matrix`` — for a fixed window, returns the latest
      (date, ticker, ticker) cross-correlation matrix; vectorised over the
      whole panel.
    * ``rolling_corr_vs_benchmarks`` — long-format multi-index
      (date, ticker) -> benchmarks columns, useful for plotting one
      asset-vs-benchmark line over time.
    * ``corr_regime_changes`` — alerts when corr(ticker, benchmark) shifted
      by more than ``threshold`` in absolute value between two windows
      (``window`` days ago vs now).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from src.utils.logging import get_logger

log = get_logger(__name__)

NAMESPACE = "corr"
DEFAULT_WINDOW = 60
DEFAULT_THRESHOLD = 0.30


# ---------------------------------------------------------------------------
# Matrix view
# ---------------------------------------------------------------------------
def rolling_corr_matrix(
    returns_df: pd.DataFrame,
    window_days: int = DEFAULT_WINDOW,
) -> pd.DataFrame:
    """Latest rolling correlation matrix for ``returns_df`` (last ``window_days``).

    Returns a square DataFrame indexed and columned by the input's columns.
    Returns an empty frame if there aren't enough rows.
    """
    if returns_df is None or returns_df.empty:
        return pd.DataFrame()
    df = returns_df.dropna(how="all").copy()
    if len(df) < window_days:
        log.debug("rolling_corr_matrix: only %d rows < window %d", len(df), window_days)
        return pd.DataFrame()
    tail = df.tail(window_days)
    return tail.corr().replace([np.inf, -np.inf], np.nan).fillna(0.0)


# ---------------------------------------------------------------------------
# Long-format vs-benchmarks view
# ---------------------------------------------------------------------------
def rolling_corr_vs_benchmarks(
    portfolio_returns: pd.DataFrame,        # date x ticker
    benchmark_returns: pd.DataFrame,        # date x bench
    *,
    window: int = DEFAULT_WINDOW,
) -> pd.DataFrame:
    """Rolling correlations per ticker vs each benchmark, long form.

    Returns a frame with a (date, ticker) multi-index and benchmark columns.
    """
    if portfolio_returns is None or portfolio_returns.empty:
        return pd.DataFrame()
    if benchmark_returns is None or benchmark_returns.empty:
        return pd.DataFrame()

    aligned = portfolio_returns.join(benchmark_returns, how="inner")
    if len(aligned) < window:
        return pd.DataFrame()

    out_blocks: list[pd.DataFrame] = []
    bench_cols = list(benchmark_returns.columns)
    for ticker in portfolio_returns.columns:
        if ticker not in aligned.columns:
            continue
        per_bench: dict[str, pd.Series] = {}
        x = aligned[ticker]
        for b in bench_cols:
            y = aligned[b]
            cov = x.rolling(window).cov(y)
            vx = x.rolling(window).var()
            vy = y.rolling(window).var()
            denom = np.sqrt(vx * vy)
            corr = (cov / denom.replace(0, np.nan))
            per_bench[b] = corr
        block = pd.DataFrame(per_bench).dropna(how="all")
        if block.empty:
            continue
        block.index = pd.MultiIndex.from_product([block.index, [ticker]], names=["date", "ticker"])
        out_blocks.append(block)

    if not out_blocks:
        return pd.DataFrame()
    return pd.concat(out_blocks).sort_index()


# ---------------------------------------------------------------------------
# Regime-change alerts
# ---------------------------------------------------------------------------
def corr_regime_changes(
    returns_df: pd.DataFrame,
    *,
    window: int = DEFAULT_WINDOW,
    threshold: float = DEFAULT_THRESHOLD,
    benchmarks: list[str] | None = None,
) -> pd.DataFrame:
    """Alert table: tickers whose correlation regime shifted significantly.

    For every column pair (ticker, benchmark) we compare:
        * ``corr_now``  — corr over the most recent ``window`` rows
        * ``corr_then`` — corr over the prior ``window`` rows
        * ``delta``     — corr_now - corr_then

    Rows are returned only when ``abs(delta) >= threshold``.

    If ``benchmarks`` is None, every column is compared against every other.
    Otherwise only ticker(non-benchmark) -> benchmark pairs are emitted.
    """
    if returns_df is None or returns_df.empty:
        return pd.DataFrame(columns=["ticker", "benchmark", "corr_now", "corr_then", "delta", "asof"])

    df = returns_df.dropna(how="all").copy()
    if len(df) < 2 * window:
        return pd.DataFrame(columns=["ticker", "benchmark", "corr_now", "corr_then", "delta", "asof"])

    recent = df.tail(window)
    prior = df.iloc[-2 * window:-window]
    asof = df.index[-1]

    corr_now = recent.corr()
    corr_then = prior.corr()

    cols = list(df.columns)
    if benchmarks is None:
        pairs = [(t, b) for t in cols for b in cols if t != b and t < b]
    else:
        bench_in = [b for b in benchmarks if b in cols]
        tickers = [c for c in cols if c not in set(bench_in)]
        pairs = [(t, b) for t in tickers for b in bench_in]

    rows: list[dict] = []
    for t, b in pairs:
        try:
            cn = float(corr_now.at[t, b])
            ct = float(corr_then.at[t, b])
        except (KeyError, ValueError):
            continue
        if not (np.isfinite(cn) and np.isfinite(ct)):
            continue
        delta = cn - ct
        if abs(delta) >= threshold:
            rows.append({
                "ticker": t,
                "benchmark": b,
                "corr_now": round(cn, 3),
                "corr_then": round(ct, 3),
                "delta": round(delta, 3),
                "asof": pd.Timestamp(asof).date(),
            })

    out = pd.DataFrame(rows, columns=["ticker", "benchmark", "corr_now", "corr_then", "delta", "asof"])
    if not out.empty:
        out = out.reindex(out["delta"].abs().sort_values(ascending=False).index).reset_index(drop=True)
    return out


# Backward-compat name expected by the architect plan
correlation_change_alerts = corr_regime_changes
