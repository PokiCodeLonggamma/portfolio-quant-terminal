"""Persistent state for the alerts engine.

Tracks `last_fired_at` per trigger so the engine can enforce cooldowns
across Streamlit reruns. Stores fired history for the UI timeline.
Storage: JSON at `data/alerts/state.json` and `data/alerts/history.json`.
"""
from __future__ import annotations

import json
from datetime import datetime

from src.alerts.triggers import AlertEvent
from src.utils.config import PROJECT_ROOT
from src.utils.logging import get_logger

log = get_logger(__name__)

_DIR = PROJECT_ROOT / "data" / "alerts"
_STATE_FILE = _DIR / "state.json"
_HISTORY_FILE = _DIR / "history.json"
_MAX_HISTORY = 500


def _ensure_dir() -> None:
    _DIR.mkdir(parents=True, exist_ok=True)


def load_state() -> dict[str, str]:
    """Returns {trigger_name: iso_timestamp_of_last_fire}."""
    if not _STATE_FILE.exists():
        return {}
    try:
        return json.loads(_STATE_FILE.read_text(encoding="utf-8"))
    except Exception as exc:
        log.warning("alerts state read failed: %s", exc)
        return {}


def save_state(state: dict[str, str]) -> None:
    _ensure_dir()
    try:
        _STATE_FILE.write_text(json.dumps(state, indent=2), encoding="utf-8")
    except Exception as exc:
        log.warning("alerts state write failed: %s", exc)


def record_fire(trigger_name: str, when: datetime | None = None) -> None:
    state = load_state()
    state[trigger_name] = (when or datetime.utcnow()).isoformat()
    save_state(state)


def append_history(event: AlertEvent) -> None:
    _ensure_dir()
    history = load_history()
    history.append(json.loads(event.model_dump_json()))
    history = history[-_MAX_HISTORY:]
    try:
        _HISTORY_FILE.write_text(json.dumps(history, indent=2), encoding="utf-8")
    except Exception as exc:
        log.warning("alerts history write failed: %s", exc)


def load_history() -> list[dict]:
    if not _HISTORY_FILE.exists():
        return []
    try:
        return json.loads(_HISTORY_FILE.read_text(encoding="utf-8"))
    except Exception as exc:
        log.warning("alerts history read failed: %s", exc)
        return []


def cooldown_active(trigger_name: str, cooldown_minutes: int) -> bool:
    state = load_state()
    iso = state.get(trigger_name)
    if not iso:
        return False
    try:
        last = datetime.fromisoformat(iso)
    except Exception:
        return False
    elapsed_min = (datetime.utcnow() - last).total_seconds() / 60.0
    return elapsed_min < cooldown_minutes
