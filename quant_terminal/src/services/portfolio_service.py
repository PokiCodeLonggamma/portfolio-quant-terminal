"""Portfolio service — exposes the loaded Portfolio as Pydantic DTOs.

Wraps :class:`src.portfolio.holdings.Portfolio` for the FastAPI surface.
The portfolio is loaded from a DataFrame at construction; an optional
``portfolio_fetch_fn`` can hydrate it on demand (Phase 2: in-memory; Phase 3:
Redis-cached after DEGIRO upload).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Callable

import pandas as pd

from src.portfolio.holdings import Portfolio
from src.services.schemas import Holding, PortfolioSummary


# ---------------------------------------------------------------------------
# Default loader: empty portfolio (no DEGIRO upload yet)
# ---------------------------------------------------------------------------
def _empty_portfolio() -> Portfolio | None:
    """Return None — the FastAPI handler maps this to a 404."""
    return None


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------
@dataclass
class PortfolioService:
    """Read-only orchestration around a Portfolio instance.

    Phase 2 supports a single-user portfolio. Multi-user keying comes
    later (auth = single-user JWT per the architecture decisions).
    """
    portfolio_fetch_fn: Callable[[], Portfolio | None] = _empty_portfolio

    # ------------------------------------------------------------------
    # summary
    # ------------------------------------------------------------------
    def get_summary(self) -> PortfolioSummary | None:
        """Top-level NAV + holdings list."""
        p = self.portfolio_fetch_fn()
        if p is None or p.holdings is None or p.holdings.empty:
            return None
        holdings: list[Holding] = []
        for _, row in p.holdings.iterrows():
            holdings.append(_row_to_holding(row))
        return PortfolioSummary(
            nav_eur=float(p.total_value_eur),
            n_positions=len(holdings),
            holdings=holdings,
            asof=datetime.utcnow(),
        )

    # ------------------------------------------------------------------
    # availability
    # ------------------------------------------------------------------
    def portfolio_available(self) -> bool:
        p = self.portfolio_fetch_fn()
        return p is not None and not p.holdings.empty


def _row_to_holding(row: pd.Series) -> Holding:
    """Map a Portfolio row to a Holding DTO. Resilient to missing columns."""
    return Holding(
        ticker=str(row.get("universe_key") or row.get("symbol") or "UNKNOWN"),
        isin=row.get("isin") if "isin" in row else None,
        name=row.get("name"),
        quantity=float(row.get("quantity", 0) or 0),
        price_eur=float(row["price_eur"]) if "price_eur" in row and pd.notna(row["price_eur"]) else None,
        market_value_eur=float(row.get("value_eur", 0) or 0),
        currency=str(row.get("currency") or "EUR"),
        theme=row.get("theme"),
        region=row.get("region"),
    )
