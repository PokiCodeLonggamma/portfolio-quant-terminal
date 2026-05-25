"""Streamlit renderers for the 📡 Execution tab."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from src.common.schemas import BrokerAccount
from src.viz.theme import PALETTE


def render_mode_banner(mode: str) -> None:
    if mode == "live":
        st.markdown(
            f"<div style='padding:10px;border-radius:8px;background:rgba(239,68,68,0.15);"
            f"border:1px solid {PALETTE.loss};color:{PALETTE.loss};font-weight:600'>"
            "🚨 LIVE MODE · les ordres affectent un compte réel."
            "</div>",
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            f"<div style='padding:10px;border-radius:8px;background:rgba(34,197,94,0.10);"
            f"border:1px solid {PALETTE.profit};color:{PALETTE.profit};font-weight:600'>"
            "🧪 PAPER MODE · simulation Alpaca paper, aucun ordre réel."
            "</div>",
            unsafe_allow_html=True,
        )


def render_account_summary(account: BrokerAccount | None) -> None:
    if account is None:
        st.warning("Compte Alpaca indisponible (credentials manquantes ou erreur réseau).")
        return
    cols = st.columns(5)
    cols[0].metric("Cash (USD)", f"${account.cash_usd:,.0f}")
    cols[1].metric("Buying power (USD)", f"${account.buying_power_usd:,.0f}")
    cols[2].metric("Portfolio value (USD)", f"${account.portfolio_value_usd:,.0f}")
    cols[3].metric("Day-trade count", f"{account.daytrade_count}")
    cols[4].metric(
        "Status",
        account.status,
        delta="PDT" if account.pattern_day_trader else None,
        delta_color="off" if not account.pattern_day_trader else "normal",
    )


def render_open_orders_table(df: pd.DataFrame, on_cancel) -> None:
    if df is None or df.empty:
        st.info("Aucun ordre ouvert.")
        return
    keep = [c for c in ["order_id", "ticker", "side", "qty", "asset_class",
                         "order_type", "limit_price", "status", "submitted_at",
                         "broker_order_id"] if c in df.columns]
    st.dataframe(df[keep], use_container_width=True, hide_index=True)
    st.markdown("##### Cancel an order")
    cancel_id = st.selectbox(
        "Broker order ID",
        df["broker_order_id"].dropna().tolist() if "broker_order_id" in df.columns else [],
        key="exec_cancel_select",
    )
    if cancel_id and st.button("❌ Cancel", type="secondary", key="exec_cancel_btn"):
        if on_cancel(cancel_id):
            st.success(f"Cancel sent for {cancel_id}.")
        else:
            st.error("Cancel failed.")


def render_reconciliation(rec_df: pd.DataFrame) -> None:
    if rec_df is None or rec_df.empty:
        st.info("Pas de réconciliation à afficher (charger DEGIRO + connecter Alpaca).")
        return
    # Color status column with quick highlight by row
    def _row_color(status: str) -> str:
        return {
            "match":           PALETTE.profit,
            "qty_mismatch":    PALETTE.warning,
            "broker_missing":  PALETTE.fg_muted,
            "internal_missing":PALETTE.warning,
        }.get(status, PALETTE.fg)
    show = rec_df.copy()
    if "status" in show.columns:
        show["status_dot"] = show["status"].map(
            lambda s: f"<span style='color:{_row_color(s)};font-weight:600'>● {s}</span>"
        )
    st.dataframe(show, use_container_width=True, hide_index=True)
    mismatch_n = int((rec_df["status"] != "match").sum()) if "status" in rec_df.columns else 0
    if mismatch_n:
        st.warning(f"{mismatch_n} ligne(s) en désaccord broker / interne.")
    else:
        st.success("Broker et interne parfaitement réconciliés.")


def render_submit_form(default_ticker: str, default_side: str = "BUY",
                       default_qty: int = 1, on_submit=None) -> None:
    """Generic submit form (manual ticket — independent of the options Δ25 finder)."""
    st.markdown("### Manual order ticket")
    with st.form(key="exec_manual_ticket"):
        cols = st.columns(5)
        ticker = cols[0].text_input("Ticker", value=default_ticker, key="exec_ticker").upper()
        side = cols[1].selectbox("Side", ["BUY", "SELL"],
                                  index=0 if default_side == "BUY" else 1, key="exec_side")
        qty = cols[2].number_input("Qty", min_value=1, value=int(default_qty), step=1, key="exec_qty")
        order_type = cols[3].selectbox("Type", ["market", "limit"], key="exec_order_type")
        limit_price = cols[4].number_input(
            "Limit price", min_value=0.0, value=0.0, step=0.01, key="exec_limit_px",
            disabled=(order_type == "market"),
        )
        asset_class = st.selectbox(
            "Asset class", ["stock", "option"], key="exec_asset_class",
            help="For options, also fill the OCC contract symbol below.",
        )
        contract_symbol = st.text_input(
            "Contract symbol (OCC, options only)",
            value="", key="exec_contract_symbol",
            disabled=(asset_class != "option"),
        )
        confirm = st.checkbox(
            "Je confirme cet ordre (paper mode)",
            value=False, key="exec_confirm_box",
        )
        submitted = st.form_submit_button("📡 Submit to broker", type="primary")

    if not submitted:
        return
    if not confirm:
        st.error("Confirmation requise (case à cocher).")
        return
    if on_submit is None:
        st.warning("Pas de handler câblé.")
        return
    payload = {
        "ticker": ticker,
        "qty": int(qty),
        "side": side,
        "asset_class": asset_class,
        "order_type": order_type,
        "limit_price": float(limit_price) if order_type == "limit" else None,
        "contract_symbol": contract_symbol.strip() or None,
    }
    on_submit(payload)


def render_audit_log(tail: int = 50) -> None:
    from src.utils.config import PROJECT_ROOT
    log_path = PROJECT_ROOT / "data" / "execution" / "audit.log"
    if not log_path.exists():
        st.caption("Aucun audit log encore.")
        return
    try:
        lines = log_path.read_text(encoding="utf-8").splitlines()[-tail:][::-1]
    except Exception as exc:
        st.warning(f"audit log read error: {exc}")
        return
    st.code("\n".join(lines) or "(empty)", language="text")
