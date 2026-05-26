"""Alerts engine — load triggers, evaluate, dispatch, persist."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

from src.alerts import channels as _channels
from src.alerts import state as _state
from src.alerts import triggers as _triggers
from src.alerts.triggers import AlertEvent, Trigger
from src.utils.config import PROJECT_ROOT
from src.utils.logging import get_logger

log = get_logger(__name__)

_CFG_FILE = PROJECT_ROOT / "config" / "alerts.yaml"


@dataclass
class EvaluationContext:
    """Data the engine needs to evaluate all trigger types.

    Each field may be None — the corresponding triggers will just skip.
    """

    prices_eur: pd.DataFrame | None = None
    drawdown_series: pd.Series | None = None
    squeeze_scores_df: pd.DataFrame | None = None
    upcoming_events: list[Any] | None = None
    runway_rows: list[dict] | None = None
    dilution_rows: list[dict] | None = None
    journal_entries: list[Any] | None = None
    iv_ranks: dict[str, float] | None = None


def load_triggers(yaml_path: Path | None = None) -> list[Trigger]:
    path = Path(yaml_path) if yaml_path else _CFG_FILE
    if not path.exists():
        log.info("alerts config not found at %s", path)
        return []
    try:
        with path.open("r", encoding="utf-8") as fp:
            data = yaml.safe_load(fp) or {}
    except Exception as exc:
        log.warning("alerts config read failed: %s", exc)
        return []
    out: list[Trigger] = []
    for raw in data.get("triggers", []):
        if not isinstance(raw, dict):
            continue
        try:
            out.append(Trigger(**raw))
        except Exception as exc:
            log.warning("invalid trigger %s: %s", raw.get("name"), exc)
    return out


def _evaluate_one(t: Trigger, ctx: EvaluationContext) -> AlertEvent | None:
    if not t.enabled:
        return None
    if t.type == "price_breach":
        return _triggers.eval_price_breach(t, ctx.prices_eur)
    if t.type == "drawdown_threshold":
        return _triggers.eval_drawdown_threshold(t, ctx.drawdown_series)
    if t.type == "squeeze_score":
        return _triggers.eval_squeeze_score(t, ctx.squeeze_scores_df)
    if t.type == "catalyst_proximity":
        return _triggers.eval_catalyst_proximity(t, ctx.upcoming_events)
    if t.type == "runway_low":
        return _triggers.eval_runway_low(t, ctx.runway_rows)
    if t.type == "dilution_high":
        return _triggers.eval_dilution_high(t, ctx.dilution_rows)
    if t.type == "journal_stop_breach":
        return _triggers.eval_journal_stop_breach(t, ctx.journal_entries, ctx.prices_eur)
    if t.type == "iv_rank":
        return _triggers.eval_iv_rank(t, ctx.iv_ranks)
    log.warning("Unknown trigger type: %s", t.type)
    return None


def evaluate_all(triggers: list[Trigger], ctx: EvaluationContext,
                 dispatch: bool = True) -> list[AlertEvent]:
    """Evaluate every enabled trigger; respect cooldown; dispatch + persist on fire.

    Returns the list of *newly fired* events (cooldown-blocked ones are skipped).
    """
    fired: list[AlertEvent] = []
    for t in triggers:
        if _state.cooldown_active(t.name, t.cooldown_minutes):
            continue
        try:
            event = _evaluate_one(t, ctx)
        except Exception as exc:
            log.warning("eval error for %s: %s", t.name, exc)
            continue
        if event is None:
            continue
        if dispatch:
            results = _channels.dispatch(event)
            log.info("Fired %s — dispatch results: %s", t.name, results)
        _state.record_fire(t.name, event.fired_at)
        _state.append_history(event)
        fired.append(event)
    return fired
