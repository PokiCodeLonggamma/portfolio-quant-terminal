"""Surveillance watchlist — user-curated list of tickers to monitor.

Persisted as a YAML file under `config/surveillance.yaml` so the user can edit
it manually too. The Streamlit UI in the Watchlists tab exposes an editor.

Public API
----------
* ``load_surveillance() -> list[str]``
* ``save_surveillance(tickers: list[str]) -> None``
"""
from __future__ import annotations

from pathlib import Path

import yaml

from src.utils.logging import get_logger

log = get_logger(__name__)

_CFG_FILE = Path(__file__).resolve().parents[2] / "config" / "surveillance.yaml"


def _normalize(tickers: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for t in tickers:
        if not t:
            continue
        u = str(t).strip().upper()
        if not u or u in seen:
            continue
        seen.add(u)
        out.append(u)
    return out


def load_surveillance(path: Path | None = None) -> list[str]:
    """Read the surveillance ticker list. Returns [] if the file is missing."""
    p = Path(path) if path else _CFG_FILE
    if not p.exists():
        return []
    try:
        with p.open("r", encoding="utf-8") as fp:
            data = yaml.safe_load(fp) or {}
    except Exception as exc:
        log.warning("surveillance.yaml read failed: %s", exc)
        return []
    raw = data.get("tickers") or []
    return _normalize([str(t) for t in raw])


def save_surveillance(tickers: list[str], path: Path | None = None) -> None:
    """Write the surveillance list back to YAML (atomic)."""
    p = Path(path) if path else _CFG_FILE
    p.parent.mkdir(parents=True, exist_ok=True)
    payload = {"tickers": _normalize(tickers)}
    tmp = p.with_suffix(p.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as fp:
        yaml.safe_dump(payload, fp, sort_keys=False, allow_unicode=True)
    tmp.replace(p)
    log.info("surveillance watchlist saved: %d tickers", len(payload["tickers"]))


def merge_with(*lists: list[str]) -> list[str]:
    """Union of N ticker lists, preserving first-seen order."""
    merged: list[str] = []
    seen: set[str] = set()
    for lst in lists:
        for t in lst or []:
            u = str(t).strip().upper()
            if u and u not in seen:
                seen.add(u)
                merged.append(u)
    return merged
