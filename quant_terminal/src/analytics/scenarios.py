"""Named macro stress scenarios.

Each scenario specifies a set of asset shocks (in percent). Designed to map
naturally to the portfolio described in `rapport_portefeuille_quant_terminal.md`
section 6.
"""
from __future__ import annotations

from typing import Iterable

import pandas as pd

# Shocks are expressed as decimal daily/cumulative price moves on the universe_key.
# Tickers not listed in a scenario implicitly take a 0% move (beta-zero stress).
DEFAULT_SCENARIOS: dict[str, dict[str, float]] = {
    "Inflation_Energy_Spike": {
        "3OIL.L": +0.90,    # WTI 3x leveraged on +30% WTI move
        "CCJ": +0.15,
        "NTR": +0.10,
        "IGLN.L": +0.08,
        "PHAG.L": +0.08,
        "3DES.L": +0.30,    # DAX 3x short benefits from energy-driven DAX selloff
    },
    "Disinflation_Recession": {
        "3OIL.L": -0.60,
        "CCJ": -0.20,
        "NTR": -0.15,
        "ALB": -0.20,
        "ASTS": -0.40,
        "QS": -0.40,
        "RDW": -0.35,
        "AAOI": -0.35,
        "ONDS": -0.45,
        "PNG.V": -0.40,
        "AII.TO": -0.30,
        "GOOG": -0.10,
        "IGLN.L": +0.05,
    },
    "Real_Rates_Up_200bps": {
        "ASTS": -0.45,
        "QS": -0.50,
        "RDW": -0.40,
        "AAOI": -0.40,
        "ONDS": -0.55,
        "PNG.V": -0.45,
        "GOOG": -0.12,
        "IGLN.L": -0.10,
        "3OIL.L": -0.20,
    },
    "Range_Bound_Volatile_3M": {
        "3OIL.L": -0.30,    # path-dependency / vol decay
        "3DES.L": -0.25,
    },
    "Geopolitical_Defense_Boom": {
        "BWXT": +0.25,
        "RDW": +0.30,
        "PNG.V": +0.30,
        "CCJ": +0.15,
        "ENGI.PA": +0.05,
    },
}


def list_scenarios() -> list[str]:
    return list(DEFAULT_SCENARIOS.keys())


def get_scenario(name: str) -> dict[str, float]:
    if name not in DEFAULT_SCENARIOS:
        raise KeyError(f"unknown scenario: {name}; available: {list_scenarios()}")
    return dict(DEFAULT_SCENARIOS[name])


def apply_all(weights: pd.Series, scenarios: Iterable[str] | None = None) -> pd.DataFrame:
    """Compute portfolio impact for each scenario.

    Returns DataFrame with columns: scenario, portfolio_pct, worst_position, worst_pct.
    """
    if scenarios is None:
        scenarios = list_scenarios()
    rows = []
    for name in scenarios:
        sc = get_scenario(name)
        per_pos = pd.Series(0.0, index=weights.index)
        for k, v in sc.items():
            if k in per_pos.index:
                per_pos[k] = v
        contrib = per_pos * weights
        if contrib.empty:
            continue
        rows.append({
            "scenario": name,
            "portfolio_pct": float(contrib.sum()),
            "worst_position": str(contrib.idxmin()),
            "worst_pct": float(contrib.min()),
        })
    return pd.DataFrame(rows).sort_values("portfolio_pct")
