"""Streamlit render blocks for the Decision Support tab.

Each ``render_*`` accepts already-computed data (DataFrames or pydantic
models); fetches happen in ``app.py``.

Widget keys are namespaced with ``decision_`` to avoid Streamlit
DuplicateWidgetID errors when other tabs render similar forms.
"""
from __future__ import annotations

from datetime import date
from typing import Any

import numpy as np
import pandas as pd
import streamlit as st

from src.common.schemas import CollarQuote, JournalEntry, JournalMilestone
from src.decision.journal_store import write_journal
from src.viz.theme import PALETTE, fmt_eur, fmt_pct


def _fmt_eur(v: float | None) -> str:
    if v is None or (isinstance(v, float) and (np.isnan(v) or not np.isfinite(v))):
        return "n/a"
    return fmt_eur(float(v))


def _fmt_pct(v: float | None, decimals: int = 2) -> str:
    if v is None or (isinstance(v, float) and (np.isnan(v) or not np.isfinite(v))):
        return "n/a"
    return fmt_pct(float(v), decimals=decimals)


# ---------------------------------------------------------------------------
# Conviction matrix
# ---------------------------------------------------------------------------
def render_conviction_matrix(scores_df: pd.DataFrame) -> None:
    """Render the per-position conviction matrix.

    Expected columns: ticker, thesis_quality, downside, liquidity,
    catalyst_proximity, composite, grade, rationale,
    optionally current_weight, target_weight, delta.
    """
    st.subheader("Conviction matrix")
    if scores_df is None or scores_df.empty:
        st.info("No conviction scores yet — fetch dilution/runway/liquidity first.")
        return

    shown = scores_df.copy()
    for col, fn in (
        ("current_weight", lambda v: _fmt_pct(v, decimals=1)),
        ("target_weight", lambda v: _fmt_pct(v, decimals=1)),
        ("delta", lambda v: _fmt_pct(v, decimals=2)),
    ):
        if col in shown.columns:
            shown[col + "_fmt"] = shown[col].apply(fn)

    display_cols = ["ticker", "grade", "composite", "thesis_quality",
                    "downside", "liquidity", "catalyst_proximity"]
    for c in ("current_weight_fmt", "target_weight_fmt", "delta_fmt", "rationale"):
        if c in shown.columns:
            display_cols.append(c)
    display_cols = [c for c in display_cols if c in shown.columns]

    rename = {
        "current_weight_fmt": "current",
        "target_weight_fmt": "target",
        "delta_fmt": "Δ",
        "thesis_quality": "thesis",
        "catalyst_proximity": "catalyst",
    }
    st.dataframe(
        shown[display_cols].rename(columns=rename),
        use_container_width=True, hide_index=True,
    )
    st.caption(
        "Composite is a weighted mean (1-5). Each axis: 5 = best.  "
        "Suggested weights use Kelly/4 capped at max_single_position_pct."
    )
    # Explain WHY axes are low — most of the time it's missing data, not a
    # genuine weak score. The rationale column already says e.g.
    # "no journal entry" / "no liquidity data" / "no catalyst on calendar".
    with st.expander("ℹ️ What feeds each axis (and how to boost a low score)"):
        st.markdown(
            """
            | Axis            | Data source                     | How to lift a low score |
            |-----------------|---------------------------------|--------------------------|
            | **thesis**      | `src.decision.journal_store`    | Add a thesis entry from **Decision Support → Thesis Journal** |
            | **downside**    | dilution + runway risk          | Verify SEC filings via **Smart-Money → Dilution / Cash runway** |
            | **liquidity**   | ADV + spread + borrow           | Loads automatically; needs an Alpaca chain / yfinance volume |
            | **catalyst**    | events on the next ~30 days     | Wait for one or import via **Catalysts → Catalyst Calendar** |

            A score of **1** with rationale `no X` usually means the data source returned empty — not that the position scored poorly. Fill the missing input and the axis lifts.
            """
        )


