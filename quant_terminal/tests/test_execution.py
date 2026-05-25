"""Tests for the execution / OMS layer (Feature 1)."""
from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock

import pandas as pd
import pytest

from src.common.schemas import (
    BrokerAccount,
    BrokerPosition,
    OrderRecord,
    OrderRequest,
)
from src.execution import oms as exec_oms
from src.execution import validators
from src.execution.modes import resolve_mode
from src.execution.positions import reconcile
from src.portfolio.holdings import Portfolio


@pytest.fixture(autouse=True)
def _isolate_oms(tmp_path, monkeypatch):
    """Redirect OMS parquet + audit + validator orders read to tmp."""
    monkeypatch.setattr(exec_oms, "_DIR", tmp_path)
    monkeypatch.setattr(exec_oms, "_ORDERS_FILE", tmp_path / "orders.parquet")
    monkeypatch.setattr(exec_oms, "_AUDIT_FILE", tmp_path / "audit.log")
    monkeypatch.setattr(validators, "_ORDERS_FILE", tmp_path / "orders.parquet")
    yield


# ---------------------------------------------------------------------------
# Modes
# ---------------------------------------------------------------------------
def test_resolve_mode_defaults_to_paper(monkeypatch):
    monkeypatch.delenv("EXECUTION_ALLOW_LIVE", raising=False)
    assert resolve_mode() == "paper"


def test_resolve_mode_stays_paper_when_only_one_guard(monkeypatch):
    monkeypatch.setenv("EXECUTION_ALLOW_LIVE", "1")
    # APCA_API_BASE_URL still points to paper from .env
    assert resolve_mode() == "paper"


# ---------------------------------------------------------------------------
# Validators
# ---------------------------------------------------------------------------
def _req(**overrides) -> OrderRequest:
    base = dict(
        ticker="ASTS", qty=10, side="BUY",
        asset_class="stock", order_type="limit", limit_price=50.0,
        mode="paper",
    )
    base.update(overrides)
    return OrderRequest(**base)


def test_validate_negative_qty_refused():
    req = _req(qty=0)
    reasons = validators.validate(req)
    assert any("qty must be positive" in r for r in reasons)


def test_validate_limit_without_price_refused():
    req = _req(limit_price=0.0)
    reasons = validators.validate(req)
    assert any("limit order requires" in r for r in reasons)


def test_validate_fat_finger_refused():
    req = _req(qty=5_000)
    reasons = validators.validate(req)
    assert any("fat-finger" in r for r in reasons)


def test_validate_single_notional_cap():
    req = _req(qty=200, limit_price=50.0)  # 200×50 = 10_000 USD > 2000 cap
    reasons = validators.validate(req)
    assert any("single-order notional" in r for r in reasons)


def test_validate_passes_when_within_limits():
    req = _req(qty=10, limit_price=30.0)   # 300 USD < single cap 2000
    account = BrokerAccount(
        mode="paper", cash_usd=100_000, buying_power_usd=100_000,
        portfolio_value_usd=200_000,
    )
    reasons = validators.validate(req, account=account)
    assert reasons == []


def test_validate_option_requires_contract_symbol():
    req = _req(asset_class="option", contract_symbol=None)
    reasons = validators.validate(req)
    assert any("contract_symbol" in r for r in reasons)


def test_validate_buy_blocked_by_buying_power():
    req = _req(qty=10, limit_price=30.0)
    account = BrokerAccount(
        mode="paper", cash_usd=0, buying_power_usd=50,
        portfolio_value_usd=100,
    )
    reasons = validators.validate(req, account=account)
    assert any("buying power" in r for r in reasons)


# ---------------------------------------------------------------------------
# OMS persistence
# ---------------------------------------------------------------------------
def test_persist_and_list():
    rec = OrderRecord(
        order_id="abc",
        broker_order_id="xyz",
        status="submitted",
        request=_req(),
        submitted_at=datetime.utcnow(),
    )
    exec_oms.persist(rec)
    open_df = exec_oms.list_open()
    assert len(open_df) == 1
    assert open_df.iloc[0]["order_id"] == "abc"
    assert open_df.iloc[0]["status"] == "submitted"


def test_submit_refuses_via_validators_without_calling_broker():
    bad_req = _req(qty=0)
    # Broker mock that would fail the test if called
    broker = MagicMock()
    broker.submit_order = MagicMock(side_effect=AssertionError("broker should not be called"))
    rec = exec_oms.submit(bad_req, broker=broker)
    assert rec.status == "rejected"
    assert "qty must be positive" in (rec.error or "")
    broker.submit_order.assert_not_called()


def test_submit_calls_broker_when_validators_pass():
    good_req = _req(qty=5, limit_price=30.0)
    broker = MagicMock()
    broker.submit_order = MagicMock(return_value=OrderRecord(
        order_id="server-id",
        broker_order_id="bid-1",
        status="submitted",
        request=good_req,
        submitted_at=datetime.utcnow(),
    ))
    rec = exec_oms.submit(good_req, broker=broker)
    assert rec.status == "submitted"
    broker.submit_order.assert_called_once()


# ---------------------------------------------------------------------------
# Reconciliation
# ---------------------------------------------------------------------------
def test_reconcile_match_and_mismatch():
    internal = Portfolio(holdings=pd.DataFrame({
        "symbol": ["GOOG", "CCJ"],
        "name": ["Alphabet C", "Cameco"],
        "quantity": [4, 30],
        "value_eur": [1_300.0, 720.0],
        "currency": ["USD", "USD"],
    }))
    broker_pos = [
        BrokerPosition(symbol="GOOG", asset_class="stock", qty=4.0,
                       avg_entry_price=370.0, market_value_usd=1480.0,
                       unrealized_pl_usd=20.0),
        BrokerPosition(symbol="CCJ", asset_class="stock", qty=25.0,   # qty mismatch
                       avg_entry_price=28.0, market_value_usd=700.0,
                       unrealized_pl_usd=-20.0),
        BrokerPosition(symbol="TSLA", asset_class="stock", qty=2.0,   # broker-only
                       avg_entry_price=180.0, market_value_usd=360.0,
                       unrealized_pl_usd=0.0),
    ]
    rec = reconcile(internal, broker_pos)
    assert (rec["status"] == "match").sum() == 1
    assert (rec["status"] == "qty_mismatch").sum() == 1
    assert (rec["status"] == "internal_missing").sum() == 1
