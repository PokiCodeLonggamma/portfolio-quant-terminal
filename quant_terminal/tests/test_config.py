from __future__ import annotations

from src.utils.config import get_config


def test_config_loads_yaml():
    cfg = get_config()
    assert isinstance(cfg.settings, dict)
    assert "paths" in cfg.settings
    assert "risk" in cfg.settings
    # Universe knows the portfolio names from the report
    assert "GOOG" in cfg.instruments
    assert "3OIL.L" in cfg.instruments


def test_config_resolves_currency_and_theme():
    cfg = get_config()
    assert cfg.currency_of("GOOG") == "USD"
    assert cfg.currency_of("3OIL.L") == "USD"
    assert cfg.currency_of("ENGI.PA") == "EUR"
    assert cfg.theme_of("CCJ") == "Uranium"


def test_config_risk_limits_present():
    cfg = get_config()
    assert "position" in cfg.risk_limits
    assert "leveraged_etps" in cfg.risk_limits
