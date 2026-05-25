"""Tests for the alerts engine (Feature 2)."""
from __future__ import annotations


import pandas as pd
import pytest

from src.alerts import state as _state
from src.alerts.engine import EvaluationContext, evaluate_all, load_triggers
from src.alerts.triggers import (
    Trigger,
    eval_drawdown_threshold,
    eval_price_breach,
    eval_squeeze_score,
)


@pytest.fixture(autouse=True)
def _isolate_state(tmp_path, monkeypatch):
    """Redirect alerts state + history to a tmp dir for every test."""
    monkeypatch.setattr(_state, "_DIR", tmp_path)
    monkeypatch.setattr(_state, "_STATE_FILE", tmp_path / "state.json")
    monkeypatch.setattr(_state, "_HISTORY_FILE", tmp_path / "history.json")
    yield


# ---------------------------------------------------------------------------
# Per-trigger evaluators
# ---------------------------------------------------------------------------
def test_price_breach_below_fires():
    t = Trigger(name="t1", type="price_breach",
                params={"ticker": "ASTS", "direction": "below", "threshold_eur": 100.0})
    prices = pd.DataFrame({"ASTS": [120, 110, 95]})
    ev = eval_price_breach(t, prices)
    assert ev is not None
    assert ev.payload["last_price"] == 95.0
    assert ev.severity == "warning"


def test_price_breach_below_no_match():
    t = Trigger(name="t1", type="price_breach",
                params={"ticker": "ASTS", "direction": "below", "threshold_eur": 90.0})
    prices = pd.DataFrame({"ASTS": [120, 110, 95]})
    assert eval_price_breach(t, prices) is None


def test_price_breach_above_fires():
    t = Trigger(name="t1", type="price_breach",
                params={"ticker": "RKLB", "direction": "above", "threshold_eur": 130.0})
    prices = pd.DataFrame({"RKLB": [100, 120, 135]})
    ev = eval_price_breach(t, prices)
    assert ev is not None and ev.payload["last_price"] == 135.0


def test_drawdown_threshold_fires_on_breach():
    t = Trigger(name="t_dd", type="drawdown_threshold", params={"threshold_pct": 0.10})
    dd = pd.Series([-0.02, -0.05, -0.12])
    ev = eval_drawdown_threshold(t, dd)
    assert ev is not None and ev.payload["current_dd"] == -0.12


def test_drawdown_threshold_no_breach():
    t = Trigger(name="t_dd", type="drawdown_threshold", params={"threshold_pct": 0.20})
    dd = pd.Series([-0.02, -0.05, -0.12])
    assert eval_drawdown_threshold(t, dd) is None


def test_squeeze_score_fires_above_threshold():
    t = Trigger(name="t_sq", type="squeeze_score", params={"threshold": 80})
    df = pd.DataFrame({"ticker": ["ASTS", "RKLB"], "score": [60, 90]})
    ev = eval_squeeze_score(t, df)
    assert ev is not None and "RKLB" in ev.title


# ---------------------------------------------------------------------------
# Engine integration
# ---------------------------------------------------------------------------
def test_engine_respects_cooldown():
    trigger = Trigger(name="t_dd", type="drawdown_threshold",
                      cooldown_minutes=60,
                      channels=["streamlit"],
                      params={"threshold_pct": 0.05})
    ctx = EvaluationContext(drawdown_series=pd.Series([-0.10]))
    fired_first = evaluate_all([trigger], ctx, dispatch=False)
    fired_second = evaluate_all([trigger], ctx, dispatch=False)
    assert len(fired_first) == 1
    assert len(fired_second) == 0  # blocked by cooldown


def test_engine_persists_history():
    trigger = Trigger(name="t_dd2", type="drawdown_threshold",
                      cooldown_minutes=0,
                      channels=["streamlit"],
                      params={"threshold_pct": 0.05})
    ctx = EvaluationContext(drawdown_series=pd.Series([-0.10]))
    evaluate_all([trigger], ctx, dispatch=False)
    history = _state.load_history()
    assert len(history) >= 1
    assert history[-1]["trigger_name"] == "t_dd2"


# ---------------------------------------------------------------------------
# Config loader
# ---------------------------------------------------------------------------
def test_load_triggers_returns_list_when_yaml_exists():
    """Smoke: the shipped config should parse cleanly."""
    triggers = load_triggers()
    assert isinstance(triggers, list)
    assert any(t.name == "portfolio_drawdown_5pct" for t in triggers)
    assert all(isinstance(t, Trigger) for t in triggers)


def test_load_triggers_handles_missing_file(tmp_path):
    triggers = load_triggers(tmp_path / "nope.yaml")
    assert triggers == []


# ---------------------------------------------------------------------------
# Disabled trigger short-circuits
# ---------------------------------------------------------------------------
def test_disabled_trigger_does_not_fire():
    trigger = Trigger(name="t_dis", type="drawdown_threshold",
                      enabled=False,
                      params={"threshold_pct": 0.05})
    ctx = EvaluationContext(drawdown_series=pd.Series([-0.50]))
    fired = evaluate_all([trigger], ctx, dispatch=False)
    assert fired == []
