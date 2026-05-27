"""Phase 1 — FastAPI surface tests for the new service-backed endpoints.

We patch the singleton services with stub fetchers so tests stay offline.
"""
from __future__ import annotations

from datetime import date, datetime
from unittest.mock import patch

import pandas as pd
from fastapi.testclient import TestClient

from api.main import app
from src.common.schemas import OptionContract, OptionRight
from src.services import CrossAssetService, OptionsService, RegimeService

client = TestClient(app)


# ---------------------------------------------------------------------------
# /api/cross-asset/quotes — POST
# ---------------------------------------------------------------------------
def test_post_quotes_batch_with_known_logicals():
    stub = CrossAssetService(quote_fetch_fn=lambda _sym: {
        "last": 100.0, "chg_1d_pct": 0.5, "chg_5d_pct": -1.0,
    })
    with patch("api.routes.cross_asset._service", stub):
        r = client.post(
            "/api/cross-asset/quotes",
            json={"logicals": ["ES", "NQ", "CL"]},
        )
    assert r.status_code == 200
    body = r.json()
    assert body["requested"] == 3
    assert body["resolved"] == 3
    assert len(body["quotes"]) == 3


def test_post_quotes_batch_bad_payload_returns_400():
    r = client.post("/api/cross-asset/quotes", json={"foo": "bar"})
    assert r.status_code == 400


def test_post_quotes_batch_caps_at_100():
    r = client.post(
        "/api/cross-asset/quotes",
        json={"logicals": ["ES"] * 101},
    )
    assert r.status_code == 400


# ---------------------------------------------------------------------------
# /api/cross-asset/heatmap — GET
# ---------------------------------------------------------------------------
def test_get_heatmap_returns_list():
    stub = CrossAssetService(quote_fetch_fn=lambda _sym: {
        "last": 100.0, "chg_1d_pct": 0.1, "chg_5d_pct": 0.2,
    })
    with patch("api.routes.cross_asset._service", stub):
        r = client.get("/api/cross-asset/heatmap")
    assert r.status_code == 200
    body = r.json()
    assert isinstance(body, list)
    assert len(body) > 0


# ---------------------------------------------------------------------------
# /api/options/{ticker}/gex — GET
# ---------------------------------------------------------------------------
def _mk_chain():
    chain = []
    for s in (95, 100, 105):
        for right in (OptionRight.CALL, OptionRight.PUT):
            chain.append(OptionContract(
                underlying="TEST",
                symbol=f"TEST261218{right.value}{int(s*1000):08d}",
                expiry=date(2026, 12, 18),
                strike=float(s), right=right,
                bid=1.0, ask=1.1, last=1.05, mid=1.05,
                iv=0.30,
                delta=0.5 if right == OptionRight.CALL else -0.5,
                gamma=0.01, theta=-0.02, vega=0.10,
                open_interest=1500, volume=200,
                snapshot_ts=datetime.utcnow(),
                source="alpaca",
            ))
    return chain


def test_get_options_gex_returns_summary():
    stub = OptionsService(
        chain_fetch_fn=lambda _tk: _mk_chain(),
        spot_fetch_fn=lambda _tk: 100.0,
    )
    with patch("api.routes.options._service", stub):
        r = client.get("/api/options/TEST/gex")
    assert r.status_code == 200
    body = r.json()
    assert body["ticker"] == "TEST"
    assert body["spot"] == 100.0
    assert "buckets" in body
    assert isinstance(body["buckets"], list)


def test_get_options_gex_503_when_unavailable():
    stub = OptionsService(
        chain_fetch_fn=lambda _tk: [],
        spot_fetch_fn=lambda _tk: None,
    )
    with patch("api.routes.options._service", stub):
        r = client.get("/api/options/TEST/gex")
    assert r.status_code == 503


# ---------------------------------------------------------------------------
# /api/options/{ticker}/available — GET
# ---------------------------------------------------------------------------
def test_get_options_available_true():
    stub = OptionsService(
        chain_fetch_fn=lambda _tk: _mk_chain(),
        spot_fetch_fn=lambda _tk: 100.0,
    )
    with patch("api.routes.options._service", stub):
        r = client.get("/api/options/TEST/available")
    assert r.status_code == 200
    assert r.json() == {"ticker": "TEST", "available": True}


def test_get_options_available_false():
    stub = OptionsService(
        chain_fetch_fn=lambda _tk: [],
        spot_fetch_fn=lambda _tk: None,
    )
    with patch("api.routes.options._service", stub):
        r = client.get("/api/options/NOPE/available")
    assert r.status_code == 200
    assert r.json() == {"ticker": "NOPE", "available": False}


# ---------------------------------------------------------------------------
# /api/options/{ticker}/iv_term_structure — GET
# ---------------------------------------------------------------------------
def test_get_iv_term_structure_returns_list():
    stub = OptionsService(
        chain_fetch_fn=lambda _tk: _mk_chain(),
        spot_fetch_fn=lambda _tk: 100.0,
    )
    with patch("api.routes.options._service", stub):
        r = client.get("/api/options/TEST/iv_term_structure")
    assert r.status_code == 200
    body = r.json()
    assert isinstance(body, list)


# ---------------------------------------------------------------------------
# /api/regime/hmm/{ticker} — GET
# ---------------------------------------------------------------------------
def _synth_prices(n=400):
    import numpy as np
    rng = np.random.default_rng(0)
    log_returns = rng.normal(0.0005, 0.012, size=n)
    log_returns[150:200] = rng.normal(0.0, 0.04, size=50)
    prices = 100.0 * (1 + log_returns).cumprod()
    idx = pd.date_range("2024-01-01", periods=n, freq="B")
    return pd.Series(prices, index=idx)


def test_get_hmm_returns_regime():
    stub = RegimeService(history_fetch_fn=lambda _tk: _synth_prices())
    with patch("api.routes.regime._service", stub):
        r = client.get("/api/regime/hmm/SPY")
    assert r.status_code == 200
    body = r.json()
    assert body["ticker"] == "SPY"
    assert body["n_states"] == 3
    assert body["sample_size"] > 100


def test_get_hmm_503_when_no_history():
    stub = RegimeService(history_fetch_fn=lambda _tk: pd.Series(dtype=float))
    with patch("api.routes.regime._service", stub):
        r = client.get("/api/regime/hmm/SPY")
    assert r.status_code == 503


def test_get_hmm_validates_n_states():
    r = client.get("/api/regime/hmm/SPY?n_states=10")
    assert r.status_code == 422  # Pydantic le > 5
