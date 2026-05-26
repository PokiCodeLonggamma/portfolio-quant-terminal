"""Walk-forward parameter sweep.

For each parameter combination of a base rule factory:
  1. Build the rule with those params.
  2. Step through the price history in expanding folds:
       fold k uses bars [k*step : k*step + train_window + test_window)
       train = first ``train_window_days`` bars (NOT used to "fit" -- the
       rules are non-parametric in the optimisation sense, but the train
       window is required to warm up trailing peaks / momentum windows).
       test  = next ``test_window_days`` bars -- this is the OOS slice that
       feeds the Sharpe.
  3. Run :func:`simulate` on the train+test slice with the rule, take the
     ruled-NAV OOS Sharpe, record it.

Output: a tidy DataFrame with one row per (fold, params).
"""
from __future__ import annotations

from collections.abc import Callable, Iterable
from itertools import product
from typing import Any

import numpy as np
import pandas as pd

from src.backtest.engine import simulate
from src.backtest.rules import Rule
from src.portfolio.risk import risk_metrics
from src.utils.logging import get_logger

log = get_logger(__name__)


def _iter_param_grid(grid: dict[str, Iterable[Any]]) -> list[dict[str, Any]]:
    """Cartesian product of a {param: [values, ...]} dict."""
    if not grid:
        return [{}]
    keys = list(grid.keys())
    value_lists = [list(grid[k]) for k in keys]
    combos: list[dict[str, Any]] = []
    for vals in product(*value_lists):
        combos.append(dict(zip(keys, vals)))
    return combos


def _equal_weight(columns: list[str]) -> pd.Series:
    if not columns:
        return pd.Series(dtype=float)
    return pd.Series(1.0 / len(columns), index=columns)


def walk_forward(
    prices_eur: pd.DataFrame,
    base_rule_factory: Callable[..., Rule],
    param_grid: dict[str, Iterable[Any]],
    train_window_days: int = 252,
    test_window_days: int = 63,
    initial_weights: pd.Series | None = None,
    step_days: int | None = None,
    initial_eur: float = 10_000.0,
    rebalance_freq: str = "M",
) -> pd.DataFrame:
    """Return a tidy DataFrame of OOS results per (fold, param-set).

    Parameters
    ----------
    prices_eur : pd.DataFrame
        EUR price panel.
    base_rule_factory : callable
        e.g. ``lambda max_pct: MaxSinglePositionRule(max_pct=max_pct)``.
        Receives kwargs from each grid combination.
    param_grid : dict
        ``{"param_name": [v1, v2, ...]}``.
    train_window_days : int
        Warm-up bars per fold (rules with trailing windows need history).
    test_window_days : int
        OOS Sharpe is computed on this window.
    initial_weights : pd.Series | None
        If ``None``, equal-weight across all columns.
    step_days : int | None
        Roll step between folds; defaults to ``test_window_days``.
    initial_eur : float
    rebalance_freq : str

    Returns
    -------
    pd.DataFrame
        Columns: ``fold``, ``train_start``, ``test_start``, ``test_end``,
        ``oos_sharpe``, ``oos_max_dd``, ``oos_total_return``,
        ``baseline_oos_sharpe``, plus one column per grid param.
    """
    if prices_eur is None or prices_eur.empty:
        return pd.DataFrame()
    prices = prices_eur.sort_index().ffill().dropna(how="all")
    n = len(prices.index)
    if n < (train_window_days + test_window_days):
        log.warning(
            "walk_forward: not enough history (have %d, need %d) -- returning empty",
            n,
            train_window_days + test_window_days,
        )
        return pd.DataFrame()

    step = int(step_days or test_window_days)
    cols = list(prices.columns)
    w0 = (
        initial_weights.reindex(cols).fillna(0.0)
        if initial_weights is not None
        else _equal_weight(cols)
    )

    combos = _iter_param_grid(param_grid)
    fold_id = 0
    rows: list[dict[str, Any]] = []

    start_i = 0
    while start_i + train_window_days + test_window_days <= n:
        train_start = prices.index[start_i]
        test_start_idx = start_i + train_window_days
        test_end_idx = test_start_idx + test_window_days - 1
        test_start = prices.index[test_start_idx]
        test_end = prices.index[test_end_idx]

        fold_prices = prices.iloc[start_i : test_end_idx + 1]

        # Baseline OOS Sharpe (no rules) — same warm-up + test horizon.
        baseline_res = simulate(
            fold_prices,
            initial_weights=w0,
            rules=None,
            rebalance_freq=rebalance_freq,
            initial_eur=initial_eur,
        )
        baseline_oos = baseline_res.ruled_nav.loc[test_start:test_end]
        baseline_sharpe = (
            float(risk_metrics(baseline_oos.pct_change().dropna()).sharpe)
            if len(baseline_oos) > 2
            else 0.0
        )

        for params in combos:
            try:
                rule = base_rule_factory(**params)
            except Exception as exc:
                log.warning("rule factory failed for %s: %s", params, exc)
                continue

            res = simulate(
                fold_prices,
                initial_weights=w0,
                rules=[rule],
                rebalance_freq=rebalance_freq,
                initial_eur=initial_eur,
            )
            oos = res.ruled_nav.loc[test_start:test_end]
            if len(oos) < 3:
                continue
            oos_ret = oos.pct_change().dropna()
            metrics = risk_metrics(oos_ret)
            total_ret = (
                float(oos.iloc[-1] / oos.iloc[0] - 1.0)
                if oos.iloc[0] > 0
                else float("nan")
            )

            row = {
                "fold": fold_id,
                "train_start": train_start,
                "test_start": test_start,
                "test_end": test_end,
                "oos_sharpe": float(metrics.sharpe),
                "oos_max_dd": float(metrics.max_drawdown),
                "oos_total_return": total_ret,
                "baseline_oos_sharpe": baseline_sharpe,
                **params,
            }
            rows.append(row)

        fold_id += 1
        start_i += step

    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    return df


def best_params(wf: pd.DataFrame, metric: str = "oos_sharpe") -> dict[str, Any]:
    """Aggregate the walk-forward output across folds and return the
    parameter combination with the highest mean of ``metric``."""
    if wf is None or wf.empty:
        return {}
    param_cols = [
        c
        for c in wf.columns
        if c
        not in {
            "fold",
            "train_start",
            "test_start",
            "test_end",
            "oos_sharpe",
            "oos_max_dd",
            "oos_total_return",
            "baseline_oos_sharpe",
        }
    ]
    if not param_cols:
        return {}
    means = wf.groupby(param_cols)[metric].mean().sort_values(ascending=False)
    if means.empty:
        return {}
    top = means.index[0]
    if not isinstance(top, tuple):
        top = (top,)
    return dict(zip(param_cols, top))


def pivot_heatmap(
    wf: pd.DataFrame,
    rows_param: str,
    cols_param: str,
    metric: str = "oos_sharpe",
    aggfunc: str = "mean",
) -> pd.DataFrame:
    """Pivot the walk-forward table to a 2D heatmap matrix."""
    if wf is None or wf.empty:
        return pd.DataFrame()
    if rows_param not in wf.columns or cols_param not in wf.columns:
        return pd.DataFrame()
    pivot = wf.pivot_table(
        index=rows_param, columns=cols_param, values=metric, aggfunc=aggfunc
    )
    return pivot.replace([np.inf, -np.inf], np.nan)
