"""Streamlit renderers for the Tax tab."""
from __future__ import annotations

from datetime import date

import pandas as pd
import streamlit as st

from src.tax.importer import import_csv
from src.tax.lots import (
    add_lot,
    annual_realised,
    list_lots,
    list_realised,
    record_sale,
)
from src.viz.theme import PALETTE, fmt_eur


def render_lots_table() -> None:
    df = list_lots(open_only=True)
    if df.empty:
        st.info("Aucun lot ouvert. Importer un CSV ou ajouter manuellement.")
        return
    show = df.copy()
    if "acquired_at" in show.columns:
        show["acquired_at"] = pd.to_datetime(show["acquired_at"]).dt.date.astype(str)
    show = show[[c for c in ["ticker", "qty", "qty_initial", "acquired_at",
                              "price_local", "currency", "fx_rate_eur", "cost_eur",
                              "account"] if c in show.columns]]
    show["cost_eur"] = show["cost_eur"].round(2)
    st.dataframe(show.sort_values(["ticker", "acquired_at"]),
                 use_container_width=True, hide_index=True)


def render_realised_table() -> None:
    df = list_realised()
    if df.empty:
        st.info("Aucune vente réalisée enregistrée.")
        return
    show = df.copy()
    show["sold_at"] = pd.to_datetime(show["sold_at"]).dt.date.astype(str)
    keep = [c for c in ["ticker", "sold_at", "qty_sold",
                         "sale_proceeds_eur", "cost_basis_eur",
                         "realised_pnl_eur", "holding_period_days", "account"]
            if c in show.columns]
    show = show[keep]
    for col in ["sale_proceeds_eur", "cost_basis_eur", "realised_pnl_eur"]:
        if col in show.columns:
            show[col] = show[col].round(2)
    st.dataframe(show.sort_values("sold_at", ascending=False),
                 use_container_width=True, hide_index=True)


def render_annual_summary() -> None:
    df = annual_realised()
    if df.empty:
        st.info("Pas encore de PnL réalisé.")
        return
    show = df.copy()
    for col in ["proceeds_eur", "cost_basis_eur", "realised_pnl_eur", "tax_pfu_30pct_eur"]:
        if col in show.columns:
            show[col] = show[col].round(2)
    st.dataframe(show, use_container_width=True, hide_index=True)
    # KPI strip — current year
    cur_year = pd.Timestamp.utcnow().year
    cur = df[df["year"] == cur_year]
    if not cur.empty:
        cols = st.columns(4)
        cols[0].metric("Ventes YTD", int(cur["n_sales"].iloc[0]))
        cols[1].metric("Plus-values nettes",
                       fmt_eur(float(cur["realised_pnl_eur"].iloc[0])))
        cols[2].metric("PFU 30% estimé",
                       fmt_eur(float(cur["tax_pfu_30pct_eur"].iloc[0])))
        cols[3].metric("À déclarer (2074-CMV)",
                       fmt_eur(float(cur["realised_pnl_eur"].iloc[0])))


def render_lot_manual_form() -> None:
    st.markdown("### Ajouter un lot manuellement")
    with st.form("tax_add_lot_form"):
        cols = st.columns(6)
        ticker = cols[0].text_input("Ticker", "").upper()
        qty = cols[1].number_input("Qty", min_value=0.0, value=1.0, step=1.0)
        acq = cols[2].date_input("Date d'achat", value=date.today())
        price = cols[3].number_input("Prix local", min_value=0.0, value=0.0, step=0.01)
        ccy = cols[4].selectbox("Devise", ["USD", "EUR", "CAD", "GBP", "GBp"])
        fx = cols[5].number_input("FX rate (1 EUR = X ccy)", min_value=0.0, value=1.10, step=0.01)
        account = st.selectbox("Compte", ["CTO", "PEA", "Alpaca", "IBKR", "Other"])
        submitted = st.form_submit_button("➕ Ajouter le lot")
    if submitted and ticker and qty > 0:
        add_lot(ticker, qty, acq, price, ccy, fx, account=account)
        st.success(f"Lot ajouté : {ticker} × {qty} @ {price} {ccy}")


def render_sale_manual_form() -> None:
    st.markdown("### Enregistrer une vente (FIFO matching automatique)")
    with st.form("tax_record_sale_form"):
        cols = st.columns(6)
        ticker = cols[0].text_input("Ticker", "", key="tax_sale_ticker").upper()
        qty = cols[1].number_input("Qty vendue", min_value=0.0, value=1.0, step=1.0)
        sold = cols[2].date_input("Date vente", value=date.today())
        price = cols[3].number_input("Prix vente local", min_value=0.0, value=0.0, step=0.01)
        ccy = cols[4].selectbox("Devise vente", ["USD", "EUR", "CAD", "GBP", "GBp"],
                                 key="tax_sale_ccy")
        fx = cols[5].number_input("FX rate vente", min_value=0.0, value=1.10, step=0.01,
                                    key="tax_sale_fx")
        account = st.selectbox("Compte", ["CTO", "PEA", "Alpaca", "IBKR", "Other"],
                                key="tax_sale_account")
        submitted = st.form_submit_button("💰 Enregistrer la vente")
    if submitted and ticker and qty > 0:
        trade = record_sale(ticker, qty, sold, price, ccy, fx, account=account)
        if trade is None:
            st.error("Aucun lot ouvert pour ce ticker.")
        else:
            color = PALETTE.profit if trade.realised_pnl_eur >= 0 else PALETTE.loss
            st.markdown(
                f"<div style='color:{color};font-weight:600'>"
                f"PnL réalisé : {fmt_eur(trade.realised_pnl_eur, 2)} EUR"
                f" (cost {fmt_eur(trade.cost_basis_eur)} → proceeds {fmt_eur(trade.sale_proceeds_eur)})"
                "</div>", unsafe_allow_html=True,
            )


def render_csv_import() -> None:
    st.markdown("### Import CSV / Excel")
    uploaded = st.file_uploader(
        "Transactions (BUY + SELL) — colonnes attendues : date · ticker · qty · price_local · currency · fx_rate_eur · side · account",
        type=["csv", "xlsx", "xls"],
        key="tax_csv_uploader",
    )
    if uploaded is not None:
        try:
            buys, sells = import_csv(uploaded)
            st.success(f"Import OK : {buys} BUY, {sells} SELL")
        except Exception as exc:
            st.error(f"Import échoué : {exc}")
