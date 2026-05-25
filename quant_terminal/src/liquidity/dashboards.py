"""Streamlit render blocks for the liquidity & borrow section.

The render helpers accept pre-computed DataFrames; the host ``app.py``
runs ``adv_panel`` + ``slippage_panel`` + ``borrow_panel`` and feeds the
joined frame here.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import streamlit as st

from src.viz.theme import fmt_eur


def _fmt_days(v: float) -> str:
    if v is None or (isinstance(v, float) and (np.isnan(v) or np.isinf(v))):
        return "∞"
    if v >= 100:
        return f"{v:,.0f}d"
    return f"{v:.1f}d"


def _fmt_bps(v: float) -> str:
    if v is None or (isinstance(v, float) and (np.isnan(v) or np.isinf(v))):
        return "n/a"
    return f"{v:,.1f} bps"


def _fmt_pct(v: float | None) -> str:
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return "n/a"
    return f"{v:.1f}%"


def render_liquidity_table(df: pd.DataFrame, title: str = "Liquidity & impact") -> None:
    """Render the consolidated liquidity table.

    Expected columns (any subset):
        ticker, weight_eur, adv_usd, adv_eur,
        days_to_liq_10pct, days_to_liq_20pct,
        slippage_bps_1pct_trade, short_interest_pct, borrow_estimate.
    """
    st.subheader(title)
    if df is None or df.empty:
        st.info("No liquidity data available — check that holdings resolved to yfinance tickers.")
        return

    shown = df.copy()
    if "weight_eur" in shown.columns:
        shown["weight (EUR)"] = shown["weight_eur"].apply(lambda v: fmt_eur(float(v)) if pd.notna(v) else "n/a")
    if "adv_usd" in shown.columns:
        shown["ADV ($)"] = shown["adv_usd"].apply(lambda v: f"${v:,.0f}" if pd.notna(v) and np.isfinite(v) else "n/a")
    if "adv_eur" in shown.columns:
        shown["ADV (EUR)"] = shown["adv_eur"].apply(lambda v: fmt_eur(float(v)) if pd.notna(v) and np.isfinite(v) else "n/a")
    if "days_to_liq_10pct" in shown.columns:
        shown["Days @10%"] = shown["days_to_liq_10pct"].apply(_fmt_days)
    if "days_to_liq_20pct" in shown.columns:
        shown["Days @20%"] = shown["days_to_liq_20pct"].apply(_fmt_days)
    if "slippage_bps_1pct_trade" in shown.columns:
        shown["Slippage (1% trade)"] = shown["slippage_bps_1pct_trade"].apply(_fmt_bps)
    if "short_interest_pct" in shown.columns:
        shown["Short interest"] = shown["short_interest_pct"].apply(_fmt_pct)
    if "borrow_estimate" in shown.columns:
        shown["Borrow"] = shown["borrow_estimate"].fillna("n/a")

    display_cols = ["ticker"]
    for c in ("weight (EUR)", "ADV ($)", "ADV (EUR)", "Days @10%", "Days @20%",
              "Slippage (1% trade)", "Short interest", "Borrow"):
        if c in shown.columns:
            display_cols.append(c)
    st.dataframe(shown[display_cols], use_container_width=True, hide_index=True)
    st.caption(
        "Slippage uses simplified Almgren-Chriss "
        f"(k=0.1 * sigma * sqrt(trade/ADV)). Short-interest is a stale yfinance estimate."
    )


def render_borrow_panel(df: pd.DataFrame) -> None:
    """Compact short-interest / borrow estimate table."""
    st.subheader("Borrow & short interest")
    if df is None or df.empty:
        st.info("No borrow data resolved.")
        return
    shown = df.copy()
    if "short_interest_pct" in shown.columns:
        shown["short_interest_pct"] = shown["short_interest_pct"].apply(_fmt_pct)
    if "days_to_cover" in shown.columns:
        shown["days_to_cover"] = shown["days_to_cover"].apply(
            lambda v: f"{v:.1f}" if pd.notna(v) else "n/a"
        )
    cols = [c for c in (
        "ticker", "short_interest_pct", "days_to_cover",
        "shares_short", "float_shares", "borrow_estimate", "source",
    ) if c in shown.columns]
    st.dataframe(shown[cols], use_container_width=True, hide_index=True)
    st.caption("Source: yfinance.info — sparse, stale, treat as estimate only.")
