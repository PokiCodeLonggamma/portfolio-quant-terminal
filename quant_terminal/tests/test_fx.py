from __future__ import annotations

import pandas as pd

from src.data import fx


def test_eur_identity():
    assert fx.spot_rate("EUR") == 1.0


def test_series_to_eur_eur_passthrough():
    s = pd.Series([100, 101, 102], index=pd.date_range("2024-01-01", periods=3))
    out = fx.series_to_eur(s, "EUR")
    assert (out.values == s.values).all()


def test_gbp_pence_supported(monkeypatch):
    # spot_rate should accept GBp/GBX without raising
    rate = fx.spot_rate("EUR")  # baseline
    assert rate == 1.0
    # GBp call should at least not crash
    fx.spot_rate.cache_clear()
    val = fx.spot_rate("GBp")
    assert isinstance(val, float)
