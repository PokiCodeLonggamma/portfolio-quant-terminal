"""Pinned-tickers bookmark system.

Lightweight persistent list of favourite tickers exposed in the sidebar for
quick navigation. Stored as YAML so the user can edit by hand or via the UI.

Public API
----------
* ``load_bookmarks() -> list[str]``
* ``save_bookmarks(tickers: list[str]) -> None``
* ``add_bookmark(ticker: str) -> list[str]``
* ``remove_bookmark(ticker: str) -> list[str]``
"""
from __future__ import annotations

from pathlib import Path

import yaml

from src.utils.logging import get_logger

log = get_logger(__name__)

_CFG_FILE = Path(__file__).resolve().parents[2] / "config" / "bookmarks.yaml"


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


def load_bookmarks(path: Path | None = None) -> list[str]:
    p = Path(path) if path else _CFG_FILE
    if not p.exists():
        return []
    try:
        with p.open("r", encoding="utf-8") as fp:
            data = yaml.safe_load(fp) or {}
    except Exception as exc:
        log.warning("bookmarks.yaml read failed: %s", exc)
        return []
    return _normalize([str(t) for t in (data.get("tickers") or [])])


def save_bookmarks(tickers: list[str], path: Path | None = None) -> None:
    p = Path(path) if path else _CFG_FILE
    p.parent.mkdir(parents=True, exist_ok=True)
    payload = {"tickers": _normalize(tickers)}
    tmp = p.with_suffix(p.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as fp:
        yaml.safe_dump(payload, fp, sort_keys=False, allow_unicode=True)
    tmp.replace(p)
    log.info("bookmarks saved: %d tickers", len(payload["tickers"]))


def add_bookmark(ticker: str) -> list[str]:
    current = load_bookmarks()
    current.append(ticker)
    save_bookmarks(current)
    return load_bookmarks()


def remove_bookmark(ticker: str) -> list[str]:
    current = load_bookmarks()
    current = [t for t in current if t.upper() != ticker.strip().upper()]
    save_bookmarks(current)
    return current
