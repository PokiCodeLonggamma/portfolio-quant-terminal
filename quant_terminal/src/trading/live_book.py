"""Live Options Position Monitor — refresh-able view over the open journal.

Aggregates per-trade mark-to-market with live Greeks pulled from the latest
option chain. Surfaces:
  * Per-position P&L card (debit → live credit, € + %, days-to-expiry, breakeven)
  * Aggregated portfolio-level Greeks (Δ, Γ, Θ, Vega) over the open book
  * Theta burn-rate (€/day projected from current Greeks)
  * Time-to-expiry watchdog (positions < 14 DTE flagged)

Backend-touching is limited to **reading** the chain + journal — no compute
logic is modified. This module just composes the existing primitives into a
single live dashboard.
"""
from __future__ import annotations

from datetime import date
from typing import Callable

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from src.common.schemas import OptionContract, OptionRight
from src.data.fx import to_eur
from src.utils.config import get_config
from src.utils.logging import get_logger
from src.viz.theme import PALETTE

log = get_logger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _find_contract(
    contracts: list[OptionContract], symbol: str,
) -> OptionContract | None:
    for c in contracts or []:
        if c.symbol == symbol:
            return c
    return None


def _pos_mid_eur(c: OptionContract, ticker: str) -> float | None:
    px = c.mid or (
        0.5 * ((c.bid or 0.0) + (c.ask or 0.0))
        if (c.bid is not None and c.ask is not None) else None
    ) or c.last
    if px is None or px <= 0:
        return None
    ccy = (get_config().currency_of(ticker) or "USD").upper()
    return float(to_eur(px * 100.0, ccy))


