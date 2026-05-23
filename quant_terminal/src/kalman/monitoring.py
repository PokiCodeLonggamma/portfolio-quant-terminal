"""Kalman Elastic Trading — monitoring template.

This module is a thin reader: it expects the live Kalman pipeline (the
PokiCodeLonggamma/Kalman_Filter_XGBoost repo) to drop its run artefacts
into a known directory. The dashboard tab consumes whatever it finds.

Default artefacts directory:  <repo-root>/data/kalman_artefacts/
You can point elsewhere via env var QUANT_TERMINAL_KALMAN_ARTEFACTS.

Expected files (all optional — UI degrades gracefully):
    equity.csv          # daily NAV, columns: date, equity
    trades.csv          # one row per trade, with PnL_pct, side, ticker, ...
    metrics_phase2.json # Phase 2 industrialised metrics
    metrics_phase3.json # Phase 3 ML metrics
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import pandas as pd

from src.utils.config import PROJECT_ROOT
from src.utils.logging import get_logger

log = get_logger(__name__)


def artefacts_dir() -> Path:
    custom = os.getenv("QUANT_TERMINAL_KALMAN_ARTEFACTS")
    if custom:
        return Path(custom).expanduser().resolve()
    return (PROJECT_ROOT / "data" / "kalman_artefacts").resolve()


@dataclass
class KalmanRun:
    equity: pd.DataFrame
    trades: pd.DataFrame
    metrics_phase2: dict
    metrics_phase3: dict

    @property
    def is_empty(self) -> bool:
        return self.equity.empty and self.trades.empty and not self.metrics_phase2 and not self.metrics_phase3

    @property
    def total_trades(self) -> int:
        return len(self.trades)

    @property
    def win_rate(self) -> float:
        if self.trades.empty or "PnL_pct" not in self.trades.columns:
            return 0.0
        winners = (self.trades["PnL_pct"] > 0).sum()
        return float(winners) / max(1, len(self.trades))

    @property
    def last_equity_date(self) -> datetime | None:
        if self.equity.empty:
            return None
        return pd.to_datetime(self.equity["date"]).max().to_pydatetime()


def load_run(directory: Path | None = None) -> KalmanRun:
    d = directory or artefacts_dir()
    equity = _safe_read_csv(d / "equity.csv")
    trades = _safe_read_csv(d / "trades.csv")
    return KalmanRun(
        equity=equity,
        trades=trades,
        metrics_phase2=_safe_read_json(d / "metrics_phase2.json"),
        metrics_phase3=_safe_read_json(d / "metrics_phase3.json"),
    )


def _safe_read_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    try:
        return pd.read_csv(path)
    except Exception as exc:
        log.warning("Could not read %s: %s", path, exc)
        return pd.DataFrame()


def _safe_read_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        log.warning("Could not read %s: %s", path, exc)
        return {}
