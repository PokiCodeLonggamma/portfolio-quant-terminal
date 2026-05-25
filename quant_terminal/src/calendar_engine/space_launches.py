"""Space launch manifest reader (SpaceX + Rocket Lab).

Loads ``config/launches_2026.yaml`` and returns ``list[CalendarEvent]``
with ``category="launch"``.  Each event's ``payload`` carries the
``vehicle``, ``customer`` and ``operator`` so dashboards can render the
proper provider badge.

Cache
-----
Namespace ``cal_launches``, 24-hour TTL.
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
    Path(__file__).resolve().parents[2] / "config" / "launches_2026.yaml"
)

# Listed-equity proxies — only used to attach a ticker to launches that
# obviously belong to a public company.  SpaceX is private — we still tag
# its Starlink missions with ticker=None.
_OPERATOR_TICKER = {
    "rocketlab": "RKLB",
    # SpaceX is private; we attach ticker via customer-name detection below.
}


def _event_id(operator: str, when: date, mission: str) -> str:
    raw = f"launch|{operator}|{when.isoformat()}|{mission}"
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


def _customer_ticker(customer: str) -> str | None:
    """Best-effort: detect 'XYZ (TICKER)' suffix or known operator tags."""
    if not customer:
        return None
    import re
    m = re.search(r"\(([A-Z\.]{2,6})\)", customer)
    if m:
        return m.group(1).upper()
    cu = customer.lower()
    if "blacksky" in cu:
        return "BKSY"
    if "ast spacemobile" in cu:
        return "ASTS"
    if "rocket lab" in cu:
        return "RKLB"
    return None


def _load_yaml(path: Path | None = None) -> dict[str, Any]:
    p = Path(path) if path else _YAML_PATH
    if not p.exists():
        log.warning("launches yaml missing: %s", p)
        return {}
    try:
        with p.open("r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        if not isinstance(data, dict):
            return {}
        return data
    except Exception as exc:
        log.error("launches yaml parse failed: %s", exc)
        return {}


def load_launches(*, yaml_path: Path | str | None = None) -> list[CalendarEvent]:
    """Return all launches declared in the YAML as `CalendarEvent` list."""
    data = _load_yaml(Path(yaml_path) if yaml_path else None)
    if not data:
        return []
    out: list[CalendarEvent] = []
    for operator, items in data.items():
        op_key = str(operator).lower()
        if not isinstance(items, list):
            continue
        for it in items:
            if not isinstance(it, dict):
                continue
            d = _coerce_date(it.get("date"))
            if d is None:
                continue
            mission = str(it.get("mission") or "Launch").strip()
            vehicle = str(it.get("vehicle") or "").strip()
            customer = str(it.get("customer") or "").strip()
            ticker = _OPERATOR_TICKER.get(op_key) or _customer_ticker(customer)
            title_parts = [vehicle, "—", mission] if vehicle else [mission]
            title = " ".join(part for part in title_parts if part)
            start = datetime.combine(d, time(12, 0))
            payload = {
                "operator": op_key,
                "vehicle": vehicle,
                "customer": customer,
                "mission": mission,
            }
            out.append(CalendarEvent(
                event_id=_event_id(op_key, d, mission),
                ticker=ticker,
                category="launch",
                start=start,
                end=None,
                title=title,
                source="manual",
                payload=payload,
            ))
    return sorted(out, key=lambda e: e.start)
