"""Hyperscaler CapEx quarterly reader.

The data lives in `config/hyperscaler_capex.yaml` so the user can edit
post-earnings without code changes. Returned panel:

  quarter | msft | meta | goog | amzn | orcl | total

All values are USD billions.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import yaml

from src.utils.logging import get_logger

log = get_logger(__name__)


_CFG_FILE = Path(__file__).resolve().parents[2] / "config" / "hyperscaler_capex.yaml"

_HYPERSCALERS: list[str] = ["msft", "meta", "goog", "amzn", "orcl"]


def capex_panel(yaml_path: Path | None = None) -> pd.DataFrame:
    path = Path(yaml_path) if yaml_path else _CFG_FILE
    if not path.exists():
        log.warning("hyperscaler capex config not found at %s", path)
        cols = ["quarter", *_HYPERSCALERS, "total"]
        return pd.DataFrame(columns=cols)
    try:
        with path.open("r", encoding="utf-8") as fp:
            data = yaml.safe_load(fp) or {}
    except Exception as exc:
        log.warning("capex yaml read failed: %s", exc)
        cols = ["quarter", *_HYPERSCALERS, "total"]
        return pd.DataFrame(columns=cols)

    rows = []
    for q in data.get("quarters", []):
        if not isinstance(q, dict):
            continue
        row = {"quarter": str(q.get("quarter", ""))}
        for hs in _HYPERSCALERS:
            row[hs] = float(q.get(hs, 0.0))
        row["total"] = float(sum(row[h] for h in _HYPERSCALERS))
        rows.append(row)
    if not rows:
        cols = ["quarter", *_HYPERSCALERS, "total"]
        return pd.DataFrame(columns=cols)
    df = pd.DataFrame(rows)[["quarter", *_HYPERSCALERS, "total"]]
    return df.sort_values("quarter").reset_index(drop=True)
