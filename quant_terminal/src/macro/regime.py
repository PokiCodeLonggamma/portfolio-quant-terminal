"""Regime classifier — 2x2x2 lattice on the FRED macro panel.

Axes (boolean each):
    * inflation: ``high`` if CPI YoY > 3%, else ``low``
    * growth:    ``low``  if PMI proxy < 50, else ``high``  (neutral PMI = high
                 — when PMI is unavailable we fall back to T10Y3M ≤ 0 = low)
    * policy:    ``tight`` if DFF moved up by > 0 over the past 6 months
                 (i.e. tightening cycle), else ``loose``

The 8 boxes have human-readable labels (Goldilocks, Stagflation, etc.) so
the UI can show one badge per regime change.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import numpy as np
import pandas as pd

from src.common.schemas import RegimeSnapshot
from src.macro.fred_series import build_macro_panel
from src.utils.cache import read as cache_read, write as cache_write
from src.utils.logging import get_logger

log = get_logger(__name__)

NAMESPACE = "regime"
CACHE_TTL_SECONDS = 60 * 60 * 6

# Thresholds (mirror config/regime_thresholds.yaml when that file ships)
CPI_HIGH_THRESHOLD = 3.0          # YoY %
PMI_LOW_THRESHOLD = 50.0          # diffusion index
DFF_TIGHT_LOOKBACK_BDAYS = 126    # ~6 months of business days
DFF_TIGHT_DELTA_BPS = 0.0         # any positive 6m change = tight cycle

# 2x2x2 regime label lattice
_REGIME_LABELS: dict[tuple[str, str, str], str] = {
    ("high", "high", "tight"):  "Late-cycle inflation",
    ("high", "high", "loose"):  "Reflation",
    ("high", "low",  "tight"):  "Stagflation",
    ("high", "low",  "loose"):  "Stagflation (easing)",
    ("low",  "high", "tight"):  "Disinflationary boom",
    ("low",  "high", "loose"):  "Goldilocks",
    ("low",  "low",  "tight"):  "Deflationary squeeze",
    ("low",  "low",  "loose"):  "Recessionary easing",
}


# ---------------------------------------------------------------------------
# Per-axis classification primitives
# ---------------------------------------------------------------------------
def _classify_inflation(cpi_yoy: float | None) -> str:
    if cpi_yoy is None or not np.isfinite(cpi_yoy):
        return "low"
    return "high" if cpi_yoy > CPI_HIGH_THRESHOLD else "low"


def _classify_growth(pmi_proxy: float | None, t10y3m: float | None) -> str:
    """PMI < 50 = low growth. Fallback: inverted curve (T10Y3M ≤ 0) = low."""
    if pmi_proxy is not None and np.isfinite(pmi_proxy):
        return "low" if pmi_proxy < PMI_LOW_THRESHOLD else "high"
    if t10y3m is not None and np.isfinite(t10y3m):
        return "low" if t10y3m <= 0 else "high"
    return "high"


def _classify_policy(dff_now: float | None, dff_6m_ago: float | None) -> str:
    if dff_now is None or dff_6m_ago is None:
        return "loose"
    if not (np.isfinite(dff_now) and np.isfinite(dff_6m_ago)):
        return "loose"
    delta = dff_now - dff_6m_ago
    return "tight" if delta > DFF_TIGHT_DELTA_BPS else "loose"


def _label_for(inflation: str, growth: str, policy: str) -> str:
    return _REGIME_LABELS.get((inflation, growth, policy), "Unclassified")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def classify_regime_from_panel(panel: pd.DataFrame, asof: date | None = None) -> RegimeSnapshot:
    """Classify the regime at ``asof`` (default: last row of ``panel``)."""
    if panel is None or panel.empty:
        # Deterministic fallback so the dashboard always renders.
        target = asof or date.today()
        return RegimeSnapshot(
            asof=target,
            inflation="low",
            growth="high",
            policy="loose",
            label="Goldilocks",
            confidence=0.0,
            metrics={},
        )

    p = panel.copy()
    p.index = pd.to_datetime(p.index)

    if asof is None:
        target_ts = p.index[-1]
    else:
        target_ts = pd.Timestamp(asof)
        # Snap to last available row at or before asof
        idx = p.index[p.index <= target_ts]
        if len(idx) == 0:
            target_ts = p.index[0]
        else:
            target_ts = idx[-1]

    row = p.loc[target_ts]
    cpi_yoy = float(row.get("cpi_yoy", np.nan)) if "cpi_yoy" in p.columns else np.nan
    pmi_proxy = float(row.get("pmi_proxy", np.nan)) if "pmi_proxy" in p.columns else np.nan
    t10y3m = float(row.get("t10y3m", np.nan)) if "t10y3m" in p.columns else np.nan
    dff_now = float(row.get("dff", np.nan)) if "dff" in p.columns else np.nan

    dff_6m_ago: float | None = None
    if "dff" in p.columns:
        lookback_ts = target_ts - pd.Timedelta(days=int(DFF_TIGHT_LOOKBACK_BDAYS * 7 / 5))
        prior = p["dff"].loc[:lookback_ts].dropna()
        if not prior.empty:
            dff_6m_ago = float(prior.iloc[-1])

    inflation = _classify_inflation(cpi_yoy if np.isfinite(cpi_yoy) else None)
    growth = _classify_growth(
        pmi_proxy if np.isfinite(pmi_proxy) else None,
        t10y3m if np.isfinite(t10y3m) else None,
    )
    policy = _classify_policy(
        dff_now if np.isfinite(dff_now) else None,
        dff_6m_ago,
    )

    metrics: dict[str, float] = {}
    for col in p.columns:
        v = row.get(col, np.nan)
        try:
            vf = float(v)
        except (TypeError, ValueError):
            continue
        if np.isfinite(vf):
            metrics[col] = vf
    if dff_6m_ago is not None:
        metrics["dff_6m_ago"] = dff_6m_ago
        metrics["dff_6m_delta"] = (dff_now - dff_6m_ago) if np.isfinite(dff_now) else 0.0

    # Confidence: proportion of axes whose primary signal was present
    present = sum([
        1.0 if np.isfinite(cpi_yoy) else 0.0,
        1.0 if np.isfinite(pmi_proxy) else (0.5 if np.isfinite(t10y3m) else 0.0),
        1.0 if dff_6m_ago is not None else 0.0,
    ])
    confidence = round(present / 3.0, 2)

    return RegimeSnapshot(
        asof=target_ts.date() if hasattr(target_ts, "date") else (asof or date.today()),
        inflation=inflation,
        growth=growth,
        policy=policy,
        label=_label_for(inflation, growth, policy),
        confidence=confidence,
        metrics=metrics,
    )


def classify_regime(asof: date | None = None) -> RegimeSnapshot:
    """Classify the current macro regime, fetching the FRED panel on demand."""
    panel = build_macro_panel()
    return classify_regime_from_panel(panel, asof=asof)


def regime_history(panel: pd.DataFrame | None = None, *, freq: str = "W") -> pd.DataFrame:
    """Compute a regime snapshot for every ``freq`` step of ``panel``.

    Returns columns: date, inflation, growth, policy, label, confidence.
    """
    if panel is None:
        panel = build_macro_panel()
    if panel is None or panel.empty:
        return pd.DataFrame(columns=["date", "inflation", "growth", "policy", "label", "confidence"])

    sample_idx = panel.resample(freq).last().index
    rows: list[dict] = []
    for ts in sample_idx:
        snap = classify_regime_from_panel(panel, asof=ts.date())
        rows.append({
            "date": snap.asof,
            "inflation": snap.inflation,
            "growth": snap.growth,
            "policy": snap.policy,
            "label": snap.label,
            "confidence": snap.confidence,
        })
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Dataclass mirror (some callers prefer a plain dataclass)
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class RegimeTuple:
    inflation: str
    growth: str
    policy: str
    label: str

    @classmethod
    def from_snapshot(cls, snap: RegimeSnapshot) -> "RegimeTuple":
        return cls(snap.inflation, snap.growth, snap.policy, snap.label)