# ---------------------------------------------------------------------------
# VaR-contribution sizing
# ---------------------------------------------------------------------------
def render_var_sizing(suggestion_df: pd.DataFrame) -> None:
    st.subheader("VaR-contribution trim suggestions")
    if suggestion_df is None or suggestion_df.empty:
        st.info("Run var_contribution_sizing(portfolio, returns, theme=..., target_theme_pct=...).")
        return

    shown = suggestion_df.copy()
    shown["weight"] = shown["weight_eur"].apply(_fmt_eur)
    shown["VaR contrib"] = shown["contrib_pct_of_portfolio_var"].apply(lambda v: _fmt_pct(v, 1))
    shown["trim (EUR)"] = shown["suggested_trim_eur"].apply(_fmt_eur)
    shown["new weight"] = shown["suggested_weight_eur"].apply(_fmt_eur)
    shown["in theme?"] = shown["in_theme"].map({True: "yes", False: ""})

    cols = ["ticker", "theme", "in theme?", "weight", "VaR contrib",
            "trim (EUR)", "new weight", "rationale"]
    cols = [c for c in cols if c in shown.columns]
    st.dataframe(shown[cols], use_container_width=True, hide_index=True)


# ---------------------------------------------------------------------------
# Risk-parity preview
# ---------------------------------------------------------------------------
def render_risk_parity_preview(
    current_w: pd.Series, parity_w: pd.Series, *, title: str = "Vol-parity preview",
) -> None:
    st.subheader(title)
    if (current_w is None or current_w.empty) and (parity_w is None or parity_w.empty):
        st.info("No weights to compare — load portfolio + returns first.")
        return

    cur = (current_w if current_w is not None else pd.Series(dtype=float)).rename("current")
    par = (parity_w if parity_w is not None else pd.Series(dtype=float)).rename("vol_parity")
    combined = pd.concat([cur, par], axis=1).fillna(0.0)
    combined["delta"] = combined["vol_parity"] - combined["current"]
    combined = combined.sort_values("vol_parity", ascending=False)

    try:
        import plotly.graph_objects as go
        from src.viz.theme import PLOTLY_TEMPLATE
        fig = go.Figure()
        fig.add_bar(name="current", x=combined.index, y=combined["current"], marker_color=PALETTE.fg_muted)
        fig.add_bar(
            name="vol-parity", x=combined.index, y=combined["vol_parity"],
            marker_color=PALETTE.accent,
        )
        fig.update_layout(
            template=PLOTLY_TEMPLATE,
            barmode="group",
            yaxis_tickformat=".1%",
            height=320,
            title="Current vs vol-parity weights",
        )
        st.plotly_chart(fig, use_container_width=True, key="decision_riskparity_bars")
    except Exception:
        # Plotly missing or fails -> dataframe fallback
        st.dataframe(combined.map(lambda v: _fmt_pct(v, 2)), use_container_width=True)

    st.caption(
        "Vol-parity weights target the same daily-vol contribution per position. "
        "Bigger ‘vol_parity’ than ‘current’ -> consider adding; smaller -> consider trimming."
    )


# ---------------------------------------------------------------------------
# Journal editor + summary
# ---------------------------------------------------------------------------
def _milestones_to_df(entry: JournalEntry | None) -> pd.DataFrame:
    if entry is None or not entry.milestones:
        return pd.DataFrame({"date": [], "label": [], "hit": [], "weight": []})
    return pd.DataFrame([
        {"date": m.date, "label": m.label, "hit": bool(m.hit), "weight": float(m.weight)}
        for m in entry.milestones
    ])


