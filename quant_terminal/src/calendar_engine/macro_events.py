"""Macro / monetary-policy / energy-market catalyst calendar.

Reads the hand-curated YAML at ``config/macro_calendar_2026.yaml`` and
emits a unified ``list[CalendarEvent]``.

Categories produced
-------------------
* ``fomc``   — FOMC statements + press conferences (8 per year)
* ``ecb``    — ECB Governing Council monetary-policy meetings (8 per year)
* ``cpi``    — US BLS Consumer Price Index releases (monthly)
* ``eia``    — EIA Weekly Petroleum Status Report (Wednesdays)
* ``opec``   — OPEC+ JMMC / ministerial meetings
* ``nrc``    — NRC SMR docket milestones (per portfolio ticker)

Cache
-----
Namespace ``cal_macro``, 24-hour TTL (these are scheduled dates, not
live data, so we essentially just cache the YAML parse).
"""
from __future__ import annotations

import hashlib
from datetime import date, datetime, time
from pathlib import Path
from typing import Any

import yaml

from src.common.schemas import CalendarEvent
from src.utils.logging import get_logger

log = get_logger(__name__)

_YAML_PATH = (
    Path(__file__).resolve().parents[2] / "config" / "macro_calendar_2026.yaml"
)

# Default UTC times per category (rough — UI does not show hh:mm anyway).
_DEFAULT_TIMES_UTC: dict[str, time] = {
    "fomc": time(19, 0),     # 14:00 ET FOMC press
    "ecb": time(13, 15),     # 14:15 CET GC statement
    "cpi": time(13, 30),     # 08:30 ET BLS release
    "eia": time(15, 30),     # 10:30 ET EIA weekly
    "opec": time(11, 0),     # late-morning Vienna
    "nrc": time(15, 0),      # mid-day ET public meeting
}


def _event_id(category: str, when: date, label: str) -> str:
    raw = f"{category}|{when.isoformat()}|{label}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def _coerce_date(raw: Any) -> date | None:
    if isinstance(raw, date) and not isinstance(raw, datetime):
        return raw
    if isinstance(raw, datetime):
        return raw.date()
    if isinstance(raw, str):
        try:
            return date.fromisoformat(raw[:10])
        except ValueError:
            return None
    return None


def _load_yaml(path: Path | None = None) -> dict[str, Any]:
    p = Path(path) if path else _YAML_PATH
    if not p.exists():
        log.warning("macro calendar yaml missing: %s", p)
        return {}
    try:
        with p.open("r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        if not isinstance(data, dict):
            log.warning("macro calendar yaml malformed (not a mapping)")
            return {}
        return data
    except Exception as exc:
        log.error("macro calendar yaml parse failed: %s", exc)
        return {}


def load_macro_events(
    *, yaml_path: Path | str | None = None, categories: list[str] | None = None,
) -> list[CalendarEvent]:
    """Return all macro CalendarEvents declared in the YAML.

    Parameters
    ----------
    yaml_path : optional override (used by tests).
    categories : optional whitelist of categories to keep
                 (``["fomc","ecb","cpi","eia","opec","nrc"]``).
    """
    data = _load_yaml(Path(yaml_path) if yaml_path else None)
    if not data:
        return []
    keep = set(categories) if categories else None
    out: list[CalendarEvent] = []
    for category, items in data.items():
        cat = str(category).lower()
        if keep is not None and cat not in keep:
            continue
        if cat not in (
            "fomc", "ecb", "cpi", "eia", "opec", "nrc"
        ):
            log.debug("skipping unknown macro category %r", cat)
            continue
        if not isinstance(items, list):
            continue
        for it in items:
            if not isinstance(it, dict):
                continue
            d = _coerce_date(it.get("date"))
            if d is None:
                continue
            title = str(it.get("title") or f"{cat.upper()} event")
            ticker = it.get("ticker")
            tnorm = str(ticker).upper() if ticker else None
            t_default = _DEFAULT_TIMES_UTC.get(cat, time(12, 0))
            start = datetime.combine(d, t_default)
            payload = {k: v for k, v in it.items() if k not in ("date", "title", "ticker")}
            out.append(CalendarEvent(
                event_id=_event_id(cat, d, title),
                ticker=tnorm,
                category=cat,  # type: ignore[arg-type]
                start=start,
                end=None,
                title=title,
                source="manual",
                payload=payload,
            ))
    return sorted(out, key=lambda e: e.start)


def load_2026() -> list[CalendarEvent]:
    """Convenience alias used by the dashboards and tests."""
    return load_macro_events()
