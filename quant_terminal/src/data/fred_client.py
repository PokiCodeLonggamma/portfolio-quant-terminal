"""Thin FRED wrapper. Optional — needs FRED_API_KEY in .env."""
from __future__ import annotations

import pandas as pd

from src.utils.config import get_config
from src.utils.logging import get_logger

log = get_logger(__name__)

# Useful macro series
SERIES = {
    "fed_funds": "DFF",
    "cpi": "CPIAUCSL",
    "ten_y": "DGS10",
    "two_y": "DGS2",
    "wti": "DCOILWTICO",
    "vix": "VIXCLS",
    "dxy": "DTWEXBGS",
}


def fetch(series_id: str) -> pd.Series | None:
    cfg = get_config()
    if not cfg.secrets.fred_api_key:
        log.info("FRED_API_KEY missing; skipping series %s", series_id)
        return None
    try:
        from fredapi import Fred
        f = Fred(api_key=cfg.secrets.fred_api_key)
        s = f.get_series(series_id)
        s.index = pd.to_datetime(s.index)
        s.name = series_id
        return s
    except Exception as exc:
        log.warning("FRED fetch failed for %s: %s", series_id, exc)
        return None


def fetch_macro_panel() -> pd.DataFrame:
    panel: dict[str, pd.Series] = {}
    for label, sid in SERIES.items():
        s = fetch(sid)
        if s is not None:
            panel[label] = s
    if not panel:
        return pd.DataFrame()
    return pd.concat(panel.values(), axis=1, keys=panel.keys()).sort_index()
