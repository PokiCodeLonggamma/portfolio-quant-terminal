"""Tiny parquet-backed cache so we don't hammer Alpaca/yfinance during dev."""
from __future__ import annotations

import hashlib
from pathlib import Path

import pandas as pd

from src.utils.config import get_config
from src.utils.logging import get_logger

log = get_logger(__name__)


def _key_to_path(key: str, namespace: str) -> Path:
    digest = hashlib.sha1(key.encode("utf-8")).hexdigest()[:16]
    safe = "".join(c for c in namespace if c.isalnum() or c in "_-")
    return get_config().cache_dir / f"{safe}__{digest}.parquet"


def read(key: str, namespace: str = "default", max_age_seconds: int | None = None) -> pd.DataFrame | None:
    path = _key_to_path(key, namespace)
    if not path.exists():
        return None
    if max_age_seconds is not None:
        import time
        if (time.time() - path.stat().st_mtime) > max_age_seconds:
            return None
    try:
        df = pd.read_parquet(path)
        log.debug("cache hit %s/%s -> %d rows", namespace, key, len(df))
        return df
    except Exception as exc:
        log.warning("cache read failed for %s: %s", path.name, exc)
        return None


def write(key: str, df: pd.DataFrame, namespace: str = "default") -> None:
    if df is None or df.empty:
        return
    path = _key_to_path(key, namespace)
    try:
        df.to_parquet(path, index=True)
        log.debug("cache write %s/%s (%d rows)", namespace, key, len(df))
    except Exception as exc:
        log.warning("cache write failed for %s: %s", path.name, exc)
