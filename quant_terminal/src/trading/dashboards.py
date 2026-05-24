"""Streamlit render blocks for the "Trading Bench" tab.

All render functions accept pre-fetched data (no I/O), apply the project's
`PLOTLY_TEMPLATE`, and namespace their widget keys with `trading_` to avoid
DuplicateWidgetID clashes with the other clusters.

Public render functions
-----------------------
* `render_catalyst_board(events, window_days=14)`
* `render_chain_explorer(contracts, underlying, spot, highlight_delta=0.25)`
* `render_gex_profile(gex_df, spot, gamma_flip)`
* `render_trade_ticket_form(ticker, net_ev_eur, fetch_chain_fn)`
* `render_journal(open_trades_df, closed_trades_df)`
* `render_iv_rank_pill(iv_rank_payload)`
* `render_squeeze_board(scores_df)`
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Callable

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from src.common.schemas import CalendarEvent, OptionContract
from src.trading.options_chain import chain_dataframe
from src.trading.trade_ticket import build_ticket
from src.viz.theme import PALETTE, PLOTLY_TEMPLATE, fmt_eur, fmt_pct


def _apply_template(fig: go.Figure) -> go.Figure:
    fig.update_layout(**PLOTLY_TEMPLATE["layout"])
    return fig


# ---------------------------------------------------------------------------
# Catalyst board
# ---------------------------------------------------------------------------
def render_catalyst_board(
    events: list[CalendarEvent] | None, window_days: int = 14,
) -> None:
    st.markdown("### Catalyst board")
    if not events:
        st.info("No upcoming catalysts in the selected window.")
        return
    today = date.today()
    rows = []
    for ev in events:
        days = (ev.start.date() - today).days
        if 0 <= days <= window_days:
            rows.append({
                "ticker": ev.ticker or "MACRO",
                "category": ev.category,
                "title": ev.title,
                "start": ev.start,
                "days_until": days,
                "source": ev.source,
            })
    if not rows:
        st.info(f"No catalysts inside the next {window_days} days.")
        return
    df = pd.DataFrame(rows).sort_values("days_until").reset_index(drop=True)
    st.dataframe(df, hide_index=True, use_container_width=True, key="trading_catalysts")


# ---------------------------------------------------------------------------
# Chain explorer
# ---------------------------------------------------------------------------
def render_chain_explorer(
    contracts: list[OptionContract],
    underlying: str,
    spot: float | None,
    highlight_delta: float = 0.25,
) -> None:
    st.markdown(f"### Chain explorer — `{underlying}`")
    cols = st.columns(3)
    cols[0].metric("Underlying", underlying)
    cols[1].metric("Spot (listing ccy)", f"{spot:,.2f}" if spot else "—")
    cols[2].metric("Contracts", len(contracts) if contracts else 0)

    if not contracts:
        st.info("No contracts loaded.")
        return

    df = chain_dataframe(contracts)
    if df.empty:
        st.info("Chain is empty.")
        return

    show_right = st.radio(
        "Right", ["C", "P", "Both"], horizontal=True,
        key=f"trading_chain_right_{underlying}",
    )
    sub = df if show_right == "Both" else df[df["right"] == show_right]

    # Highlight the row closest to highlight_delta
    if "delta" in sub.columns:
        sub = sub.copy()
        sub["|Δ−tgt|"] = (sub["delta"].abs() - highlight_delta).abs()
        sub = sub.sort_values(["expiry", "|Δ−tgt|", "strike"]).reset_index(drop=True)

    display_cols = [
        c for c in [
            "expiry", "right", "strike", "bid", "ask", "mid", "last", "iv",
            "delta", "gamma", "theta", "vega", "open_interest", "volume",
            "source", "|Δ−tgt|",
        ] if c in sub.columns
    ]
    st.dataframe(
        sub[display_cols],
        hide_index=True, use_container_width=True,
        key=f"trading_chain_{underlying}",
    )


# ---------------------------------------------------------------------------
# GEX profile
# ---------------------------------------------------------------------------
def render_gex_profile(
    gex_df: pd.DataFrame, spot: float | None, gamma_flip: float | None,
) -> None:
    st.markdown("### Net Gamma Exposure profile")
    if gex_df is None or gex_df.empty:
        st.info("No GEX data — chain missing greeks or open interest.")
        return

    colours = [PALETTE.profit if v >= 0 else PALETTE.loss for v in gex_df["net_gex_usd"]]
    fig = go.Figure(go.Bar(
        x=gex_df["strike"], y=gex_df["net_gex_usd"],
        marker_color=colours,
        name="Net GEX ($)",
    ))
    if spot is not None and spot > 0:
        fig.add_vline(x=spot, line_dash="dot", line_color=PALETTE.fg,
                      annotation_text=f"Spot {spot:.2f}", annotation_position="top")
    if gamma_flip is not None:
        fig.add_vline(x=gamma_flip, line_dash="dash", line_color=PALETTE.warning,
                      annotation_text=f"γ-flip {gamma_flip:.2f}",
                      annotation_position="bottom")
    fig.update_layout(
        title="Dealer net gamma per strike (USD)",
        xaxis_title="Strike", yaxis_title="Net GEX (USD)",
    )
    st.plotly_chart(_apply_template(fig), use_container_width=True,
                    key="trading_gex_chart")

    total = float(gex_df["net_gex_usd"].sum())
    cols = st.columns(3)
    cols[0].metric("Total net GEX (USD)", f"${total:,.0f}")
    cols[1].metric("Gamma flip", f"{gamma_flip:.2f}" if gamma_flip else "—")
    cols[2].metric(
        "Regime",
        "NEGATIVE — vol-amplifying" if total < 0 else "POSITIVE — vol-dampening",
    )


# ---------------------------------------------------------------------------
# IV-rank pill
# ---------------------------------------------------------------------------
def render_iv_rank_pill(iv_rank_payload: dict | None) -> None:
    if not iv_rank_payload:
        return
    rank = float(iv_rank_payload.get("iv_rank", 50.0))
    colour = (
        PALETTE.loss if rank > 80 else
        PALETTE.warning if rank > 60 else
        PALETTE.profit if rank < 30 else
        PALETTE.fg_muted
    )
    st.markdown(
        f"<div style='display:inline-block;padding:6px 12px;border-radius:14px;"
        f"background:{PALETTE.card};border:1px solid {colour};color:{colour};"
        f"font-weight:600;font-family:Fira Code, monospace;'>"
        f"IV rank {rank:.0f}/100"
        f"</div>",
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------------------
# Trade ticket form
# ---------------------------------------------------------------------------
def render_trade_ticket_form(
    ticker: str,
    net_ev_eur: float,
    fetch_chain_fn: Callable[..., list[OptionContract]] | None = None,
) -> None:
    st.markdown(f"### Trade ticket — `{ticker}`")
    with st.form(key=f"trading_ticket_form_{ticker}"):
        cols = st.columns(4)
        direction = cols[0].selectbox(
            "Direction", ["LONG_CALL", "LONG_PUT"],
            key=f"trading_ticket_dir_{ticker}",
        )
        target_delta = cols[1].number_input(
            "Target Δ", min_value=0.05, max_value=0.95, value=0.25, step=0.05,
            key=f"trading_ticket_delta_{ticker}",
        )
        dte_min = cols[2].number_input(
            "DTE min", min_value=1, max_value=120, value=14, step=1,
            key=f"trading_ticket_dtemin_{ticker}",
        )
        dte_max = cols[3].number_input(
            "DTE max", min_value=2, max_value=180, value=45, step=1,
            key=f"trading_ticket_dtemax_{ticker}",
        )
        max_debit = st.number_input(
            "Max debit EUR (optional cap)", min_value=0.0, value=0.0, step=10.0,
            key=f"trading_ticket_maxdebit_{ticker}",
            help="0 = use the 2%-of-net-EV cap only.",
        )
        submitted = st.form_submit_button("Build ticket", type="primary")

    if not submitted:
        return

    ticket = build_ticket(
        ticker=ticker,
        direction=direction,
        target_delta=float(target_delta),
        max_debit_eur=float(max_debit) if max_debit > 0 else None,
        net_ev_eur=float(net_ev_eur),
        dte_window=(int(dte_min), int(dte_max)),
        fetch_chain_fn=fetch_chain_fn,
    )

    st.markdown("#### Result")
    if ticket.refused_reasons:
        st.error("Trade refused:")
        for r in ticket.refused_reasons:
            st.write(f"- {r}")
    else:
        st.success("All gates passed.")

    kcols = st.columns(4)
    kcols[0].metric("Strike", f"{ticket.strike:.2f}")
    kcols[1].metric("Expiry", str(ticket.expiry))
    kcols[2].metric("Δ", f"{ticket.actual_delta:+.3f}")
    kcols[3].metric("Debit (EUR)", fmt_eur(ticket.debit_eur, 2))

    kcols2 = st.columns(4)
    kcols2[0].metric("Mid (EUR)", fmt_eur(ticket.mid_eur, 2))
    kcols2[1].metric("Breakeven", f"{ticket.breakeven:.2f}")
    kcols2[2].metric("R/R 1:1", f"{ticket.rr_1_to_1:.2f}")
    kcols2[3].metric("% of net EV", fmt_pct(ticket.pct_of_net_ev, 2))

    st.caption(f"Contract: `{ticket.contract_symbol}` — snapshot "
               f"{ticket.snapshot_ts:%Y-%m-%d %H:%M UTC}")


# ---------------------------------------------------------------------------
# Journal
# ---------------------------------------------------------------------------
def render_journal(
    open_trades_df: pd.DataFrame | None,
    closed_trades_df: pd.DataFrame | None,
) -> None:
    st.markdown("### Trading journal")
    open_df = open_trades_df if open_trades_df is not None else pd.DataFrame()
    closed_df = closed_trades_df if closed_trades_df is not None else pd.DataFrame()

    tab_open, tab_closed = st.tabs([
        f"Open ({len(open_df)})", f"Closed ({len(closed_df)})",
    ])

    with tab_open:
        if open_df.empty:
            st.info("No open trades.")
        else:
            show_cols = [c for c in [
                "trade_id", "opened_ts", "ticker", "direction", "contract_symbol",
                "strike", "expiry", "qty", "debit_eur",
                "mtm_credit_eur", "mtm_pnl_eur", "mtm_pct",
            ] if c in open_df.columns]
            st.dataframe(open_df[show_cols], hide_index=True, use_container_width=True,
                         key="trading_journal_open")
            if "mtm_pnl_eur" in open_df.columns:
                total = float(pd.to_numeric(open_df["mtm_pnl_eur"], errors="coerce").sum(skipna=True))
                st.metric("Unrealised PnL (EUR)", fmt_eur(total, 2))

    with tab_closed:
        if closed_df.empty:
            st.info("No closed trades.")
        else:
            show_cols = [c for c in [
                "trade_id", "opened_ts", "closed_ts", "ticker", "direction",
                "contract_symbol", "strike", "expiry", "qty",
                "debit_eur", "exit_credit_eur", "pnl_eur",
            ] if c in closed_df.columns]
            st.dataframe(closed_df[show_cols], hide_index=True, use_container_width=True,
                         key="trading_journal_closed")
            if "pnl_eur" in closed_df.columns:
                total = float(pd.to_numeric(closed_df["pnl_eur"], errors="coerce").sum(skipna=True))
                st.metric("Realised PnL (EUR)", fmt_eur(total, 2))


# ---------------------------------------------------------------------------
# Squeeze score board
# ---------------------------------------------------------------------------
def render_squeeze_board(scores_df: pd.DataFrame | None) -> None:
    st.markdown("### Gamma squeeze candidates")
    if scores_df is None or scores_df.empty:
        st.info("Run the squeeze scan to populate the board.")
        return
    st.dataframe(
        scores_df, hide_index=True, use_container_width=True,
        key="trading_squeeze_board",
    )


# Silence unused-import lint
_ = datetime  # used implicitly in renderer captions