def render_journal_editor(entry: JournalEntry | None, ticker: str) -> None:
    """Streamlit form to read / write the thesis YAML for one ticker."""
    t = (ticker or "").upper().strip()
    st.subheader(f"Thesis journal — {t or '?'}")
    if not t:
        st.info("Pick a ticker to edit its thesis.")
        return

    e = entry or JournalEntry(ticker=t)

    with st.form(key=f"decision_journal_{t}", clear_on_submit=False):
        c1, c2 = st.columns(2)
        with c1:
            thesis = st.text_area(
                "Thesis", value=e.thesis or "", height=120,
                key=f"decision_journal_{t}_thesis",
            )
            entry_rationale = st.text_area(
                "Entry rationale", value=e.entry_rationale or "", height=90,
                key=f"decision_journal_{t}_rationale",
            )
            pre_mortem = st.text_area(
                "Pre-mortem", value=e.pre_mortem or "", height=120,
                key=f"decision_journal_{t}_pm",
            )
        with c2:
            entry_price = st.number_input(
                "Entry price (EUR)",
                value=float(e.entry_price_eur or 0.0), min_value=0.0, step=0.01,
                key=f"decision_journal_{t}_entry_px",
            )
            price_target = st.number_input(
                "Price target (EUR)",
                value=float(e.price_target_eur or 0.0), min_value=0.0, step=0.01,
                key=f"decision_journal_{t}_target_px",
            )
            stop_thesis = st.number_input(
                "Stop-loss (thesis cassée, EUR)",
                value=float(e.stop_loss_thesis_eur or 0.0), min_value=0.0, step=0.01,
                key=f"decision_journal_{t}_stop_thesis",
            )
            stop_tech = st.number_input(
                "Stop-loss (technique, EUR)",
                value=float(e.stop_loss_technical_eur or 0.0), min_value=0.0, step=0.01,
                key=f"decision_journal_{t}_stop_tech",
            )
            target_pct = st.number_input(
                "Position target (% of book)",
                value=float(e.position_target_pct or 0.0) * 100.0,
                min_value=0.0, max_value=100.0, step=0.5,
                key=f"decision_journal_{t}_target_pct",
            )

        st.markdown("**Milestones**  (date label hit weight)")
        ms_df = st.data_editor(
            _milestones_to_df(e),
            num_rows="dynamic",
            use_container_width=True,
            key=f"decision_journal_{t}_milestones",
        )

        submitted = st.form_submit_button("Save thesis", type="primary")
        if submitted:
            milestones: list[JournalMilestone] = []
            for _, row in ms_df.iterrows():
                if not str(row.get("label", "")).strip():
                    continue
                try:
                    milestones.append(JournalMilestone(
                        date=str(row.get("date", "")).strip(),
                        label=str(row.get("label", "")).strip(),
                        hit=bool(row.get("hit", False)),
                        weight=float(row.get("weight", 1.0) or 1.0),
                    ))
                except Exception:
                    continue
            new_entry = JournalEntry(
                ticker=t,
                thesis=str(thesis).strip(),
                entry_rationale=str(entry_rationale).strip(),
                pre_mortem=str(pre_mortem).strip(),
                entry_price_eur=float(entry_price) or None,
                price_target_eur=float(price_target) or None,
                stop_loss_thesis_eur=float(stop_thesis) or None,
                stop_loss_technical_eur=float(stop_tech) or None,
                position_target_pct=(float(target_pct) / 100.0) if target_pct else None,
                milestones=milestones,
                entry_date=e.entry_date or date.today(),
                last_updated=date.today(),
                catalyst_event_ids=e.catalyst_event_ids,
                re_rating_triggers=e.re_rating_triggers,
            )
            path = write_journal(new_entry)
            st.success(f"Saved {path.name}")


def render_journal_summary(journals_df: pd.DataFrame) -> None:
    st.subheader("Thesis journals — overview")
    if journals_df is None or journals_df.empty:
        st.info("No journals on disk yet. Use the editor above to create one.")
        return
    shown = journals_df.copy()
    if "entry_price_eur" in shown.columns:
        shown["entry_price_eur"] = shown["entry_price_eur"].apply(_fmt_eur)
    if "price_target_eur" in shown.columns:
        shown["price_target_eur"] = shown["price_target_eur"].apply(_fmt_eur)
    if "stop_loss_thesis_eur" in shown.columns:
        shown["stop_loss_thesis_eur"] = shown["stop_loss_thesis_eur"].apply(_fmt_eur)
    if "has_pre_mortem" in shown.columns:
        shown["pre-mortem?"] = shown["has_pre_mortem"].map({True: "yes", False: "—"})
        shown = shown.drop(columns=["has_pre_mortem"])
    st.dataframe(shown, use_container_width=True, hide_index=True)


# ---------------------------------------------------------------------------
# Rerating dashboard
# ---------------------------------------------------------------------------
def render_rerating_dashboard(rerating_rows: pd.DataFrame) -> None:
    st.subheader("Re-rating progress")
    if rerating_rows is None or rerating_rows.empty:
        st.info("Compute compute_rerating_score(entry, spot) for each journal entry.")
        return
    shown = rerating_rows.copy()
    if "score" in shown.columns:
        shown["score"] = shown["score"].apply(lambda v: f"{v:.0f}/100" if pd.notna(v) else "n/a")
    for c in ("price_progress_pct", "milestones_hit_pct"):
        if c in shown.columns:
            shown[c] = shown[c].apply(lambda v: f"{v:.0f}%" if pd.notna(v) else "n/a")
    if "days_since_entry" in shown.columns:
        shown["days_since_entry"] = shown["days_since_entry"].apply(
            lambda v: f"{int(v)}d" if pd.notna(v) else "n/a"
        )
    rename = {
        "price_progress_pct": "price progress",
        "milestones_hit_pct": "milestones",
        "days_since_entry": "age",
        "recommendation": "action",
    }
    st.dataframe(shown.rename(columns=rename), use_container_width=True, hide_index=True)
    st.caption("score = 0.4·price + 0.4·milestones + 0.2·time-efficacy.")


