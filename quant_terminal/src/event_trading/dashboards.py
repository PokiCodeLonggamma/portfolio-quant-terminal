"""Streamlit renderers for the 🎬 Event Trading tab."""
from __future__ import annotations

from typing import Callable

import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st

from src.common.schemas import CalendarEvent, OptionContract
from src.event_trading.earnings_simulator import shock_grid, simulate_position
from src.event_trading.pre_event_wizard import candidates_for_event
from src.viz.theme import PALETTE, PLOTLY_TEMPLATE, fmt_eur


def render_pre_event_wizard(
    events: list[CalendarEvent],
    universe: list[str],
    *,
    spot_lookup: dict[str, float],
    fetch_chain_fn: Callable[..., list[OptionContract]] | None,
    iv_rank_lookup: Callable[[str], float] | None = None,
    fx_to_eur: float = 1.10,
) -> None:
    st.markdown("### Pre-event setup wizard")
    if not events:
        st.info("Aucun catalyseur à venir dans la fenêtre.")
        return

    labels = [
        f"{e.start.strftime('%Y-%m-%d')} · {e.category} · {e.title[:60]}"
        for e in events
    ]
    pick = st.selectbox("Catalyseur à trader", labels, key="evt_wizard_pick")
    event = events[labels.index(pick)]

    target_delta = st.slider("Target delta (foot of gamma)",
                              0.05, 0.95, 0.25, 0.05, key="evt_wizard_delta")

    if fetch_chain_fn is None:
        st.warning("Pas de fetch_chain_fn câblé — wizard désactivé.")
        return

    with st.spinner("Building setup candidates…"):
        df = candidates_for_event(
            event, universe,
            spot_lookup=spot_lookup,
            fetch_chain_fn=fetch_chain_fn,
            iv_rank_lookup=iv_rank_lookup,
            fx_to_eur=fx_to_eur,
            target_delta=float(target_delta),
        )
    if df.empty:
        st.info("Aucun candidat exploitable (pas de chain, pas de delta, ou univers vide).")
        return
    # Round + display — coerce to numeric first to handle None/NaN cells (object dtype)
    show = df.copy()
    for c in ["iv_rank", "implied_move_pct", "historical_avg_move_pct", "score"]:
        if c in show.columns:
            show[c] = pd.to_numeric(show[c], errors="coerce").round(2)
    for c in ["debit_usd", "debit_eur"]:
        if c in show.columns:
            show[c] = pd.to_numeric(show[c], errors="coerce").round(0)
    st.dataframe(show.head(40), use_container_width=True, hide_index=True)

    # Highlight top-3
    st.markdown("##### Top 3 setups")
    for _, row in df.head(3).iterrows():
        st.markdown(
            f"- **{row['ticker']}** · {row['direction']} · Δ {row['target_delta']:.2f} "
            f"· strike {row['strike']:.2f} · debit ≈ {fmt_eur(row['debit_eur'] or 0)} · "
            f"score {row['score']:.1f} — {row['rationale']}"
        )


def render_earnings_simulator(
    open_options_df: pd.DataFrame | None,
    fetch_chain_fn: Callable[..., list[OptionContract]] | None,
    spot_lookup: dict[str, float],
    *,
    fx_to_eur: float = 1.10,
) -> None:
    st.markdown("### Earnings reaction simulator")

    if open_options_df is None or open_options_df.empty:
        st.info("Pas d'options ouvertes — simulateur affichera un scénario fictif.")
        # Synthetic demo : prompt for a manual contract
        ticker = st.text_input("Ticker (no positions yet)", "ASTS", key="evt_sim_ticker").upper()
        if not ticker or fetch_chain_fn is None:
            return
        with st.spinner(f"Chargement chaîne {ticker}…"):
            try:
                chain = fetch_chain_fn(ticker)
            except Exception:
                chain = []
        if not chain:
            st.warning("Pas de chaîne — impossible de simuler.")
            return
        contract = chain[0]
    else:
        pick = st.selectbox(
            "Position",
            open_options_df["contract_symbol"].tolist(),
            key="evt_sim_pos_pick",
        )
        row = open_options_df[open_options_df["contract_symbol"] == pick].iloc[0]
        ticker = str(row["ticker"])
        if fetch_chain_fn is None:
            st.warning("Pas de fetch_chain_fn câblé.")
            return
        with st.spinner(f"Chargement chaîne {ticker}…"):
            try:
                chain = fetch_chain_fn(ticker)
            except Exception:
                chain = []
        contract = next((c for c in chain if c.symbol == pick), None) or (chain[0] if chain else None)
        if contract is None:
            st.warning("Contrat introuvable dans la chaîne.")
            return

    # spot is passed explicitly to the simulator below
    spot_for_sim = spot_lookup.get(ticker, float(contract.strike))

    cols = st.columns(3)
    spot_shock = cols[0].slider("Spot shock (%)", -30, 30, 10, 1, key="evt_sim_spot") / 100.0
    iv_shock = cols[1].slider("IV shock (%)", -60, 50, -30, 5, key="evt_sim_iv") / 100.0
    qty = cols[2].number_input("Qty (contracts)", min_value=1, value=1, step=1,
                                key="evt_sim_qty")

    scen = simulate_position(
        contract, int(qty), float(spot_shock), float(iv_shock),
        spot=spot_for_sim, fx_to_eur=fx_to_eur,
    )
    if scen is None:
        st.warning("Simulation impossible (IV ou prix manquant).")
        return
    color = PALETTE.profit if scen.pnl_total_eur >= 0 else PALETTE.loss
    st.markdown(
        f"<div style='padding:12px;border-radius:8px;background:{PALETTE.card};"
        f"border:1px solid {PALETTE.border}'>"
        f"<div style='color:{PALETTE.fg_muted};font-size:0.8rem'>"
        f"{contract.symbol} · {scen.notes}</div>"
        f"<div style='font-size:1.4rem;font-weight:600;color:{color}'>"
        f"PnL : {fmt_eur(scen.pnl_total_eur, 2)}</div>"
        f"<div>price now {scen.price_now:.2f} → after {scen.price_after:.2f} · "
        f"IV {scen.iv_now * 100:.0f}% → {scen.iv_after * 100:.0f}%</div>"
        "</div>",
        unsafe_allow_html=True,
    )

    # Heatmap : spot grid × IV grid
    st.markdown("##### PnL grid")
    spot_grid = np.linspace(-0.25, 0.25, 11).tolist()
    iv_grid = np.linspace(-0.5, 0.2, 8).tolist()
    grid = shock_grid(contract, int(qty), spot_grid, iv_grid,
                        spot=spot_for_sim, fx_to_eur=fx_to_eur)
    if not grid.empty:
        pivot = grid.pivot(index="iv_shock_pct", columns="spot_shock_pct", values="pnl_eur")
        fig = px.imshow(
            pivot, color_continuous_scale="RdYlGn", aspect="auto",
            labels=dict(color="PnL EUR"), title="Earnings PnL surface (EUR)",
        )
        fig.update_layout(**PLOTLY_TEMPLATE["layout"])
        st.plotly_chart(fig, use_container_width=True)
