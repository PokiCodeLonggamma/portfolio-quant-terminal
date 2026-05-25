"""Snapshot persistence — one parquet directory per day."""
from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path
from typing import Any

import pandas as pd

from src.common.schemas import SnapshotMeta
from src.utils.config import PROJECT_ROOT
from src.utils.logging import get_logger

log = get_logger(__name__)

_BASE = PROJECT_ROOT / "data" / "snapshots"


def _ensure() -> Path:
    _BASE.mkdir(parents=True, exist_ok=True)
    return _BASE


def _dir_for(asof: date) -> Path:
    p = _ensure() / asof.isoformat()
    p.mkdir(parents=True, exist_ok=True)
    return p


def save(bundle: dict[str, Any]) -> Path:
    """Write a snapshot bundle. Returns the directory path."""
    meta: SnapshotMeta = bundle["meta"]
    d = _dir_for(meta.asof)
    (d / "meta.json").write_text(meta.model_dump_json(indent=2), encoding="utf-8")
    positions: pd.DataFrame = bundle.get("positions", pd.DataFrame())
    if not positions.empty:
        positions.to_parquet(d / "positions.parquet", index=False)
    options: pd.DataFrame = bundle.get("options", pd.DataFrame())
    if not options.empty:
        options.to_parquet(d / "options.parquet", index=False)
    return d


def load(asof: date) -> dict[str, Any] | None:
    d = _BASE / asof.isoformat()
    if not d.exists():
        return None
    meta_path = d / "meta.json"
    if not meta_path.exists():
        return None
    try:
        meta = SnapshotMeta(**json.loads(meta_path.read_text(encoding="utf-8")))
    except Exception as exc:
        log.warning("snapshot meta read failed for %s: %s", asof, exc)
        return None
    pos = pd.read_parquet(d / "positions.parquet") if (d / "positions.parquet").exists() else pd.DataFrame()
    opt = pd.read_parquet(d / "options.parquet") if (d / "options.parquet").exists() else pd.DataFrame()
    return {"meta": meta, "positions": pos, "options": opt}


def list_dates() -> list[date]:
    if not _BASE.exists():
        return []
    out: list[date] = []
    for child in sorted(_BASE.iterdir()):
        if not child.is_dir():
            continue
        try:
            out.append(date.fromisoformat(child.name))
        except Exception:
            continue
    return out


def history_table() -> pd.DataFrame:
    rows = []
    for d in list_dates():
        b = load(d)
        if b is None:
            continue
        m = b["meta"]
        rows.append({
            "asof": m.asof.isoformat(),
            "net_eur": m.net_value_eur,
            "gross_long_eur": m.gross_long_eur,
            "cash_eur": m.cash_eur,
            "n_positions": m.n_positions,
            "n_options": m.n_open_options,
        })
    return pd.DataFrame(rows)
