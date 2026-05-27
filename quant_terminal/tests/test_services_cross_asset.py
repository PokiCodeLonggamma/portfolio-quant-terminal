"""Phase 1 — CrossAssetService tests (TDD).

The service must be testable WITHOUT live network calls — we inject a
``quote_fetch_fn`` so tests can pass stub data.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from src.services.cross_asset_service import CrossAssetService
from src.services.schemas import HeatmapRow, Quote, QuoteBatch


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
def _stub_quote(symbol: str) -> dict:
    """Return a deterministic stub quote shape for a given yfinance symbol."""
    base = {
        "ES=F": {"last": 5000.0, "chg_1d_pct": 0.5, "chg_5d_pct": -1.2},
        "NQ=F": {"last": 18000.0, "chg_1d_pct": 1.2, "chg_5d_pct": 2.4},
        "CL=F": {"last": 75.0, "chg_1d_pct": -0.8, "chg_5d_pct": -3.5},
        "GC=F": {"last": 2050.0, "chg_1d_pct": 0.2, "chg_5d_pct": 1.1},
        "BTC=F": {"last": 65000.0, "chg_1d_pct": 3.5, "chg_5d_pct": -2.1},
    }
    return base.get(symbol, {"last": None, "chg_1d_pct": None, "chg_5d_pct": None})


@pytest.fixture
def service():
    """A service instance with a deterministic stub fetcher (no network)."""
    return CrossAssetService(quote_fetch_fn=_stub_quote)


# ---------------------------------------------------------------------------
# get_quote (single)
# ---------------------------------------------------------------------------
def test_get_quote_known_symbol_returns_filled_pydantic(service):
    q = service.get_quote("ES")
    assert isinstance(q, Quote)
    assert q.logical == "ES"
    assert q.last == 5000.0
    assert q.chg_1d_pct == 0.5
    assert q.chg_5d_pct == -1.2
    assert q.asof is not None
    assert q.source == "stub"


def test_get_quote_unknown_logical_returns_empty_quote(service):
    """Service is null-safe — unknown logical → Quote with all None fields."""
    q = service.get_quote("NOPE")
    assert isinstance(q, Quote)
    assert q.logical == "NOPE"
    assert q.last is None
    assert q.chg_1d_pct is None


def test_get_quote_uses_resolve_symbol_for_yfinance(service):
    """ES should resolve to ES=F via cross_asset.resolve_symbol."""
    q = service.get_quote("ES")
    assert q.last == 5000.0  # stub returns 5000.0 for ES=F


# ---------------------------------------------------------------------------
# get_quotes_batch
# ---------------------------------------------------------------------------
def test_get_quotes_batch_resolves_all_known(service):
    batch = service.get_quotes_batch(["ES", "NQ", "CL"])
    assert isinstance(batch, QuoteBatch)
    assert batch.requested == 3
    # All 3 have stub data → 3 resolved (last is not None)
    assert batch.resolved == 3
    assert len(batch.quotes) == 3
    logicals = {q.logical for q in batch.quotes}
    assert logicals == {"ES", "NQ", "CL"}


def test_get_quotes_batch_partial_unknown(service):
    batch = service.get_quotes_batch(["ES", "NOPE"])
    assert batch.requested == 2
    assert batch.resolved == 1  # only ES has data
    assert len(batch.quotes) == 2


def test_get_quotes_batch_empty_input(service):
    batch = service.get_quotes_batch([])
    assert batch.requested == 0
    assert batch.resolved == 0
    assert batch.quotes == []
    assert isinstance(batch.asof, datetime)


def test_get_quotes_batch_deduplicates_input(service):
    """Asking ES twice should result in 1 entry."""
    batch = service.get_quotes_batch(["ES", "ES", "NQ"])
    logicals = {q.logical for q in batch.quotes}
    assert logicals == {"ES", "NQ"}


# ---------------------------------------------------------------------------
# get_heatmap_rows
# ---------------------------------------------------------------------------
def test_heatmap_includes_all_yfinance_mapped_contracts(service):
    rows = service.get_heatmap_rows()
    assert isinstance(rows, list)
    # Service should hit every contract in the cross-asset universe that has
    # a yfinance symbol. ES, NQ, CL, GC, BTC are all in our stub.
    logicals = {r.logical for r in rows}
    for must_have in ("ES", "NQ", "CL", "GC"):
        assert must_have in logicals, f"heatmap missing {must_have}"
    for r in rows:
        assert isinstance(r, HeatmapRow)
        assert r.asset_class
        assert r.name


def test_heatmap_sorted_desc_by_1d_pct(service):
    rows = service.get_heatmap_rows()
    # Filter to rows where chg_1d_pct is known
    known = [r for r in rows if r.chg_1d_pct is not None]
    # Service contract: descending order
    sorted_known = sorted(known, key=lambda r: r.chg_1d_pct, reverse=True)
    assert known == sorted_known


def test_heatmap_filters_unknown_chg():
    """Heatmap should NOT include rows where chg_1d_pct is None
    (i.e. data wasn't fetched). Otherwise it pollutes the UI."""
    def empty_fetcher(_symbol: str) -> dict:
        return {"last": None, "chg_1d_pct": None, "chg_5d_pct": None}

    s = CrossAssetService(quote_fetch_fn=empty_fetcher)
    rows = s.get_heatmap_rows()
    assert rows == []  # everything filtered out


# ---------------------------------------------------------------------------
# Service contract — no streamlit imports
# ---------------------------------------------------------------------------
def test_service_module_has_no_streamlit_import():
    """The service must be pure — no Streamlit dependency."""
    import src.services.cross_asset_service as mod
    src = mod.__file__
    with open(src, encoding="utf-8") as f:
        content = f.read()
    assert "import streamlit" not in content
    assert "from streamlit" not in content


def test_quote_timestamp_is_utc(service):
    q = service.get_quote("ES")
    assert q.asof is not None
    # We don't enforce timezone-aware in the schema, but asof should be recent
    # (within last 60 seconds — fast-running test).
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    delta = (now - q.asof.replace(tzinfo=None)).total_seconds()
    assert -2 < delta < 60
