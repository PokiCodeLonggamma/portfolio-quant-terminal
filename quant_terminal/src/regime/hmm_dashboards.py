"""Streamlit rendering helpers for the HMM regime engine."""
from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from src.regime.hmm import HMMRegimeResult, REGIME_COLORS
from src.viz.theme import PALETTE, hex_to_rgba


def _state_color(label: str) -> str:
    return REGIME_COLORS.get(label, PALETTE.fg_muted)


def render_regime_hero(result: HMMRegimeResult, ticker: str) -> None:
    """Top-of-page regime badge + KPIs."""
    current = result.current_label
    color = _state_color(current)
    p = result.current_probs[current]

    st.markdown(
        f"""
        <div style='padding:18px;border-radius:12px;background:{hex_to_rgba(color, 0.10)};
                    border-left:6px solid {color};margin-bottom:12px;'>
            <div style='font-size:12px;color:{PALETTE.fg_muted};letter-spacing:0.05em;
                        text-transform:uppercase;'>Current regime — {ticker}</div>
            <div style='font-size:32px;font-weight:600;color:{color};margin-top:4px;'>
                {current}
            </div>
            <div style='font-size:14px;color:{PALETTE.fg};margin-top:4px;'>
                Posterior probability : <code>{p:.1%}</code>
                &nbsp;·&nbsp; State σ : <code>{result.stds[result.current_state]:.4f}</code>
                &nbsp;·&nbsp; Expected duration : <code>{result.expected_duration[current]:.0f} bars</code>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    cols = st.columns(result.n_states)
    for i, lbl in enumerate(result.state_labels):
        prob = result.current_probs[lbl]
        cols[i].metric(
            lbl,
            f"{prob:.0%}",
            help=f"σ = {result.stds[i]:.4f} · μ = {result.means[i]:+.5f}",
        )


def render_regime_path(
    result: HMMRegimeResult, price: pd.Series, ticker: str,
) -> None:
    """Overlay: closing price line + colored regime ribbon underneath."""
    px = price.reindex(result.index).ffill()
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=px.index, y=px.values,
        mode="lines",
        line=dict(color=PALETTE.fg, width=1.4),
        name="Close",
    ))
    # Regime ribbon — shaded vrects per contiguous state segment
    states = result.states
    if len(states) > 0:
        seg_start = 0
        for i in range(1, len(states) + 1):
            if i == len(states) or states[i] != states[seg_start]:
                lbl = result.state_labels[int(states[seg_start])]
                fig.add_vrect(
                    x0=result.index[seg_start],
                    x1=result.index[i - 1],
                    fillcolor=_state_color(lbl),
                    opacity=0.12,
                    line_width=0,
                )
                seg_start = i
    fig.update_layout(
        template="plotly_dark",
        title=f"{ticker} price + HMM regime path",
        xaxis_title="Date",
        yaxis_title="Close",
        height=380,
        margin=dict(l=40, r=20, t=50, b=30),
        plot_bgcolor=PALETTE.bg_elev,
        paper_bgcolor=PALETTE.bg,
        font_color=PALETTE.fg,
    )
    st.plotly_chart(fig, use_container_width=True, key=f"hmm_path_{ticker}")


def render_regime_posterior(result: HMMRegimeResult, ticker: str) -> None:
    """Stacked-area chart of posterior probabilities — visual of state mixing."""
    df = pd.DataFrame(
        result.state_probs,
        index=result.index,
        columns=result.state_labels,
    )
    fig = go.Figure()
    for lbl in result.state_labels:
        fig.add_trace(go.Scatter(
            x=df.index, y=df[lbl],
            mode="lines",
            stackgroup="one",
            name=lbl,
            line=dict(width=0.5, color=_state_color(lbl)),
            fillcolor=hex_to_rgba(_state_color(lbl), 0.55),
        ))
    fig.update_layout(
        template="plotly_dark",
        title=f"{ticker} regime posterior probabilities",
        xaxis_title="Date",
        yaxis_title="P(state | data)",
        yaxis_range=[0, 1],
        height=300,
        margin=dict(l=40, r=20, t=50, b=30),
        plot_bgcolor=PALETTE.bg_elev,
        paper_bgcolor=PALETTE.bg,
        font_color=PALETTE.fg,
        legend=dict(orientation="h", y=-0.18),
    )
    st.plotly_chart(fig, use_container_width=True, key=f"hmm_post_{ticker}")


def render_transition_heatmap(result: HMMRegimeResult, ticker: str) -> None:
    """Transition probability heatmap."""
    z = result.transition_matrix
    fig = go.Figure(go.Heatmap(
        z=z,
        x=result.state_labels,
        y=result.state_labels,
        colorscale="Blues",
        text=[[f"{v:.2f}" for v in row] for row in z],
        texttemplate="%{text}",
        textfont=dict(color=PALETTE.fg, size=14),
        showscale=False,
    ))
    fig.update_layout(
        template="plotly_dark",
        title="Transition matrix — P(j | i)",
        xaxis=dict(title="To state", side="bottom"),
        yaxis=dict(title="From state", autorange="reversed"),
        height=300,
        margin=dict(l=60, r=20, t=50, b=40),
        plot_bgcolor=PALETTE.bg,
        paper_bgcolor=PALETTE.bg,
        font_color=PALETTE.fg,
    )
    st.plotly_chart(fig, use_container_width=True, key=f"hmm_trans_{ticker}")


def render_stationary(result: HMMRegimeResult) -> None:
    """Show long-run state frequencies vs current state."""
    stat = result.stationary_distribution
    df = pd.DataFrame({
        "State": result.state_labels,
        "Long-run frequency": [f"{v:.1%}" for v in stat],
        "Current posterior": [f"{result.state_probs[-1, i]:.1%}"
                               for i in range(result.n_states)],
        "Mean return": [f"{m:+.5f}" for m in result.means],
        "Std dev (σ)": [f"{s:.4f}" for s in result.stds],
        "Expected duration (bars)": [f"{result.expected_duration[lbl]:.0f}"
                                       for lbl in result.state_labels],
    })
    st.dataframe(df, hide_index=True, use_container_width=True)


def render_model_diagnostics(result: HMMRegimeResult) -> None:
    """Convergence + information criteria pill row."""
    cols = st.columns(4)
    cols[0].metric("Converged", "Yes" if result.converged else "No")
    cols[1].metric("Log-likelihood", f"{result.log_likelihood:.1f}")
    cols[2].metric("AIC", f"{result.aic:.1f}",
                    help="Lower is better. Compare across n_states.")
    cols[3].metric("BIC", f"{result.bic:.1f}",
                    help="Lower is better. BIC penalises complexity harder than AIC.")
