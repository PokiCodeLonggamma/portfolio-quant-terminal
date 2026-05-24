"""Streamlit render helpers for the Backtest tab.

Render functions accept ONLY data (no fetches, no side-effects) so they
can be unit-rendered from app.py.
"""
from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from src.backtest.metrics_diff import drawdown_series
from src.backtest.rules import RuleSpec, available_rules
from src.viz.theme import PALETTE, PLOTLY_TEMPLATE, fmt_eur, fmt_pct


# ---------------------------------------------------------------------------
# Rule picker
# ---------------------------------------------------------------------------
_DEFAULT_PARAMS: dict[str, dict] = {
    "max_single_position": {"max_pct": 0.20},
    "max_drawdown_trigger": {"threshold_pct": 0.10, "derisk_pct": 0.5},
    "max_theme_cap": {"max_pct": 0.40},
    "stop_loss": {"per_position_pct": 0.15},
    "momentum_entry": {"lookback_days": 60, "threshold": 0.0},
}


def render_rule_picker(
    available: list[str] | None = None,
    theme_map: dict[str, str] | None = None,
) -> list[RuleSpec]:
    """Render a multi-select + per-rule parameter widgets.

    Returns a list of :class:`RuleSpec` ready to be turned into concrete
    :class:`Rule` objects via :func:`src.backtest.rules.build_rule`.
    """
    options = available or available_rules()
    st.markdown("##### Rule stack")
    selected = st.multiselect(
        "Active rules (applied in order)",
        options=options,
        default=["max_single_position", "max_drawdown_trigger"],
        key="backtest_rules_select",
    )

    specs: list[RuleSpec] = []
    for rule_name in selected:
        defaults = _DEFAULT_PARAMS.get(rule_name, {})
        with st.expander(f"Params - {rule_name}", expanded=False):
            params: dict = {}
            if rule_name == "max_single_position":
                params["max_pct"] = st.slider(
                    "Max % per position",
                    min_value=0.05,
                    max_value=1.0,
                    value=float(defaults["max_pct"]),
                    step=0.01,
                    key=f"bt_{rule_name}_max_pct",
                )
            elif rule_name == "max_drawdown_trigger":
                params["threshold_pct"] = st.slider(
                    "Drawdown trigger (absolute)",
                    min_value=0.02,
                    max_value=0.50,
                    value=float(defaults["threshold_pct"]),
                    step=0.01,
                    key=f"bt_{rule_name}_threshold",
                )
                params["derisk_pct"] = st.slider(
                    "Derisk multiplier (0 = full exit, 1 = no-op)",
                    min_value=0.0,
                    max_value=1.0,
                    value=float(defaults["derisk_pct"]),
                    step=0.05,
                    key=f"bt_{rule_name}_derisk",
                )
            elif rule_name == "max_theme_cap":
                params["max_pct"] = st.slider(
                    "Max % per theme",
                    min_value=0.10,
                    max_value=1.0,
                    value=float(defaults["max_pct"]),
                    step=0.05,
                    key=f"bt_{rule_name}_max_pct",
                )
                params["theme_map"] = dict(theme_map or {})
                if not params["theme_map"]:
                    st.caption(
                        "No theme map passed in — rule will treat every "
                        "asset as 'Unclassified' (cap effectively inactive)."
                    )
            elif rule_name == "stop_loss":
                params["per_position_pct"] = st.slider(
                    "Trailing stop (% from peak)",
                    min_value=0.02,
                    max_value=0.50,
                    value=float(defaults["per_position_pct"]),
                    step=0.01,
                    key=f"bt_{rule_name}_pct",
                )
            elif rule_name == "momentum_entry":
                params["lookback_days"] = st.number_input(
                    "Lookback (days)",
                    min_value=5,
                    max_value=252,
                    value=int(defaults["lookback_days"]),
                    step=5,
                    key=f"bt_{rule_name}_lb",
                )
                params["threshold"] = st.slider(
                    "Momentum threshold",
                    min_value=-0.20,
                    max_value=0.50,
                    value=float(defaults["threshold"]),
                    step=0.01,
                    key=f"bt_{rule_name}_thr",
                )
            specs.append(RuleSpec(rule_name=rule_name, params=params))
    return specs


# ---------------------------------------------------------------------------
# Results
# ---------------------------------------------------------------------------
def _apply_template(fig: go.Figure) -> go.Figure:
    fig.update_layout(**PLOTLY_TEMPLATE["layout"])
    return fig


