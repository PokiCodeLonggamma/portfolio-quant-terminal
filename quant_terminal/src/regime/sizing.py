"""Regime-conditional sizing — UI-only multiplier driven by the HMM state.

When the HMM detects HIGH-volatility regimes (typically the top quartile of
the state machine's σ ladder), discretionary trade size should automatically
tighten. This module exposes a thin helper that converts a state label into a
sizing multiplier, plus a Streamlit pill renderer.

NO backend computation is altered — this is a recommendation layer the trade
ticket UI can surface to the user before they hit Buy.
"""
from __future__ import annotations

import streamlit as st

from src.regime.hmm import HMMRegimeResult, REGIME_COLORS
from src.viz.theme import PALETTE, hex_to_rgba


# Default multipliers — easy to tune from a single place.
_MULT_BY_LABEL = {
    "CALM":     1.20,
    "LOW vol":  1.00,
    "MID vol":  0.75,
    "HIGH vol": 0.50,
    "PANIC":    0.25,
}


def regime_size_multiplier(label: str) -> float:
    """Return the sizing multiplier for a regime label (1.0 = baseline)."""
    if not label:
        return 1.0
    return float(_MULT_BY_LABEL.get(label, 1.0))


def render_regime_sizing_pill(
    result: HMMRegimeResult | None, baseline_size_eur: float,
) -> None:
    """Render an inline pill: current regime → recommended sizing.

    Used in the Trade Ticket and Pre-event wizard to nudge the user toward
    risk-appropriate sizing.
    """
    if result is None:
        return
    lbl = result.current_label
    mult = regime_size_multiplier(lbl)
    color = REGIME_COLORS.get(lbl, PALETTE.fg_muted)
    rec = baseline_size_eur * mult
    delta = rec - baseline_size_eur
    delta_pct = (mult - 1.0) * 100
    delta_str = (
        f"<span style='color:{PALETTE.profit};'>+{delta:,.0f} € · +{delta_pct:.0f}%</span>"
        if mult > 1.0 else
        f"<span style='color:{PALETTE.loss};'>{delta:,.0f} € · {delta_pct:.0f}%</span>"
        if mult < 1.0 else
        f"<span style='color:{PALETTE.fg_muted};'>unchanged</span>"
    )
    st.markdown(
        f"""
        <div style='background:{hex_to_rgba(color, 0.08)};
                    border:1px solid {color}55;border-radius:10px;
                    padding:10px 14px;margin:8px 0;'>
            <div style='display:flex;justify-content:space-between;align-items:center;
                        gap:12px;flex-wrap:wrap;'>
                <div style='font-size:0.7rem;color:{PALETTE.fg_muted};
                            text-transform:uppercase;letter-spacing:0.08em;'>
                    HMM regime suggestion
                </div>
                <div style='font-family:monospace;font-size:0.78rem;
                            color:{color};font-weight:600;'>{lbl} → ×{mult:.2f}</div>
            </div>
            <div style='margin-top:6px;font-size:0.85rem;color:{PALETTE.fg};'>
                Baseline size €{baseline_size_eur:,.0f} → recommended
                <strong style='font-family:monospace;color:{color};'>
                    €{rec:,.0f}</strong>
                &nbsp;·&nbsp; {delta_str}
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


__all__ = ["regime_size_multiplier", "render_regime_sizing_pill"]