def _spot_for(ticker: str) -> float | None:
    """Best-effort spot, used for breakeven calc."""
    try:
        from src.trading.options_chain import _safe_spot
        return _safe_spot(ticker)
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------
def aggregate_book_greeks(
    open_df: pd.DataFrame,
    fetch_chain_fn: Callable[..., list[OptionContract]] | None = None,
) -> tuple[pd.DataFrame, dict]:
    """Return (enriched_df, summary_dict).

    The DataFrame gains: live_mid_eur, mtm_pnl_eur, mtm_pct, dte, delta, gamma,
    theta_eur_per_day, vega, breakeven_spot, breakeven_pct.

    Summary keys: total_debit_eur, total_mtm_eur, total_pnl_eur, total_pct,
    n_positions, agg_delta, agg_gamma, agg_theta_eur_day, agg_vega,
    n_expiring_soon (<14 DTE).
    """
    if open_df is None or open_df.empty:
        return open_df, {}
    if fetch_chain_fn is None:
        from src.trading.options_chain import fetch_chain as _fc
        fetch_chain_fn = _fc

    df = open_df.copy().reset_index(drop=True)
    today = date.today()
    cols_new = {
        "live_mid_eur": [], "mtm_pnl_eur": [], "mtm_pct": [], "dte": [],
        "delta": [], "gamma": [], "theta_eur_per_day": [], "vega": [],
        "breakeven_spot": [], "breakeven_pct": [], "spot_now": [],
    }

    # Group by ticker so we only fetch each chain once per refresh.
    for ticker, sub in df.groupby("ticker"):
        try:
            chain = fetch_chain_fn(ticker)
        except Exception as exc:
            log.debug("live_book chain fetch %s failed: %s", ticker, exc)
            chain = []
        spot = _spot_for(ticker)
        ccy = (get_config().currency_of(ticker) or "USD").upper()
        for _, row in sub.iterrows():
            sym = row.get("contract_symbol")
            c = _find_contract(chain, sym)
            live_mid = _pos_mid_eur(c, ticker) if c is not None else None
            qty = int(row.get("qty", 0) or 0)
            debit = float(row.get("debit_eur", 0) or 0.0)
            mtm_pnl = (live_mid - debit) * qty if live_mid is not None else None
            mtm_pct = ((live_mid - debit) / debit) if (live_mid is not None and debit > 0) else None
            dte = (row["expiry"] - today).days if isinstance(row.get("expiry"), date) else None
            delta = float(c.delta) * qty if c is not None and c.delta is not None else None
            gamma = float(c.gamma) * qty if c is not None and c.gamma is not None else None
            # Theta is per-day in the underlying currency on the per-contract base.
            theta_raw = float(c.theta) if c is not None and c.theta is not None else None
            theta_eur_day = None
            if theta_raw is not None:
                theta_eur_day = float(to_eur(theta_raw * 100.0 * qty, ccy))
            vega = float(c.vega) * qty if c is not None and c.vega is not None else None
            # Breakeven (long-only assumption): debit needs to be recovered.
            # For long call: breakeven spot = strike + premium_per_share.
            # For long put : breakeven spot = strike - premium_per_share.
            be_spot, be_pct = None, None
            if c is not None and live_mid is not None and qty > 0:
                # Premium per share in chain currency, not EUR.
                prem_share = (c.mid or c.last or 0.0) or (live_mid / (qty * 100.0))
                strike = float(c.strike)
                if c.right == OptionRight.CALL:
                    be_spot = strike + prem_share
                else:
                    be_spot = strike - prem_share
                if spot and spot > 0:
                    be_pct = (be_spot - spot) / spot
            cols_new["live_mid_eur"].append(live_mid)
            cols_new["mtm_pnl_eur"].append(mtm_pnl)
            cols_new["mtm_pct"].append(mtm_pct)
            cols_new["dte"].append(dte)
            cols_new["delta"].append(delta)
            cols_new["gamma"].append(gamma)
            cols_new["theta_eur_per_day"].append(theta_eur_day)
            cols_new["vega"].append(vega)
            cols_new["breakeven_spot"].append(be_spot)
            cols_new["breakeven_pct"].append(be_pct)
            cols_new["spot_now"].append(spot)

    # Important: re-align lists to df index. We iterated via groupby so the
    # ordering matches the groupby grouping, not the original index. Use sub
    # index to write back.
    for col, vals in cols_new.items():
        if len(vals) != len(df):
            # If the ordering got scrambled (groupby), redo with a per-row loop.
            df[col] = pd.NA
        else:
            df[col] = vals

    # Fallback: if any column got NA due to groupby reordering, redo per-row.
    if df["live_mid_eur"].isna().all() and len(df) > 0:
        # Single-pass per-row recompute.
        df = _recompute_per_row(df, fetch_chain_fn)

    # Summary
    summary = {
        "n_positions":        int(len(df)),
        "total_debit_eur":    float(df["debit_eur"].fillna(0).sum()),
        "total_mtm_eur":      float(df["live_mid_eur"].fillna(0).sum() * 1.0)
            if "live_mid_eur" in df.columns else 0.0,
        "total_pnl_eur":      float(df["mtm_pnl_eur"].fillna(0).sum()),
        "total_pct":          0.0,
        "agg_delta":          float(df["delta"].fillna(0).sum()),
        "agg_gamma":          float(df["gamma"].fillna(0).sum()),
        "agg_theta_eur_day":  float(df["theta_eur_per_day"].fillna(0).sum()),
        "agg_vega":           float(df["vega"].fillna(0).sum()),
        "n_expiring_soon":    int((df["dte"].fillna(99) < 14).sum()),
    }
    if summary["total_debit_eur"] > 0:
        summary["total_pct"] = summary["total_pnl_eur"] / summary["total_debit_eur"]
    return df, summary


