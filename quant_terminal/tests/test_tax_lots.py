"""Tests for the tax lots module (Feature 5b)."""
from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from src.tax import lots as taxlots


@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch):
    monkeypatch.setattr(taxlots, "_DIR", tmp_path)
    monkeypatch.setattr(taxlots, "_LOTS_FILE", tmp_path / "lots.parquet")
    monkeypatch.setattr(taxlots, "_REALISED_FILE", tmp_path / "realised.parquet")
    yield


def test_add_lot_persists_with_eur_cost():
    lot = taxlots.add_lot("GOOG", qty=10, acquired_at=date(2024, 1, 1),
                          price_local=140.0, currency="USD", fx_rate_eur=1.10)
    assert lot.qty == 10
    assert lot.cost_eur == pytest.approx(10 * 140 / 1.10, rel=1e-6)
    df = taxlots.list_lots(open_only=True)
    assert len(df) == 1
    assert df.iloc[0]["ticker"] == "GOOG"


def test_fifo_partial_consumption():
    taxlots.add_lot("GOOG", 10, date(2024, 1, 1), price_local=100, fx_rate_eur=1.0)
    taxlots.add_lot("GOOG", 5,  date(2024, 6, 1), price_local=120, fx_rate_eur=1.0)
    trade = taxlots.record_sale("GOOG", qty_sold=7, sold_at=date(2025, 1, 1),
                                  sale_price_local=150, sale_fx_rate_eur=1.0,
                                  sale_currency="USD")
    assert trade is not None
    # Cost basis: 7 × 100 = 700; proceeds 7 × 150 = 1050 → PnL 350
    assert trade.cost_basis_eur == pytest.approx(700.0)
    assert trade.sale_proceeds_eur == pytest.approx(1050.0)
    assert trade.realised_pnl_eur == pytest.approx(350.0)
    # Remaining: oldest lot has 3 left, second lot still has 5
    remaining = taxlots.list_lots(open_only=True)
    qty_sorted = remaining.sort_values("acquired_at")["qty"].tolist()
    assert qty_sorted == [3.0, 5.0]


def test_fifo_spans_two_lots():
    taxlots.add_lot("ASTS", 4, date(2024, 1, 1), price_local=20, fx_rate_eur=1.0)
    taxlots.add_lot("ASTS", 6, date(2024, 6, 1), price_local=30, fx_rate_eur=1.0)
    trade = taxlots.record_sale("ASTS", qty_sold=8, sold_at=date(2025, 1, 1),
                                  sale_price_local=40, sale_fx_rate_eur=1.0,
                                  sale_currency="USD")
    assert trade is not None
    # Consumes 4 × 20 + 4 × 30 = 200; proceeds 8 × 40 = 320 → PnL 120
    assert trade.cost_basis_eur == pytest.approx(200.0)
    assert trade.realised_pnl_eur == pytest.approx(120.0)
    assert len(trade.consumed_lots) == 2


def test_no_open_lots_returns_none():
    rec = taxlots.record_sale("XXX", 1, date(2025, 1, 1), 10.0)
    assert rec is None


def test_annual_summary_aggregates():
    taxlots.add_lot("GOOG", 5, date(2024, 1, 1), price_local=100, fx_rate_eur=1.0)
    taxlots.record_sale("GOOG", 5, date(2025, 6, 1), sale_price_local=120,
                          sale_currency="USD", sale_fx_rate_eur=1.0)
    summary = taxlots.annual_realised(year=2025)
    assert not summary.empty
    assert summary.iloc[0]["n_sales"] == 1
    assert summary.iloc[0]["realised_pnl_eur"] == pytest.approx(100.0)
    assert summary.iloc[0]["tax_pfu_30pct_eur"] == pytest.approx(30.0)
