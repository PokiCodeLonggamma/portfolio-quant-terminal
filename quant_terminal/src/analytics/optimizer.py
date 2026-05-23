"""Simple rebalancing helper aligned on `config/risk_limits.yaml`.

Not a full Markowitz optimiser — that's not the spirit of the report.
This module flags rule violations and proposes target weights from a
core/satellite template.
"""
from __future__ import annotations

import pandas as pd

from src.portfolio.holdings import Portfolio
from src.utils.config import get_config


def check_limits(portfolio: Portfolio) -> pd.DataFrame:
    """Return a tidy DataFrame of rule violations vs `config/risk_limits.yaml`."""
    cfg = get_config()
    limits = cfg.risk_limits
    w = portfolio.weights
    violations: list[dict[str, str | float]] = []

    max_single = float(limits.get("position", {}).get("max_single_position_pct", 0.12))
    for k, val in w.items():
        if val > max_single:
            violations.append({
                "rule": "max_single_position_pct",
                "ticker": k,
                "value": float(val),
                "limit": max_single,
                "severity": "high",
            })

    etp_max_individual = float(limits.get("leveraged_etps", {}).get("max_individual_pct", 0.05))
    etp_max_aggregate = float(limits.get("leveraged_etps", {}).get("max_aggregate_pct", 0.08))
    leveraged_mask = portfolio.holdings["asset_class"] == "etp_leveraged"
    leveraged_keys = portfolio.holdings.loc[leveraged_mask, "universe_key"].unique().tolist()
    for k in leveraged_keys:
        if w.get(k, 0.0) > etp_max_individual:
            violations.append({
                "rule": "etp_3x_max_individual",
                "ticker": k,
                "value": float(w.get(k, 0.0)),
                "limit": etp_max_individual,
                "severity": "high",
            })
    agg = float(w.reindex(leveraged_keys).sum()) if leveraged_keys else 0.0
    if agg > etp_max_aggregate:
        violations.append({
            "rule": "etp_3x_max_aggregate",
            "ticker": "<all 3x ETPs>",
            "value": agg,
            "limit": etp_max_aggregate,
            "severity": "high",
        })

    max_per_theme = float(limits.get("themes", {}).get("max_per_theme_pct", 0.35))
    by_theme = portfolio.by_theme() / portfolio.total_value_eur if portfolio.total_value_eur else portfolio.by_theme()
    for theme, val in by_theme.items():
        if val > max_per_theme:
            violations.append({
                "rule": "max_per_theme_pct",
                "ticker": str(theme),
                "value": float(val),
                "limit": max_per_theme,
                "severity": "medium",
            })

    return pd.DataFrame(violations).sort_values(["severity", "value"], ascending=[True, False]) if violations else pd.DataFrame(
        columns=["rule", "ticker", "value", "limit", "severity"]
    )
