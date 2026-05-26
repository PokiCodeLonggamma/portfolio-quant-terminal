"""Per-ticker thesis journal — module H.

One YAML file per ticker under ``data/journal/<TICKER>.yaml``.

The shape is documented on `JournalEntry` (see `src.common.schemas`).
Round-trip: `write_journal(entry) -> read_journal(ticker)` returns the same
model values (modulo any default-population for missing optional fields).

The directory is created lazily on first write. For tests, override
``DECISION_JOURNAL_DIR`` via the monkeypatch fixture (see
``tests/test_decision.py``).
"""
from __future__ import annotations

import os
from datetime import date, datetime
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

from src.common.schemas import JournalEntry, JournalMilestone
from src.utils.config import get_config
from src.utils.logging import get_logger

log = get_logger(__name__)


# ---------------------------------------------------------------------------
# Filesystem
# ---------------------------------------------------------------------------
def journal_dir() -> Path:
    """Resolve the journal directory.

    Override path with the ``DECISION_JOURNAL_DIR`` env var (tests use it).
    Otherwise lives under ``<data_dir>/journal``.
    """
    override = os.environ.get("DECISION_JOURNAL_DIR")
    if override:
        p = Path(override).expanduser().resolve()
    else:
        p = (get_config().data_dir / "journal").resolve()
    p.mkdir(parents=True, exist_ok=True)
    return p


def _journal_path(ticker: str) -> Path:
    safe = "".join(c for c in ticker.upper() if c.isalnum() or c in "._-")
    if not safe:
        raise ValueError(f"Invalid ticker for journal path: {ticker!r}")
    return journal_dir() / f"{safe}.yaml"


# ---------------------------------------------------------------------------
# Serialisation helpers
# ---------------------------------------------------------------------------
def _date_to_str(d: date | None) -> str | None:
    if d is None:
        return None
    if isinstance(d, datetime):
        return d.date().isoformat()
    if isinstance(d, date):
        return d.isoformat()
    return str(d)


def _str_to_date(v: Any) -> date | None:
    if v is None:
        return None
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    if isinstance(v, str):
        try:
            return date.fromisoformat(v.strip())
        except ValueError:
            return None
    return None


def _entry_to_dict(entry: JournalEntry) -> dict[str, Any]:
    """Serialise to a plain dict for yaml.safe_dump."""
    d = entry.model_dump()
    d["entry_date"] = _date_to_str(entry.entry_date)
    d["last_updated"] = _date_to_str(entry.last_updated or date.today())
    d["milestones"] = [m.model_dump() for m in entry.milestones]
    return d


def _dict_to_entry(raw: dict[str, Any]) -> JournalEntry:
    """Parse a yaml-loaded dict back into a JournalEntry."""
    raw = dict(raw or {})
    raw["entry_date"] = _str_to_date(raw.get("entry_date"))
    raw["last_updated"] = _str_to_date(raw.get("last_updated"))
    milestones_in = raw.get("milestones") or []
    milestones: list[JournalMilestone] = []
    for m in milestones_in:
        if isinstance(m, JournalMilestone):
            milestones.append(m)
            continue
        if not isinstance(m, dict):
            continue
        try:
            milestones.append(JournalMilestone(
                date=str(m.get("date", "")),
                label=str(m.get("label", "")),
                hit=bool(m.get("hit", False)),
                weight=float(m.get("weight", 1.0)),
            ))
        except Exception as exc:
            log.warning("skipping malformed milestone %r: %s", m, exc)
    raw["milestones"] = milestones
    # Lists default
    raw.setdefault("re_rating_triggers", [])
    raw.setdefault("catalyst_event_ids", [])
    return JournalEntry(**raw)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def read_journal(ticker: str) -> JournalEntry | None:
    """Return the JournalEntry for ``ticker`` or ``None`` if no file exists."""
    if not ticker:
        return None
    path = _journal_path(ticker)
    if not path.exists():
        return None
    try:
        with path.open("r", encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}
    except Exception as exc:
        log.warning("failed reading journal %s: %s", path.name, exc)
        return None
    if not isinstance(raw, dict):
        log.warning("journal file %s is not a mapping", path.name)
        return None
    if "ticker" not in raw:
        raw["ticker"] = ticker.upper()
    try:
        return _dict_to_entry(raw)
    except Exception as exc:
        log.warning("failed parsing journal %s: %s", path.name, exc)
        return None


def write_journal(entry: JournalEntry) -> Path:
    """Write the JournalEntry as YAML and return the path."""
    if not entry.ticker:
        raise ValueError("JournalEntry.ticker is required")
    # Stamp last_updated automatically
    if entry.last_updated is None:
        entry = entry.model_copy(update={"last_updated": date.today()})
    path = _journal_path(entry.ticker)
    payload = _entry_to_dict(entry)
    try:
        with path.open("w", encoding="utf-8") as f:
            yaml.safe_dump(payload, f, sort_keys=False, allow_unicode=True, default_flow_style=False)
    except Exception as exc:
        log.error("failed writing journal %s: %s", path.name, exc)
        raise
    return path


_SUMMARY_COLS = [
    "ticker", "thesis_short", "entry_price_eur", "price_target_eur",
    "stop_loss_thesis_eur", "n_milestones", "n_milestones_hit",
    "last_updated", "has_pre_mortem",
]


def list_journals() -> pd.DataFrame:
    """Return a one-row-per-ticker summary of every journal on disk."""
    out: list[dict[str, Any]] = []
    d = journal_dir()
    if not d.exists():
        return pd.DataFrame(columns=_SUMMARY_COLS)
    for path in sorted(d.glob("*.yaml")):
        ticker = path.stem
        entry = read_journal(ticker)
        if entry is None:
            continue
        thesis = (entry.thesis or "").strip().replace("\n", " ")
        short = thesis if len(thesis) <= 80 else thesis[:77] + "..."
        n_hit = sum(1 for m in entry.milestones if m.hit)
        out.append({
            "ticker": entry.ticker,
            "thesis_short": short,
            "entry_price_eur": entry.entry_price_eur,
            "price_target_eur": entry.price_target_eur,
            "stop_loss_thesis_eur": entry.stop_loss_thesis_eur,
            "n_milestones": len(entry.milestones),
            "n_milestones_hit": n_hit,
            "last_updated": entry.last_updated,
            "has_pre_mortem": bool((entry.pre_mortem or "").strip()),
        })
    if not out:
        return pd.DataFrame(columns=_SUMMARY_COLS)
    df = pd.DataFrame(out)
    return df.sort_values("ticker").reset_index(drop=True)
