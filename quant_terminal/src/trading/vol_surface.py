"""Volatility surface — 3D IV plot across (DTE, moneyness).

Builds a sparse grid (DTE × moneyness) from an option chain and interpolates
to produce a smooth Plotly Surface plot. The visual highlights where the
"fat" of the skew lives (e.g. left-tail puts on small-caps) and helps spot
calendar arbitrage opportunities at a glance.

Public API
----------
* ``build_surface_grid(contracts, spot) -> pd.DataFrame``
  Returns a long DataFrame ``[dte, moneyness, iv, right]`` for all contracts
  with an IV.
* ``surface_pivot(grid, right) -> tuple[ndarray, ndarray, ndarray]``
  Pivots to a (m × n) IV matrix indexed by DTE × moneyness, fills small gaps.
* ``render_vol_surface(contracts, spot, ticker)`` — Streamlit-side viz.
"""
from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd
import plotly.graph_objects as go

from src.common.schemas import OptionContract
from src.utils.logging import get_logger
from src.viz.theme import PALETTE

log = get_logger(__name__)


def build_surface_grid(
    contracts: list[OptionContract], spot: float,
) -> pd.DataFrame:
    """Long DataFrame: dte, moneyness, iv, right, strike, expiry."""
    if not contracts or spot is None or spot <= 0:
        return pd.DataFrame()
    today = date.today()
    rows = []
    for c in contracts:
        if c.iv is None or c.iv <= 0 or c.iv >= 5:
            continue
        dte = (c.expiry - today).days
        if dte < 0:
            continue
        rows.append({
            "expiry": c.expiry,
            "dte": dte,
            "strike": float(c.strike),
            "moneyness": float(c.strike) / spot - 1.0,
            "iv": float(c.iv),
            "right": c.right.value,
        })
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows)


def surface_pivot(
    grid: pd.DataFrame, right: str = "C",
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Pivot to (m × n) IV matrix. Returns (dte_axis, moneyness_axis, Z)."""
    if grid is None or grid.empty:
        return np.array([]), np.array([]), np.array([[]])
    sub = grid[grid["right"] == right].copy()
    if sub.empty:
        return np.array([]), np.array([]), np.array([[]])

    # Bucket moneyness into discrete bins so the surface looks clean.
    # Range ±50% around spot in 5% steps.
    bins = np.round(np.arange(-0.50, 0.51, 0.05), 2)
    sub["m_bin"] = pd.cut(sub["moneyness"], bins=bins, labels=bins[:-1] + 0.025,
                            include_lowest=True)
    pivot = sub.pivot_table(
        index="dte", columns="m_bin", values="iv", aggfunc="mean", observed=True,
    )
    if pivot.empty:
        return np.array([]), np.array([]), np.array([[]])
    pivot = pivot.sort_index().interpolate(axis=1, limit_direction="both")
    dte_axis = pivot.index.to_numpy(dtype=float)
    money_axis = np.array([float(c) for c in pivot.columns], dtype=float)
    Z = pivot.to_numpy(dtype=float)
    return dte_axis, money_axis, Z


def render_vol_surface(
    contracts: list[OptionContract], spot: float, ticker: str,
) -> None:
    """Streamlit-side: render a 3D plotly surface for calls and puts."""
    import streamlit as st

    grid = build_surface_grid(contracts, spot)
    if grid.empty:
        st.info("Insufficient IV data on the chain to build a surface.")
        return

    sel_col, _ = st.columns([1, 3])
    side = sel_col.radio("Side", ["Calls", "Puts"], horizontal=True,
                          key=f"volsurf_side_{ticker}")
    right = "C" if side == "Calls" else "P"

    dte, money, Z = surface_pivot(grid, right=right)
    if dte.size == 0 or money.size == 0 or Z.size == 0:
        st.info(f"No {side.lower()} IV grid available.")
        return

    fig = go.Figure(go.Surface(
        z=Z * 100,                                # display in %
        x=money * 100,                            # moneyness in % (strike/spot - 1)
        y=dte,
        colorscale=[
            [0.0, PALETTE.accent],
            [0.5, PALETTE.warning],
            [1.0, PALETTE.loss],
        ],
        contours={
            "z": {"show": True, "usecolormap": True, "highlightcolor": PALETTE.fg,
                  "project_z": True, "size": 5},
        },
        colorbar={"title": "IV (%)", "x": 1.02},
        hovertemplate=(
            "DTE: %{y} d<br>"
            "Moneyness: %{x:.1f}%<br>"
            "IV: %{z:.1f}%<extra></extra>"
        ),
    ))
    fig.update_layout(
        template="plotly_dark",
        title=f"{ticker} — IV surface ({side})",
        scene=dict(
            xaxis_title="Moneyness % (strike/spot − 1)",
            yaxis_title="Days to expiry",
            zaxis_title="IV %",
            xaxis=dict(color=PALETTE.fg_muted, gridcolor=PALETTE.border,
                       backgroundcolor=PALETTE.bg),
            yaxis=dict(color=PALETTE.fg_muted, gridcolor=PALETTE.border,
                       backgroundcolor=PALETTE.bg),
            zaxis=dict(color=PALETTE.fg_muted, gridcolor=PALETTE.border,
                       backgroundcolor=PALETTE.bg),
            camera=dict(eye=dict(x=1.8, y=-1.8, z=1.2)),
        ),
        paper_bgcolor=PALETTE.bg,
        font_color=PALETTE.fg,
        height=560,
        margin=dict(l=0, r=0, t=50, b=0),
    )
    st.plotly_chart(fig, use_container_width=True, key=f"vol_surface_{ticker}_{right}")

    # KPI strip — extreme points on the surface
    kcols = st.columns(4)
    flat_min = np.nanmin(Z) * 100
    flat_max = np.nanmax(Z) * 100
    kcols[0].metric("Min IV", f"{flat_min:.1f}%")
    kcols[1].metric("Max IV", f"{flat_max:.1f}%")
    kcols[2].metric("Skew range", f"{flat_max - flat_min:.1f} pts")
    kcols[3].metric("Sample points", f"{int(np.sum(~np.isnan(Z)))}")

    # Underlying long-form data for the technical user
    with st.expander("Raw IV grid (long form)"):
        st.dataframe(
            grid[grid["right"] == right]
            .sort_values(["dte", "strike"])
            .reset_index(drop=True),
            use_container_width=True, hide_index=True,
        )


__all__ = ["build_surface_grid", "surface_pivot", "render_vol_surface"]
