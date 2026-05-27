"""Service layer — pure Python orchestration of the core modules.

Each ``*_service.py`` exposes a class with sync (or async) methods that:
1. Pull data from upstream providers (yfinance, Alpaca, SEC, …)
2. Compute via the pure modules in ``src/<domain>/``
3. Return Pydantic v2 DTOs from :mod:`src.services.schemas`

Consumed by both ``api/`` (FastAPI) and the legacy Streamlit dashboards
(``src/<domain>/dashboards.py``). Streamlit-coupled code in
``*_dashboard.py`` becomes a thin presentation layer over these services.
"""
from src.services.cross_asset_service import CrossAssetService
from src.services.options_service import OptionsService
from src.services.regime_service import RegimeService

__all__ = [
    "CrossAssetService",
    "OptionsService",
    "RegimeService",
]
