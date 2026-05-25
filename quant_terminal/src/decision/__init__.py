"""Decision-support cluster (modules E + H + I).

Glues together SEC dilution/runway (Cluster 1), liquidity (Cluster 2),
catalyst proximity (Cluster 4) and option-chain hedges (Cluster 5) into:

* a 4-axis conviction score per position (`conviction.py`)
* sizing helpers: Kelly-haircut, VaR-contribution trim, risk-parity preview
  (`conviction.py`, `var_contribution_sizing.py`, `risk_parity_preview.py`)
* per-ticker thesis journal persisted as YAML (`journal_store.py`)
* re-rating progress score (`rerating_score.py`)
* protective-collar hedge cost quote + linear-futures fallback (`hedge_cost.py`)

All public API is re-exported here so callers can do
`from src.decision import compute_position_score, read_journal, ...`.
"""
from __future__ import annotations

from src.decision.conviction import (
    compute_position_score,
    score_portfolio,
    suggested_weight,
)
from src.decision.hedge_cost import (
    compute_collar,
    linear_futures_alternatives,
    portfolio_hedge_panel,
)
from src.decision.journal_store import (
    journal_dir,
    list_journals,
    read_journal,
    write_journal,
)
from src.decision.rerating_score import compute_rerating_score
from src.decision.risk_parity_preview import risk_parity_weights
from src.decision.var_contribution_sizing import var_contribution_sizing

__all__ = [
    "compute_collar",
    "compute_position_score",
    "compute_rerating_score",
    "journal_dir",
    "linear_futures_alternatives",
    "list_journals",
    "portfolio_hedge_panel",
    "read_journal",
    "risk_parity_weights",
    "score_portfolio",
    "suggested_weight",
    "var_contribution_sizing",
    "write_journal",
]