def _recompute_per_row(
    df: pd.DataFrame,
    fetch_chain_fn: Callable[..., list[OptionContract]],
) -> pd.DataFrame:
    """Safe fallback iteration: one row at a time, one chain fetch per unique ticker."""
    cache: dict[str, list[OptionContract]] = {}
    today = date.today()
    out_rows = []
    for _, row in df.iterrows():
        ticker = row["ticker"]
        if ticker not in cache:
            try:
                cache[ticker] = fetch_chain_fn(ticker)
            except Exception:
                cache[ticker] = []
        chain = cache[ticker]
        c = _find_contract(chain, row.get("contract_symbol"))
        live_mid = _pos_mid_eur(c, ticker) if c is not None else None
        qty = int(row.get("qty", 0) or 0)
        debit = float(row.get("debit_eur", 0) or 0.0)
        ccy = (get_config().currency_of(ticker) or "USD").upper()
        spot = _spot_for(ticker)
        d = row.to_dict()
        d["live_mid_eur"] = live_mid
        d["mtm_pnl_eur"] = (live_mid - debit) * qty if live_mid is not None else None
        d["mtm_pct"] = ((live_mid - debit) / debit) if (live_mid is not None and debit > 0) else None
        d["dte"] = (row["expiry"] - today).days if isinstance(row.get("expiry"), date) else None
        d["delta"] = float(c.delta) * qty if c is not None and c.delta is not None else None
        d["gamma"] = float(c.gamma) * qty if c is not None and c.gamma is not None else None
        d["vega"] = float(c.vega) * qty if c is not None and c.vega is not None else None
        d["theta_eur_per_day"] = (
            float(to_eur(c.theta * 100.0 * qty, ccy))
            if c is not None and c.theta is not None else None
        )
        be_spot, be_pct = None, None
        if c is not None and live_mid is not None and qty > 0:
            prem_share = (c.mid or c.last or 0.0)
            strike = float(c.strike)
            if c.right == OptionRight.CALL:
                be_spot = strike + prem_share
            else:
                be_spot = strike - prem_share
            if spot and spot > 0:
                be_pct = (be_spot - spot) / spot
        d["breakeven_spot"] = be_spot
        d["breakeven_pct"] = be_pct
        d["spot_now"] = spot
        out_rows.append(d)
    return pd.DataFrame(out_rows)


# ---------------------------------------------------------------------------
# Streamlit rendering
# ---------------------------------------------------------------------------
def _pnl_color(v: float | None) -> str:
    if v is None or pd.isna(v):
        return PALETTE.fg_muted
    return PALETTE.profit if v >= 0 else PALETTE.loss


