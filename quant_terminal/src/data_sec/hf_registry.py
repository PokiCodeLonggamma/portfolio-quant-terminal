"""Hedge-fund registry loader.

A tiny YAML-backed registry of ~20 quant + discretionary funds we want to
follow on 13F-HR. Each row has:

  cik    : str   (10-digit zero-padded)
  name   : str
  bucket : Literal["Quant", "Macro", "Activist", "Value", "Growth", "Multi-Strat"]

The CIKs are sourced from SEC EDGAR full-text "browse-edgar" pages — see
the comment in `config/hf_registry.yaml` for provenance.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

from src.utils.logging import get_logger

log = get_logger(__name__)


_CFG_FILE = Path(__file__).resolve().parents[2] / "config" / "hf_registry.yaml"


@dataclass(frozen=True)
class HedgeFund:
    cik: str
    name: str
    bucket: str


def load_registry(yaml_path: Path | None = None) -> list[HedgeFund]:
    path = Path(yaml_path) if yaml_path else _CFG_FILE
    if not path.exists():
        log.warning("hedge-fund registry not found at %s", path)
        return []
    try:
        with path.open("r", encoding="utf-8") as fp:
            data = yaml.safe_load(fp) or {}
    except Exception as exc:
        log.warning("HF registry yaml read failed: %s", exc)
        return []
    out: list[HedgeFund] = []
    for row in data.get("funds", []):
        if not isinstance(row, dict):
            continue
        cik = str(row.get("cik", "")).zfill(10)
        name = str(row.get("name", "")).strip()
        bucket = str(row.get("bucket", "")).strip() or "Multi-Strat"
        if not cik or not name:
            continue
        out.append(HedgeFund(cik=cik, name=name, bucket=bucket))
    return out


def ciks_by_bucket(bucket: str | None = None) -> list[str]:
    funds = load_registry()
    if bucket is None:
        return [f.cik for f in funds]
    b = bucket.strip().lower()
    return [f.cik for f in funds if f.bucket.lower() == b]


def name_for_cik(cik: str) -> str | None:
    """Reverse lookup. Returns None when not in registry."""
    if not cik:
        return None
    cik10 = str(cik).strip().zfill(10)
    for f in load_registry():
        if f.cik == cik10:
            return f.name
    return None
