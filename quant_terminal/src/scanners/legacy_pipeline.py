"""Adapter for the vendored short-squeeze scanner under `vendor/legacy_squeeze/`.

The legacy package uses absolute imports of the form ``from src.x import y`` and
``from config.settings import Config``. We cannot satisfy those imports while
*our* ``src`` package is on ``sys.path`` first. This module solves that with a
context manager that:

  1. Pops every cached ``src.*`` / ``config.*`` module out of ``sys.modules``
     and stashes them.
  2. Prepends the legacy package root to ``sys.path``.
  3. Executes the user's call so the legacy code's ``from src.*`` imports
     resolve against the legacy tree.
  4. On exit, removes the legacy module entries and restores our own.

The legacy code itself is **NEVER modified** — see vendor/README.md.

Public API
----------
* ``legacy_scan_single_ticker(ticker) -> dict``  (4-pillar score as a flat dict)
* ``legacy_scan_universe(tickers) -> pd.DataFrame``
"""
from __future__ import annotations

import logging
import sys
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterable

import pandas as pd

log = logging.getLogger(__name__)

LEGACY_ROOT = (Path(__file__).resolve().parents[2] / "vendor" / "legacy_squeeze").resolve()


def legacy_available() -> bool:
    """Quick smoke-check: does the vendor mirror exist?"""
    return (LEGACY_ROOT / "src" / "main.py").exists()


@contextmanager
def _legacy_namespace():
    """Temporarily route ``src`` and ``config`` imports to the legacy mirror."""
    saved: dict[str, Any] = {}
    legacy_str = str(LEGACY_ROOT)
    prefixes = ("src", "src.", "config", "config.")

    # 1. Save (and remove) any cached module that would collide.
    for key in list(sys.modules):
        if key == "src" or key == "config" or any(key.startswith(p) for p in prefixes if p.endswith(".")):
            saved[key] = sys.modules.pop(key)

    # 2. Add the legacy root to the front of sys.path.
    inserted = False
    if legacy_str not in sys.path:
        sys.path.insert(0, legacy_str)
        inserted = True

    try:
        yield
    finally:
        # 3. Tear down legacy entries so future imports resolve to *our* tree.
        for key in list(sys.modules):
            if key == "src" or key == "config" or any(key.startswith(p) for p in prefixes if p.endswith(".")):
                del sys.modules[key]
        # 4. Restore our previously-cached modules.
        sys.modules.update(saved)
        if inserted:
            try:
                sys.path.remove(legacy_str)
            except ValueError:
                pass


# ---------------------------------------------------------------------------
# Result flattening
# ---------------------------------------------------------------------------
def _score_to_row(score) -> dict[str, Any]:
    """Flatten a legacy ``TickerScore`` to a flat dict for DataFrame display."""
    return {
        "ticker": getattr(score, "ticker", "?"),
        "signal": getattr(score, "signal", "—"),
        "score_total": round(float(getattr(score, "total", 0.0)), 2),
        "score_fundamental": round(float(getattr(score, "fundamental", 0.0)), 2),
        "score_technical_bonus": round(float(getattr(score, "technical_bonus", 0.0)), 2),
        "pillar1_vad": round(float(getattr(score.pillar1, "score", 0.0)), 2),
        "pillar2_inst": round(float(getattr(score.pillar2, "score", 0.0)), 2),
        "pillar3_div": round(float(getattr(score.pillar3, "score", 0.0)), 2),
        "pillar4_tech": round(float(getattr(score.pillar4, "score", 0.0)), 2),
        "squeeze_phase": getattr(score, "squeeze_phase", "") or "",
        "short_float": float(getattr(score, "short_float_raw", 0.0) or 0.0),
        "days_to_cover": float(getattr(score, "dtc_raw", 0.0) or 0.0),
        "inst_trans": float(getattr(score, "inst_trans_raw", 0.0) or 0.0),
        "price": float(getattr(score, "price", 0.0) or 0.0),
        "market_cap": float(getattr(score, "market_cap", 0.0) or 0.0),
        "sector": getattr(score, "sector", "") or "",
        "pillar1_details": dict(getattr(score.pillar1, "details", {}) or {}),
        "pillar2_details": dict(getattr(score.pillar2, "details", {}) or {}),
        "pillar3_details": dict(getattr(score.pillar3, "details", {}) or {}),
        "pillar4_details": dict(getattr(score.pillar4, "details", {}) or {}),
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def legacy_scan_single_ticker(ticker: str) -> dict[str, Any] | None:
    """Run the legacy 4-pillar scan on a single ticker.

    Returns ``None`` if the legacy package cannot be loaded.
    """
    if not legacy_available():
        log.warning("legacy_squeeze mirror missing at %s", LEGACY_ROOT)
        return None
    with _legacy_namespace():
        try:
            from src.main import scan_single_ticker
            from src.storage.database import init_db
        except Exception as exc:
            log.error("legacy import failed: %s", exc)
            return None
        try:
            init_db()
            score = scan_single_ticker(ticker.upper())
        except Exception as exc:
            log.error("legacy scan_single_ticker(%s) failed: %s", ticker, exc)
            return None
    return _score_to_row(score) if score is not None else None


def legacy_scan_universe(tickers: Iterable[str]) -> pd.DataFrame:
    """Run the legacy scan ticker-by-ticker over a list (no Finviz screening)."""
    rows: list[dict[str, Any]] = []
    for t in tickers:
        try:
            r = legacy_scan_single_ticker(t)
        except Exception as exc:
            log.warning("legacy scan failed for %s: %s", t, exc)
            continue
        if r is not None:
            rows.append(r)
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows).sort_values("score_total", ascending=False).reset_index(drop=True)
    return df


def legacy_run_full_scan() -> pd.DataFrame:
    """Run the legacy Finviz-screened full scan (3–8 minutes typical)."""
    if not legacy_available():
        return pd.DataFrame()
    with _legacy_namespace():
        try:
            from src.main import run_full_scan
            from src.storage.database import init_db
        except Exception as exc:
            log.error("legacy import failed: %s", exc)
            return pd.DataFrame()
        try:
            init_db()
            scores = run_full_scan()
        except Exception as exc:
            log.error("legacy run_full_scan failed: %s", exc)
            return pd.DataFrame()
    if not scores:
        return pd.DataFrame()
    df = pd.DataFrame([_score_to_row(s) for s in scores])
    return df.sort_values("score_total", ascending=False).reset_index(drop=True)