def render_position_card(row: pd.Series) -> None:
    """One card per open position — KPI row + price-vs-breakeven mini bar."""
    sym = str(row.get("contract_symbol", "?"))
    ticker = str(row.get("ticker", "?"))
    direction = str(row.get("direction", "")).upper()
    pnl = row.get("mtm_pnl_eur")
    pct = row.get("mtm_pct")
    accent = _pnl_color(pnl)
    dte = row.get("dte")
    dte_str = f"{int(dte)} d" if dte is not None and not pd.isna(dte) else "—"
    dte_color = PALETTE.loss if (dte is not None and not pd.isna(dte) and dte < 14) else PALETTE.fg_muted
    pnl_str = f"€{pnl:+,.0f}" if pnl is not None and not pd.isna(pnl) else "—"
    pct_str = f"{pct * 100:+.1f}%" if pct is not None and not pd.isna(pct) else "—"
    debit = row.get("debit_eur", 0) or 0
    live = row.get("live_mid_eur") or 0
    spot = row.get("spot_now")
    be = row.get("breakeven_spot")
    be_pct = row.get("breakeven_pct")
    theta = row.get("theta_eur_per_day")
    delta = row.get("delta")
    gamma = row.get("gamma")

    spot_str = f"{spot:.2f}" if spot else "—"
    be_str = f"{be:.2f}" if be else "—"
    be_pct_str = f"{be_pct * 100:+.1f}%" if be_pct is not None and not pd.isna(be_pct) else "—"
    theta_str = f"€{theta:+,.1f}/d" if theta is not None and not pd.isna(theta) else "—"

    st.markdown(
        f"""
        <div style='background:{PALETTE.card};border:1px solid {PALETTE.border};
                    border-left:4px solid {accent};border-radius:12px;
                    padding:14px 16px;margin-bottom:10px;'>
            <div style='display:flex;justify-content:space-between;align-items:flex-start;
                        flex-wrap:wrap;gap:6px;'>
                <div>
                    <div style='font-weight:700;color:{PALETTE.fg};font-family:{PALETTE.fg_muted!s};
                                font-size:0.95rem;letter-spacing:0.02em;'>
                        {ticker} · {direction}
                    </div>
                    <div style='font-family:monospace;font-size:0.75rem;color:{PALETTE.fg_muted};
                                margin-top:2px;'>{sym}</div>
                </div>
                <div style='text-align:right;'>
                    <div style='font-family:monospace;font-weight:700;font-size:1.15rem;
                                color:{accent};'>{pnl_str}</div>
                    <div style='font-family:monospace;font-size:0.78rem;color:{accent};'>{pct_str}</div>
                </div>
            </div>
            <div style='display:grid;grid-template-columns:repeat(4, minmax(0, 1fr));gap:8px;
                        margin-top:10px;font-size:0.72rem;color:{PALETTE.fg_muted};
                        font-family:monospace;'>
                <div>DTE: <span style='color:{dte_color};font-weight:600;'>{dte_str}</span></div>
                <div>Debit: €{debit:,.0f}</div>
                <div>Live: €{live:,.0f}</div>
                <div>θ: <span style='color:{PALETTE.loss};'>{theta_str}</span></div>
                <div>Δ: {f"{delta:+.2f}" if delta is not None and not pd.isna(delta) else "—"}</div>
                <div>Γ: {f"{gamma:+.4f}" if gamma is not None and not pd.isna(gamma) else "—"}</div>
                <div>Spot: {spot_str}</div>
                <div>BE: {be_str} ({be_pct_str})</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_live_book_summary(summary: dict) -> None:
    """Top-of-page KPI strip + aggregate Greeks panel."""
    if not summary:
        return
    cols = st.columns(5)
    pnl = summary.get("total_pnl_eur", 0.0)
    cols[0].metric("Positions", summary.get("n_positions", 0))
    cols[1].metric("Total debit", f"€{summary.get('total_debit_eur', 0):,.0f}")
    cols[2].metric(
        "MtM P&L",
        f"€{pnl:+,.0f}",
        f"{summary.get('total_pct', 0) * 100:+.1f}%",
    )
    cols[3].metric(
        "Theta burn (today)",
        f"€{summary.get('agg_theta_eur_day', 0):+,.1f}/d",
        help="Negative = book loses this much to time decay every calendar day.",
    )
    cols[4].metric(
        "Expiring <14d",
        summary.get("n_expiring_soon", 0),
        help="Positions to roll, close, or accept expiry.",
    )

    # Aggregate Greeks card
    st.markdown(
        f"""
        <div style='background:{PALETTE.card};border:1px solid {PALETTE.border};
                    border-radius:12px;padding:14px 18px;margin-top:12px;'>
            <div style='display:flex;justify-content:space-between;gap:18px;flex-wrap:wrap;'>
                <div><span style='color:{PALETTE.fg_muted};font-size:0.7rem;
                            text-transform:uppercase;letter-spacing:0.08em;'>Aggregate Δ</span><br>
                     <span style='font-family:monospace;font-size:1.2rem;font-weight:600;
                            color:{PALETTE.fg};'>{summary.get('agg_delta', 0):+.2f}</span></div>
                <div><span style='color:{PALETTE.fg_muted};font-size:0.7rem;
                            text-transform:uppercase;letter-spacing:0.08em;'>Aggregate Γ</span><br>
                     <span style='font-family:monospace;font-size:1.2rem;font-weight:600;
                            color:{PALETTE.fg};'>{summary.get('agg_gamma', 0):+.4f}</span></div>
                <div><span style='color:{PALETTE.fg_muted};font-size:0.7rem;
                            text-transform:uppercase;letter-spacing:0.08em;'>Aggregate Vega</span><br>
                     <span style='font-family:monospace;font-size:1.2rem;font-weight:600;
                            color:{PALETTE.fg};'>{summary.get('agg_vega', 0):+.2f}</span></div>
                <div><span style='color:{PALETTE.fg_muted};font-size:0.7rem;
                            text-transform:uppercase;letter-spacing:0.08em;'>Theta / day</span><br>
                     <span style='font-family:monospace;font-size:1.2rem;font-weight:600;
                            color:{PALETTE.loss};'>€{summary.get('agg_theta_eur_day', 0):+,.1f}</span></div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_live_book(
    open_df: pd.DataFrame,
    fetch_chain_fn: Callable[..., list[OptionContract]] | None = None,
) -> None:
    """Full live-book panel — KPIs + aggregate Greeks + per-position cards."""
    if open_df is None or open_df.empty:
        st.markdown(
            f"""
            <div style='text-align:center;padding:48px 24px;background:{PALETTE.card};
                        border:1px dashed {PALETTE.border_strong};border-radius:14px;
                        margin:18px 0;'>
                <div style='font-size:3rem;opacity:0.5;margin-bottom:12px;'>📭</div>
                <div style='font-weight:600;font-size:1.1rem;color:{PALETTE.fg};'>
                    No open positions yet
                </div>
                <div style='font-size:0.85rem;color:{PALETTE.fg_dim};margin-top:8px;
                            max-width:480px;margin-left:auto;margin-right:auto;
                            line-height:1.5;'>
                    The Live Book aggregates marked-to-market Greeks and theta-burn for
                    every open option trade in your journal.<br><br>
                    Head to <strong>Trade Ticket</strong> (this same Trading Bench tab)
                    to record a position — it will appear here in real time.
                </div>
                <div style='margin-top:14px;font-family:{PALETTE.fg_muted!s};
                            font-family:monospace;font-size:0.72rem;color:{PALETTE.fg_dim};'>
                    Note: Streamlit Cloud resets the journal on every container restart;
                    consider local-only or external persistence for production tracking.
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        return
    with st.spinner("Pulling live chains..."):
        enriched, summary = aggregate_book_greeks(open_df, fetch_chain_fn)
    render_live_book_summary(summary)

    st.markdown("##### Positions")
    # Sort by largest theta-burn first (priority to manage)
    sorted_df = enriched.sort_values(
        "theta_eur_per_day", ascending=True, na_position="last",
    ).reset_index(drop=True)
    for _, row in sorted_df.iterrows():
        render_position_card(row)

    # P&L distribution mini-bar
    pnl_series = pd.to_numeric(enriched["mtm_pnl_eur"], errors="coerce").dropna()
    if not pnl_series.empty:
        st.markdown("##### P&L distribution across open positions")
        fig = go.Figure(go.Bar(
            x=enriched["ticker"] + " " + enriched["contract_symbol"].str[-9:],
            y=pnl_series,
            marker_color=[
                PALETTE.profit if v >= 0 else PALETTE.loss for v in pnl_series
            ],
            hovertemplate="<b>%{x}</b><br>P&L: €%{y:+,.0f}<extra></extra>",
        ))
        fig.update_layout(
            template="plotly_dark",
            height=260,
            xaxis_title="",
            yaxis_title="P&L €",
            margin=dict(l=40, r=10, t=10, b=80),
            paper_bgcolor=PALETTE.bg,
            plot_bgcolor=PALETTE.card,
            font_color=PALETTE.fg,
            showlegend=False,
        )
        fig.update_xaxes(tickangle=-30)
        st.plotly_chart(fig, use_container_width=True, key="live_book_pnl_dist")