# ---------------------------------------------------------------------------
# Hedge cost
# ---------------------------------------------------------------------------
def render_hedge_cost(collar: CollarQuote | None, alt_suggestions: list[dict[str, Any]] | None) -> None:
    st.subheader("Hedge cost")
    if collar is None:
        # Better diagnostic — most common causes spelled out so the user knows
        # where to look (chain unavailable vs. expiry too thin vs. ticker
        # without options listed).
        st.markdown(
            f"""
            <div style="background:{PALETTE.card};border:1px solid {PALETTE.warning}55;
                        border-left:4px solid {PALETTE.warning};border-radius:10px;
                        padding:14px 16px;margin-bottom:10px;">
                <div style="font-weight:600;color:{PALETTE.warning};
                            font-size:0.95rem;">⚠ Collar quote unavailable</div>
                <div style="margin-top:6px;font-size:0.85rem;color:{PALETTE.fg};
                            line-height:1.55;">
                    The collar pricer needs an OTM put + OTM call at the same expiry, on a
                    chain with usable mid prices. Common causes:
                </div>
                <ul style="margin-top:6px;font-size:0.82rem;color:{PALETTE.fg_muted};
                            padding-left:20px;line-height:1.6;">
                    <li>Underlying has no options listed (small-cap, foreign ETF on .L/.PA exchanges)</li>
                    <li>Alpaca returned a chain without OI/quotes → yfinance fallback failed</li>
                    <li>Target tenor (90d default) has no liquid strikes at the requested OTM %</li>
                    <li>The ticker symbol used here differs from the option underlying on Alpaca</li>
                </ul>
                <div style="margin-top:6px;font-size:0.82rem;color:{PALETTE.fg_dim};">
                    See the linear alternatives below for vanilla / future-based hedges
                    when the option market is too thin.
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    else:
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Underlying", _fmt_eur(collar.underlying_px_eur, ))
        c2.metric("Net premium",
                  _fmt_eur(collar.net_premium_eur),
                  delta=_fmt_pct(collar.cost_pct_notional, 2),
                  delta_color="inverse")
        c3.metric("Max loss", _fmt_eur(collar.max_loss_eur))
        c4.metric("Max gain", _fmt_eur(collar.max_gain_eur))

        st.markdown(
            f"""
            <div style="background:{PALETTE.card};border:1px solid {PALETTE.border};
                        border-radius:8px;padding:14px 18px;margin-top:6px;">
              <div><b>Expiry:</b> {collar.expiry.isoformat()}</div>
              <div><b>Long put:</b> strike {collar.long_put_strike:.2f}</div>
              <div><b>Short call:</b> strike {collar.short_call_strike:.2f}</div>
              <div><b>Breakeven:</b> {collar.breakeven_low:.2f} – {collar.breakeven_high:.2f}</div>
              <div style="color:{PALETTE.fg_muted};margin-top:6px;">{collar.notes}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    if alt_suggestions:
        st.markdown("**Linear / vanilla alternatives**")
        df_alt = pd.DataFrame(alt_suggestions)
        st.dataframe(df_alt, use_container_width=True, hide_index=True)
    elif collar is None:
        st.markdown(
            f"""
            <div style="background:{PALETTE.card};border:1px dashed {PALETTE.border_strong};
                        border-radius:10px;padding:14px 16px;margin-top:6px;">
                <div style="font-weight:600;color:{PALETTE.fg};">
                    No linear alternative mapped for this ticker
                </div>
                <div style="font-size:0.82rem;color:{PALETTE.fg_muted};margin-top:6px;
                            line-height:1.5;">
                    Add this ticker's hedge basket under
                    <code style="color:{PALETTE.accent_alt};">
                    config/hedge_defaults.yaml → linear_alternatives</code>.
                    The repo ships defaults for SPY · QQQ · GOOG · AAPL · TSLA · CCJ · IONQ ·
                    ASTS · RKLB · RDW · AAOI · QS · ONDS — extend with your own.
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
