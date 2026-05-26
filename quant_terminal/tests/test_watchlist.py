"""Tests for Cluster 6 — Watchlists."""
from __future__ import annotations

from datetime import datetime

import numpy as np
import pandas as pd
import pytest

from src.common.schemas import WatchlistEntry
from src.watchlist import enricher as enricher_mod
from src.watchlist.enricher import ENRICHED_COLUMNS, add_live_prices
from src.watchlist.loader import load_watchlist, parse_entries
from src.watchlist.mini_card import mini_card_payload
from src.watchlist.private import load_private_watchlist


# ---------------------------------------------------------------------------
# YAML loading
# ---------------------------------------------------------------------------
REQUIRED_COLS = {
    "symbol",
    "name",
    "quantity",
    "value_eur",
    "currency",
    "region",
    "theme",
    "asset_class",
    "yfinance_symbol",
    "universe_key",
    "sub_theme",
    "conviction",
    "catalyst",
    "peers",
    "list_name",
    "private",
}


def test_load_watchlist_quantum_non_empty_and_columns() -> None:
    df = load_watchlist("quantum")
    assert not df.empty, "quantum watchlist should not be empty"
    missing = REQUIRED_COLS - set(df.columns)
    assert not missing, f"missing required columns: {missing}"
    # Must include the brief-mandated quantum hardware names.
    syms = set(df["symbol"].astype(str))
    for must in ["IONQ", "RGTI", "QBTS", "QUBT", "IBM", "GOOG", "MSFT", "INTC", "NVDA", "HON"]:
        assert must in syms, f"quantum watchlist missing {must}"
    assert (df["list_name"] == "quantum").all()


def test_load_watchlist_photonics_contains_lidar_and_optics() -> None:
    df = load_watchlist("photonics")
    assert not df.empty
    syms = set(df["symbol"].astype(str))
    # AI optics datacenter
    assert {"AAOI", "LITE", "COHR", "FN", "IPGP", "MTSI", "MRVL"} <= syms
    # LiDAR coverage
    assert {"LAZR", "OUST", "AEVA", "INVZ", "MVIS"} <= syms


def test_load_watchlist_defense_has_smr_and_primes() -> None:
    df = load_watchlist("defense")
    assert not df.empty
    syms = set(df["symbol"].astype(str))
    assert {"BWXT", "CCJ", "NNE"} <= syms  # nuclear / SMR
    assert {"RDW", "RKLB", "BKSY", "KTOS", "AVAV"} <= syms  # space-defense + drones
    assert {"LMT", "RTX", "NOC"} <= syms  # primes


def test_watchlist_entry_validates_sample_entry() -> None:
    """Validate that a representative entry round-trips through the schema."""
    entries = parse_entries("quantum")
    assert entries, "expected at least one quantum entry"
    sample = entries[0]
    assert isinstance(sample, WatchlistEntry)
    assert sample.list_name == "quantum"
    assert sample.currency
    assert sample.universe_key
    # Explicit construction also works (schema has no required missing field).
    direct = WatchlistEntry(
        universe_key="TEST",
        sub_theme="Test",
        list_name="quantum",
        conviction="core",
        catalyst="x",
        peers=["A", "B"],
    )
    assert direct.universe_key == "TEST"
    # Bad conviction must raise.
    with pytest.raises(Exception):
        WatchlistEntry(
            universe_key="TEST",
            sub_theme="Test",
            list_name="quantum",
            conviction="garbage",  # type: ignore[arg-type]
        )


# ---------------------------------------------------------------------------
# Private watchlist
# ---------------------------------------------------------------------------
def test_load_private_watchlist_returns_ten_entries() -> None:
    df = load_private_watchlist()
    assert len(df) == 10, f"expected 10 private entries, got {len(df)}"
    expected_names = {
        "SpaceX",
        "PsiQuantum",
        "Pasqal",
        "Helion",
        "Vast",
        "Astranis",
        "Stoke_Space",
        "IQM",
        "Quantinuum",
        "Atom_Computing",
    }
    assert set(df["symbol"].astype(str)) == expected_names
    # Schema sanity
    for col in (
        "symbol",
        "name",
        "sub_theme",
        "latest_valuation_usd_b",
        "last_round_date",
        "last_round_type",
        "lead_investor",
        "listed_proxies",
        "private",
    ):
        assert col in df.columns
    # All marked private; all have listed_proxies as a list.
    assert df["private"].all()
    assert all(isinstance(p, list) for p in df["listed_proxies"])
    # SpaceX should have the largest valuation.
    spacex = df.loc[df["symbol"] == "SpaceX"].iloc[0]
    assert spacex["latest_valuation_usd_b"] == pytest.approx(350.0)


