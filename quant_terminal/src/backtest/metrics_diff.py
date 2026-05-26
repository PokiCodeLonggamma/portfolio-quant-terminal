"""Comparison metrics between two NAV traces.

All metrics reuse :func:`src.portfolio.risk.risk_metrics` so the Sharpe /
drawdown definitions stay consistent with the rest of the terminal.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from src.portfolio.risk import RiskMetrics, risk_metrics


def _nav_to_returns(nav: pd.Series) -> pd.Series:
    s = pd.Series(nav, copy=True).astype(float).dropna()
    if len(s) < 2:
        return pd.Series(dtype=float)
    return s.pct_change().dropna()


def _safe_metrics(nav: pd.Series) -> RiskMetrics:
    ret = _nav_to_returns(nav)
    return risk_metrics(ret)


def comparison_table(
    baseline_nav: pd.Series,
    ruled_nav: pd.Series,
) -> pd.DataFrame:
    """Return a 2-column comparison + delta table.

    Rows
    ----
    - Sharpe (annualised)
    - Sortino
    - Annualised return
    - Annualised vol
    - Max drawdown
    - VaR 95% (daily)
    - CVaR 95% (daily)
    - Ending NAV (EUR)
    - Total return (%)

    Columns: ``baseline``, ``ruled``, ``delta``.
    """
    base = _safe_metrics(baseline_nav)
    ruled = _safe_metrics(ruled_nav)

    def _end(nav: pd.Series) -> float:
        s = pd.Series(nav).astype(float).dropna()
        return float(s.iloc[-1]) if not s.empty else float("nan")

    def _start(nav: pd.Series) -> float:
        s = pd.Series(nav).astype(float).dropna()
        return float(s.iloc[0]) if not s.empty else float("nan")

    base_end, ruled_end = _end(baseline_nav), _end(ruled_nav)
    base_start, ruled_start = _start(baseline_nav), _start(ruled_nav)

    base_total_ret = (base_end / base_start - 1.0) if base_start else float("nan")
    ruled_total_ret = (ruled_end / ruled_start - 1.0) if ruled_start else float("nan")

    rows = [
        ("Sharpe", base.sharpe, ruled.sharpe),
        ("Sortino", base.sortino, ruled.sortino),
        ("Ann. return", base.ann_return, ruled.ann_return),
        ("Ann. vol", base.ann_vol, ruled.ann_vol),
        ("Max drawdown", base.max_drawdown, ruled.max_drawdown),
        ("VaR 95% (daily)", base.var_95_daily, ruled.var_95_daily),
        ("CVaR 95% (daily)", base.cvar_95_daily, ruled.cvar_95_daily),
        ("Ending NAV (EUR)", base_end, ruled_end),
        ("Total return", base_total_ret, ruled_total_ret),
    ]
    df = pd.DataFrame(rows, columns=["metric", "baseline", "ruled"]).set_index("metric")
    df["delta"] = df["ruled"] - df["baseline"]
    return df


def sharpe_delta(baseline_nav: pd.Series, ruled_nav: pd.Series) -> float:
    """Convenience: Sharpe(ruled) - Sharpe(baseline)."""
    return float(_safe_metrics(ruled_nav).sharpe - _safe_metrics(baseline_nav).sharpe)


def equity_delta(baseline_nav: pd.Series, ruled_nav: pd.Series) -> pd.Series:
    """Return the time-series ``ruled_nav - baseline_nav`` aligned on the
    intersection index. NaNs from non-overlapping windows are dropped."""
    a, b = pd.Series(baseline_nav).astype(float), pd.Series(ruled_nav).astype(float)
    aligned = pd.concat([a.rename("baseline"), b.rename("ruled")], axis=1).dropna()
    if aligned.empty:
        return pd.Series(dtype=float)
    return (aligned["ruled"] - aligned["baseline"]).rename("delta_eur")


def drawdown_series(nav: pd.Series) -> pd.Series:
    """Compute drawdown as a fraction (≤ 0) from a NAV series."""
    s = pd.Series(nav).astype(float).dropna()
    if s.empty:
        return s
    peak = s.cummax()
    dd = s / peak - 1.0
    return dd.where(np.isfinite(dd), 0.0)
