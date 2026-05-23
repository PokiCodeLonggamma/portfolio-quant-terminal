"""Shared pytest fixtures."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest


@pytest.fixture
def daily_returns() -> pd.Series:
    rng = np.random.default_rng(seed=42)
    idx = pd.date_range("2024-01-01", periods=252, freq="B")
    return pd.Series(rng.normal(0.0005, 0.012, size=len(idx)), index=idx, name="r")


@pytest.fixture
def price_panel() -> pd.DataFrame:
    rng = np.random.default_rng(seed=7)
    idx = pd.date_range("2024-01-01", periods=252, freq="B")
    cols = ["GOOG", "CCJ", "NTR", "3OIL.L", "IGLN.L"]
    drift = {"GOOG": 0.0006, "CCJ": 0.0008, "NTR": 0.0003, "3OIL.L": 0.0010, "IGLN.L": 0.0002}
    vol = {"GOOG": 0.015, "CCJ": 0.025, "NTR": 0.020, "3OIL.L": 0.055, "IGLN.L": 0.012}
    data = {c: 100 * (1 + rng.normal(drift[c], vol[c], size=len(idx))).cumprod() for c in cols}
    return pd.DataFrame(data, index=idx)


@pytest.fixture
def holdings_df() -> pd.DataFrame:
    return pd.DataFrame({
        "symbol": ["GOOG", "CCJ", "NTR", "3OIL.L", "IGLN.L"],
        "name": ["Alphabet C", "Cameco", "Nutrien", "WTI 3x", "Gold ETC"],
        "quantity": [4, 30, 10, 50, 5],
        "value_eur": [800.0, 750.0, 780.0, 1390.0, 700.0],
        "currency": ["USD", "USD", "USD", "USD", "GBp"],
    })
