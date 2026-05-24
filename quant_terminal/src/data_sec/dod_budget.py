"""DoD program-by-program budget reader.

Sourced from public FY26 PB-26 documents; we maintain the data as a YAML
file so the user can edit allocations between Congressional adjustments
without code changes. See `config/dod_programs.yaml`.

Returned DataFrame schema:
  program           : str  (e.g. "Sentinel ICBM")
  ticker_exposure   : str  (csv list of universe tickers)
  fy_usd_billion    : float
  source_note       : str
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import yaml

from src.utils.logging import get_logger

log = get_logger(__name__)


_CFG_FILE = Path(__file__).resolve().parents[2] / "config" / "dod_programs.yaml"


_PANEL_COLS = ["program", "ticker_exposure", "fy_usd_billion", "source_note"]


def budget_allocations(yaml_path: Path | None = None) -> pd.DataFrame:
    path = Path(yaml_path) if yaml_path else _CFG_FILE
    if not path.exists():
        log.warning("DoD config not found at %s", path)
        return pd.DataFrame(columns=_PANEL_COLS)
    try:
        with path.open("r", encoding="utf-8") as fp:
            data = yaml.safe_load(fp) or {}
    except Exception as exc:
        log.warning("DoD yaml read failed: %s", exc)
        return pd.DataFrame(columns=_PANEL_COLS)

    rows = []
    for prog in data.get("programs", []):
        if not isinstance(prog, dict):
            continue
        tickers = prog.get("tickers") or []
        rows.append({
            "program": str(prog.get("name", "")),
            "ticker_exposure": ",".join(str(t).upper() for t in tickers),
            "fy_usd_billion": float(prog.get("fy_usd_billion", 0.0)),
            "source_note": str(prog.get("source", "")),
        })
    if not rows:
        return pd.DataFrame(columns=_PANEL_COLS)
    return pd.DataFrame(rows).sort_values("fy_usd_billion", ascending=False).reset_index(drop=True)
