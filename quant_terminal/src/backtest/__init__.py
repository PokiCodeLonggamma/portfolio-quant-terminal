"""Backtest cluster — historical replay of user-defined risk rules.

Public surface:
  - rules:        Rule Protocol + concrete rule classes
  - engine:       simulate() returns NAV / cash / trigger log
  - metrics_diff: comparison_table(baseline, ruled) -> KPIs
  - optimizer:    walk_forward(...) — OOS Sharpe across parameter grids
  - dashboards:   Streamlit render_* helpers

All cash and NAV figures are EUR-denominated. Sharpe and drawdown are reused
from :mod:`src.portfolio.risk.risk_metrics` to keep one canonical implementation.
"""
from __future__ import annotations

from src.backtest.engine import simulate
from src.backtest.metrics_diff import comparison_table
from src.backtest.optimizer import walk_forward
from src.backtest.rules import (
    MaxDrawdownTriggerRule,
    MaxSinglePositionRule,
    MaxThemeCapRule,
    MomentumEntryRule,
    Rule,
    StopLossRule,
)

__all__ = [
    "Rule",
    "MaxSinglePositionRule",
    "MaxDrawdownTriggerRule",
    "MaxThemeCapRule",
    "StopLossRule",
    "MomentumEntryRule",
    "simulate",
    "comparison_table",
    "walk_forward",
]