def render_backtest_results(
    baseline_nav: pd.Series,
    ruled_nav: pd.Series,
    comparison: pd.DataFrame,
    trigger_log: pd.DataFrame,
) -> None:
    """Render the headline equity overlay + KPI deltas + triggers."""
    if baseline_nav is None or baseline_nav.empty:
        st.info("No backtest result to display yet.")
        return

    # KPI strip
    kpi_cols = st.columns(4)
    try:
        sharpe_delta = float(comparison.loc["Sharpe", "delta"])
    except Exception:
        sharpe_delta = float("nan")
    try:
        mdd_delta = float(comparison.loc["Max drawdown", "delta"])
    except Exception:
        mdd_delta = float("nan")
    try:
        end_delta = float(comparison.loc["Ending NAV (EUR)", "delta"])
    except Exception:
        end_delta = float("nan")
    try:
        ret_delta = float(comparison.loc["Total return", "delta"])
    except Exception:
        ret_delta = float("nan")

    kpi_cols[0].metric("Δ Sharpe", f"{sharpe_delta:+.2f}")
    kpi_cols[1].metric("Δ Max DD", fmt_pct(mdd_delta))
    kpi_cols[2].metric("Δ Total return", fmt_pct(ret_delta))
    kpi_cols[3].metric("Δ Ending NAV", fmt_eur(end_delta))

    # Equity overlay
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=baseline_nav.index,
            y=baseline_nav.values,
            mode="lines",
            line={"color": PALETTE.fg_muted, "width": 1.5, "dash": "dot"},
            name="Baseline (no rules)",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=ruled_nav.index,
            y=ruled_nav.values,
            mode="lines",
            line={"color": PALETTE.accent, "width": 2.0},
            name="Ruled portfolio",
        )
    )
    fig.update_layout(title="Equity curve — baseline vs ruled (EUR)", yaxis_title="EUR")
    st.plotly_chart(_apply_template(fig), use_container_width=True)

    # Drawdown overlay
    dd_base = drawdown_series(baseline_nav) * 100
    dd_rule = drawdown_series(ruled_nav) * 100
    fig_dd = go.Figure()
    fig_dd.add_trace(
        go.Scatter(
            x=dd_base.index,
            y=dd_base.values,
            mode="lines",
            line={"color": PALETTE.fg_muted, "width": 1.0, "dash": "dot"},
            name="Baseline DD",
        )
    )
    fig_dd.add_trace(
        go.Scatter(
            x=dd_rule.index,
            y=dd_rule.values,
            mode="lines",
            fill="tozeroy",
            fillcolor="rgba(239, 68, 68, 0.18)",
            line={"color": PALETTE.loss, "width": 1.0},
            name="Ruled DD",
        )
    )
    fig_dd.update_layout(title="Drawdown overlay", yaxis_title="%")
    st.plotly_chart(_apply_template(fig_dd), use_container_width=True)

    # Comparison table
    st.markdown("##### Metrics comparison")
    fmt_df = comparison.copy()
    pct_rows = {"Ann. return", "Ann. vol", "Max drawdown", "VaR 95% (daily)",
                "CVaR 95% (daily)", "Total return"}
    eur_rows = {"Ending NAV (EUR)"}
    for col in ("baseline", "ruled", "delta"):
        fmt_df[col] = [
            fmt_pct(v) if (idx in pct_rows and pd.notna(v))
            else (fmt_eur(v) if (idx in eur_rows and pd.notna(v))
                  else (f"{v:+.3f}" if pd.notna(v) else "-"))
            for idx, v in zip(fmt_df.index, fmt_df[col])
        ]
    st.dataframe(fmt_df, use_container_width=True)

    # Trigger log
    st.markdown("##### Rule trigger log")
    if trigger_log is None or trigger_log.empty:
        st.caption("No rule ever fired on this window.")
    else:
        summary = trigger_log.groupby("rule").size().rename("n_triggers").to_frame()
        c1, c2 = st.columns([1, 2])
        with c1:
            st.dataframe(summary, use_container_width=True)
        with c2:
            st.dataframe(
                trigger_log.tail(50).sort_values("ts", ascending=False),
                use_container_width=True,
                hide_index=True,
            )


# ---------------------------------------------------------------------------
# Walk-forward
# ---------------------------------------------------------------------------
def render_walk_forward(wf_results: pd.DataFrame) -> None:
    """Heatmap (when 2 params present) + per-fold table."""
    if wf_results is None or wf_results.empty:
        st.info("No walk-forward result to display.")
        return

    param_cols = [
        c
        for c in wf_results.columns
        if c
        not in {
            "fold",
            "train_start",
            "test_start",
            "test_end",
            "oos_sharpe",
            "oos_max_dd",
            "oos_total_return",
            "baseline_oos_sharpe",
        }
    ]

    st.markdown("##### Walk-forward summary")
    if param_cols:
        agg = (
            wf_results.groupby(param_cols)[
                ["oos_sharpe", "oos_max_dd", "oos_total_return", "baseline_oos_sharpe"]
            ]
            .mean()
            .sort_values("oos_sharpe", ascending=False)
        )
        st.dataframe(agg.round(3), use_container_width=True)
    else:
        st.dataframe(wf_results.round(3), use_container_width=True)

    if len(param_cols) >= 2:
        rows_param, cols_param = param_cols[0], param_cols[1]
        pivot = wf_results.pivot_table(
            index=rows_param,
            columns=cols_param,
            values="oos_sharpe",
            aggfunc="mean",
        )
        fig = go.Figure(
            data=go.Heatmap(
                z=pivot.values,
                x=[str(c) for c in pivot.columns],
                y=[str(r) for r in pivot.index],
                colorscale=[
                    [0.0, PALETTE.loss],
                    [0.5, PALETTE.bg],
                    [1.0, PALETTE.bull_body],
                ],
                colorbar={"title": "OOS Sharpe"},
                text=[[f"{v:+.2f}" if pd.notna(v) else "" for v in row]
                      for row in pivot.values],
                texttemplate="%{text}",
            )
        )
        fig.update_layout(
            title=f"OOS Sharpe heatmap ({rows_param} x {cols_param})",
            xaxis_title=cols_param,
            yaxis_title=rows_param,
        )
        st.plotly_chart(_apply_template(fig), use_container_width=True)

    st.markdown("##### Per-fold breakdown")
    st.dataframe(
        wf_results.sort_values(["fold"] + param_cols).round(3),
        use_container_width=True,
        hide_index=True,
    )
