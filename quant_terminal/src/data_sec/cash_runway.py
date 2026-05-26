"""Cash runway = cash / quarterly burn from XBRL.

`quarterly_burn` uses the TTM mean of `burn_qoq` (positive = cash being
consumed). Where free-cash-flow is *positive* across the trailing 4
quarters, the issuer is self-funding and runway is +inf — UI should special
case that.

EUR conversion uses `src.data.fx.convert_to_eur` so the rest of the
portfolio panel stays in EUR. We assume USD reporting (almost all SEC
filers); for non-USD ADRs you'd need to extend.
"""
from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd

from src.common.schemas import RunwayAssessment
from src.data_sec.forms_index import cik_for_ticker
from src.data_sec.xbrl_facts import quarterly_cash_and_burn
from src.utils.logging import get_logger

log = get_logger(__name__)


def _usd_to_eur(amount_usd: float) -> float:
    """Convert USD -> EUR. Falls back to identity if FX unavailable."""
    try:
        from src.data.fx import convert_to_eur

        return float(convert_to_eur(amount_usd, "USD"))
    except Exception as exc:
        log.debug("FX conversion failed (USD), falling back: %s", exc)
        return float(amount_usd)


def assess_runway(ticker: str) -> RunwayAssessment:
    """Return cash runway in quarters for ``ticker``.

    Confidence ladder:
      * high   — >=4 quarterly observations, positive burn
      * medium — 2-3 quarterly obs
      * low    — fewer than 2 quarters, OR burn <= 0 (issuer self-funding)
    """
    safe = RunwayAssessment(
        ticker=ticker.upper() if ticker else "",
        cash_eur=0.0,
        quarterly_burn_eur=0.0,
        runway_quarters=float("inf"),
        period_end=date.today(),
        confidence="low",
    )
    if not ticker:
        return safe
    cik = cik_for_ticker(ticker)
    if cik is None:
        return safe

    df = quarterly_cash_and_burn(ticker)
    if df.empty or df["cash_eq"].dropna().empty:
        return safe

    df = df.sort_values("period_end")
    last = df.iloc[-1]
    cash_usd = float(last["cash_eq"]) if pd.notna(last["cash_eq"]) else 0.0
    burns = df["burn_qoq"].dropna().tail(4)
    avg_burn_usd = float(burns.mean()) if not burns.empty else 0.0

    cash_eur = _usd_to_eur(cash_usd)
    burn_eur = _usd_to_eur(avg_burn_usd)

    if burn_eur <= 0:
        runway_q = float("inf")
        confidence: str = "low"                                         # issuer is FCF positive
    else:
        runway_q = cash_eur / burn_eur
        if len(burns) >= 4:
            confidence = "high"
        elif len(burns) >= 2:
            confidence = "medium"
        else:
            confidence = "low"

    period_end = last["period_end"]
    if isinstance(period_end, pd.Timestamp):
        period_end = period_end.date()
    elif not isinstance(period_end, date):
        period_end = date.today()

    return RunwayAssessment(
        ticker=ticker.upper(),
        cash_eur=cash_eur,
        quarterly_burn_eur=burn_eur,
        runway_quarters=runway_q,
        period_end=period_end,
        confidence=confidence,                                          # type: ignore[arg-type]
    )


_PANEL_COLS = ["ticker", "cash_eur", "quarterly_burn_eur", "runway_quarters", "period_end", "confidence"]


def portfolio_runway_panel(tickers: list[str]) -> pd.DataFrame:
    rows = []
    for t in tickers:
        a = assess_runway(t)
        rows.append({
            "ticker": a.ticker,
            "cash_eur": a.cash_eur,
            "quarterly_burn_eur": a.quarterly_burn_eur,
            "runway_quarters": a.runway_quarters,
            "period_end": a.period_end,
            "confidence": a.confidence,
        })
    if not rows:
        return pd.DataFrame(columns=_PANEL_COLS)
    df = pd.DataFrame(rows)
    # sort by riskiest first (lowest finite runway) — push inf to bottom
    df["_sort"] = df["runway_quarters"].replace([np.inf, -np.inf], np.nan).fillna(1e9)
    return df.sort_values("_sort").drop(columns="_sort").reset_index(drop=True)
