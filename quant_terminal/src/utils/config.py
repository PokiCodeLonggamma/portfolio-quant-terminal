"""Centralised config loader.

Reads:
  - .env  (secrets, via python-dotenv)
  - config/settings.yaml
  - config/universe.yaml
  - config/risk_limits.yaml

Single Config() instance is loaded lazily and cached.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONFIG_DIR = PROJECT_ROOT / "config"


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Config file missing: {path}")
    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    if not isinstance(data, dict):
        raise ValueError(f"{path} must be a YAML mapping at the top level")
    return data


@dataclass(frozen=True)
class Secrets:
    alpaca_key_id: str = ""
    alpaca_secret_key: str = ""
    alpaca_base_url: str = "https://paper-api.alpaca.markets"
    sec_email: str = ""
    fred_api_key: str = ""
    fmp_api_key: str = ""

    @classmethod
    def from_env(cls) -> "Secrets":
        return cls(
            alpaca_key_id=os.getenv("APCA_API_KEY_ID", ""),
            alpaca_secret_key=os.getenv("APCA_API_SECRET_KEY", ""),
            alpaca_base_url=os.getenv("APCA_API_BASE_URL", "https://paper-api.alpaca.markets"),
            sec_email=os.getenv("SEC_EMAIL", ""),
            fred_api_key=os.getenv("FRED_API_KEY", ""),
            fmp_api_key=os.getenv("FMP_API_KEY", ""),
        )

    @property
    def has_alpaca(self) -> bool:
        return bool(self.alpaca_key_id and self.alpaca_secret_key)


@dataclass(frozen=True)
class Config:
    settings: dict[str, Any] = field(default_factory=dict)
    universe: dict[str, Any] = field(default_factory=dict)
    risk_limits: dict[str, Any] = field(default_factory=dict)
    secrets: Secrets = field(default_factory=Secrets)

    @property
    def data_dir(self) -> Path:
        return (PROJECT_ROOT / self.settings.get("paths", {}).get("data_dir", "./data")).resolve()

    @property
    def cache_dir(self) -> Path:
        p = (PROJECT_ROOT / self.settings.get("paths", {}).get("cache_dir", "./data/cache")).resolve()
        p.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def logs_dir(self) -> Path:
        p = (PROJECT_ROOT / self.settings.get("paths", {}).get("logs_dir", "./logs")).resolve()
        p.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def instruments(self) -> dict[str, dict[str, Any]]:
        return self.universe.get("instruments", {})

    def alpaca_symbol(self, key: str) -> str:
        meta = self.instruments.get(key, {})
        return meta.get("alpaca", "") or ""

    def yfinance_symbol(self, key: str) -> str:
        meta = self.instruments.get(key, {})
        return meta.get("yfinance", "") or key

    def currency_of(self, key: str) -> str:
        return self.instruments.get(key, {}).get("currency", "EUR")

    def theme_of(self, key: str) -> str:
        return self.instruments.get(key, {}).get("theme", "Unclassified")

    def region_of(self, key: str) -> str:
        return self.instruments.get(key, {}).get("region", "Unknown")


@lru_cache(maxsize=1)
def get_config() -> Config:
    load_dotenv(PROJECT_ROOT / ".env", override=False)
    return Config(
        settings=_load_yaml(CONFIG_DIR / "settings.yaml"),
        universe=_load_yaml(CONFIG_DIR / "universe.yaml"),
        risk_limits=_load_yaml(CONFIG_DIR / "risk_limits.yaml"),
        secrets=Secrets.from_env(),
    )