def test_load_watchlist_pre_ipo_projects_private_rows() -> None:
    df = load_watchlist("pre_ipo")
    assert not df.empty
    assert df["list_name"].eq("pre_ipo").all()
    assert df["private"].all()


# ---------------------------------------------------------------------------
# Enricher
# ---------------------------------------------------------------------------
def _fake_price_panel(symbols: list[str]) -> pd.DataFrame:
    rng = np.random.default_rng(seed=11)
    idx = pd.date_range("2025-01-02", periods=120, freq="B")
    data = {
        s: 100.0 * (1 + rng.normal(0.0005, 0.012, size=len(idx))).cumprod()
        for s in symbols
    }
    return pd.DataFrame(data, index=idx)


def test_add_live_prices_attaches_numeric_returns(monkeypatch: pytest.MonkeyPatch) -> None:
    wl = load_watchlist("quantum").head(3).copy()
    syms = wl["symbol"].astype(str).tolist()

    fake = _fake_price_panel(syms)

    def _fake_download_prices(keys, start=None, end=None):  # noqa: ARG001
        return fake[[k for k in keys if k in fake.columns]]

    # Monkey-patch the symbol used inside the enricher module.
    monkeypatch.setattr(enricher_mod, "download_prices", _fake_download_prices)
    # Force FX to be identity so EUR == listing currency for the test.
    monkeypatch.setattr(
        "src.watchlist.enricher.series_to_eur", lambda s, ccy: s.copy()
    )

    out = add_live_prices(wl, start=datetime(2025, 1, 1), end=datetime(2025, 6, 30))

    for col in ENRICHED_COLUMNS:
        assert col in out.columns, f"missing enriched column {col}"

    # At least one ticker must have at least one finite numeric return.
    numeric_return_cols = ["ret_1d", "ret_1w", "ret_1m", "ret_3m", "ret_ytd"]
    finite_mask = out[numeric_return_cols].apply(
        lambda col: pd.to_numeric(col, errors="coerce")
    ).notna()
    assert finite_mask.values.any(), "expected at least one numeric return value"

    # last_close_eur should be a positive finite number for every fetched ticker.
    for sym in syms:
        row = out.loc[out["symbol"] == sym].iloc[0]
        assert row["last_close_eur"] is not None
        assert float(row["last_close_eur"]) > 0


def test_add_live_prices_with_pre_supplied_panel_skips_download(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If `price_panel` is provided, the loader does not need to be called."""
    monkeypatch.setattr(
        "src.watchlist.enricher.series_to_eur", lambda s, ccy: s.copy()
    )
    # Sentinel — if `download_prices` is called we want to know.
    def _explode(*a, **k):  # noqa: ARG001
        raise AssertionError("download_prices should not be called when price_panel is provided")

    monkeypatch.setattr(enricher_mod, "download_prices", _explode)

    wl = load_watchlist("photonics").head(2).copy()
    syms = wl["symbol"].astype(str).tolist()
    panel = _fake_price_panel(syms)

    out = add_live_prices(wl, price_panel=panel)
    assert "last_close_eur" in out.columns
    assert out["last_close_eur"].notna().any()


# ---------------------------------------------------------------------------
# Mini card payload
# ---------------------------------------------------------------------------
def test_mini_card_payload_shape_and_sparkline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "src.watchlist.enricher.series_to_eur", lambda s, ccy: s.copy()
    )
    wl = load_watchlist("defense").head(1).copy()
    panel = _fake_price_panel(wl["symbol"].astype(str).tolist())
    enriched = add_live_prices(wl, price_panel=panel)
    row = enriched.iloc[0]
    sym = str(row["symbol"])

    payload = mini_card_payload(row, prices_eur=panel[sym])
    # Required keys present
    for key in (
        "symbol",
        "list_name",
        "sub_theme",
        "conviction",
        "catalyst",
        "peers",
        "last_close_eur",
        "ret_1d",
        "ret_ytd",
        "sparkline",
    ):
        assert key in payload
    assert payload["symbol"] == sym
    assert isinstance(payload["sparkline"]["values"], list)
    assert isinstance(payload["sparkline"]["index"], list)
    assert len(payload["sparkline"]["values"]) > 0


def test_mini_card_payload_handles_missing_prices() -> None:
    wl = load_watchlist("quantum").head(1).copy()
    row = wl.iloc[0]
    payload = mini_card_payload(row, prices_eur=None)
    assert payload["symbol"] == str(row["symbol"])
    # No prices => sparkline is empty + last_close_eur is None
    assert payload["sparkline"] == {"index": [], "values": []}
    assert payload["last_close_eur"] is None
