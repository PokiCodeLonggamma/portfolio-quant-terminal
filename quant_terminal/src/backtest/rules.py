"""Personal risk rules — Protocol-based, composable, vectorised.

Each rule implements :class:`Rule.evaluate(weights, prices_eur, ts)` and
returns the **adjusted weight vector** for the current bar. The engine
applies rules in order; the output of rule *i* feeds rule *i+1*.

Convention
----------
- `weights` is a pd.Series indexed by universe_key. Sums to ≤ 1 (residual
  is cash). A weight of 0 means "fully out / parked in cash".
- `prices_eur` is a wide DataFrame (date x universe_key) of EUR-normalised
  prices. The engine slices history up to and including ``ts`` before
  calling the rule.
- `ts` is the current evaluation timestamp (a row of ``prices_eur.index``).

Rules MUST be:
- pure (no I/O, no global state)
- idempotent when re-applied to the same inputs
- safe to call on degenerate inputs (empty weights, single-row prices, NaN)

Triggered rules typically scale weights down; the freed allocation lands
in cash automatically (since `cash_weight = 1 - weights.sum()`).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

import numpy as np
import pandas as pd


# ---------------------------------------------------------------------------
# Protocol
# ---------------------------------------------------------------------------
@runtime_checkable
class Rule(Protocol):
    """Structural type for a backtest risk rule.

    Implementations are dataclasses, but any object exposing ``name`` plus a
    compatible ``evaluate`` method is accepted by the engine.
    """

    name: str

    def evaluate(
        self,
        weights: pd.Series,
        prices_eur: pd.DataFrame,
        ts: pd.Timestamp,
    ) -> pd.Series:  # pragma: no cover - Protocol
        ...


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _normalise(w: pd.Series) -> pd.Series:
    """Clip negative weights to zero. Does **not** rescale to sum to 1
    because we want to keep an explicit cash bucket."""
    return w.clip(lower=0.0).astype(float)


def _redistribute_excess(w: pd.Series, capped_keys: list[str], excess: float) -> pd.Series:
    """Pro-rata redistribute `excess` weight onto the *uncapped* positions.

    If every position is capped, the excess stays in cash.
    """
    out = w.copy()
    free_mask = ~out.index.isin(capped_keys)
    free = out[free_mask]
    free_sum = float(free.sum())
    if free_sum <= 0.0 or excess <= 0.0:
        # Nothing to redistribute onto -> excess goes to cash.
        return out
    out.loc[free_mask] = free + (free / free_sum) * excess
    return out


# ---------------------------------------------------------------------------
# MaxSinglePosition
# ---------------------------------------------------------------------------
@dataclass
class MaxSinglePositionRule:
    """Cap each line at ``max_pct`` of total exposure, redistribute pro-rata.

    Parameters
    ----------
    max_pct : float
        Maximum weight per single position, e.g. ``0.20`` for 20%.
        Applied iteratively to handle cascading caps.
    name : str
        Display name surfaced in the trigger log.
    """

    max_pct: float
    name: str = "max_single_position"

    def __post_init__(self) -> None:
        if not (0.0 < self.max_pct <= 1.0):
            raise ValueError(f"max_pct must be in (0, 1]; got {self.max_pct}")

    def evaluate(
        self,
        weights: pd.Series,
        prices_eur: pd.DataFrame,  # noqa: ARG002 - kept for Protocol
        ts: pd.Timestamp,  # noqa: ARG002
    ) -> pd.Series:
        w = _normalise(weights)
        if w.empty:
            return w

        # Iterate: capping a line frees weight that gets pushed onto others,
        # which may themselves end up above the cap. We track cumulative
        # capped keys so redistribution never spills back onto an
        # already-capped line (avoids float drift above max_pct).
        all_capped: set[str] = set()
        for _ in range(10):
            over_mask = w > self.max_pct + 1e-12
            if not over_mask.any():
                break
            newly_capped = w.index[over_mask].tolist()
            all_capped.update(newly_capped)
            excess = float((w[over_mask] - self.max_pct).sum())
            w.loc[over_mask] = self.max_pct
            w = _redistribute_excess(w, list(all_capped), excess)
        # Final safety clip — guarantees no float epsilon above cap.
        w = w.clip(upper=self.max_pct)
        return w


# ---------------------------------------------------------------------------
# MaxDrawdownTrigger
# ---------------------------------------------------------------------------
@dataclass
class MaxDrawdownTriggerRule:
    """When the portfolio's rolling drawdown exceeds ``threshold_pct``,
    scale every weight by ``derisk_pct`` and park the rest in cash.

    The trigger is computed from the running NAV that the engine threads in
    via the ``_nav_hint`` attribute on ``weights`` (a pd.Series.attrs convention).
    If the engine has not threaded a NAV history, the rule is a no-op.

    Parameters
    ----------
    threshold_pct : float
        Drawdown threshold expressed as a **positive** fraction, e.g.
        ``0.10`` triggers when rolling DD ≤ -10%.
    derisk_pct : float
        Multiplier applied to every position, e.g. ``0.5`` halves all
        exposures.
    """

    threshold_pct: float
    derisk_pct: float
    name: str = "max_drawdown_trigger"

    def __post_init__(self) -> None:
        if not (0.0 < self.threshold_pct <= 1.0):
            raise ValueError("threshold_pct must be in (0, 1]")
        if not (0.0 <= self.derisk_pct <= 1.0):
            raise ValueError("derisk_pct must be in [0, 1]")

    def evaluate(
        self,
        weights: pd.Series,
        prices_eur: pd.DataFrame,  # noqa: ARG002
        ts: pd.Timestamp,  # noqa: ARG002
    ) -> pd.Series:
        w = _normalise(weights)
        if w.empty:
            return w

        nav_hist = weights.attrs.get("_nav_hint")
        if nav_hist is None or len(nav_hist) < 2:
            return w
        nav = pd.Series(nav_hist, dtype=float)
        peak = float(nav.cummax().iloc[-1])
        last = float(nav.iloc[-1])
        if peak <= 0:
            return w
        dd = last / peak - 1.0  # negative when below peak
        if dd <= -abs(self.threshold_pct):
            return w * float(self.derisk_pct)
        return w


# ---------------------------------------------------------------------------
# MaxThemeCap
# ---------------------------------------------------------------------------
@dataclass
class MaxThemeCapRule:
    """Cap aggregate exposure per theme.

    Parameters
    ----------
    theme_map : dict[str, str]
        universe_key -> theme label.
    max_pct : float
        Maximum aggregate weight per theme.
    """

    theme_map: dict[str, str]
    max_pct: float
    name: str = "max_theme_cap"

    def __post_init__(self) -> None:
        if not (0.0 < self.max_pct <= 1.0):
            raise ValueError("max_pct must be in (0, 1]")

    def evaluate(
        self,
        weights: pd.Series,
        prices_eur: pd.DataFrame,  # noqa: ARG002
        ts: pd.Timestamp,  # noqa: ARG002
    ) -> pd.Series:
        w = _normalise(weights)
        if w.empty:
            return w
        themes = pd.Series({k: self.theme_map.get(k, "Unclassified") for k in w.index})
        # Aggregate weight per theme
        theme_totals = w.groupby(themes).sum()
        offending = theme_totals[theme_totals > self.max_pct]
        if offending.empty:
            return w
        out = w.copy()
        for theme, total in offending.items():
            mask = themes == theme
            scale = float(self.max_pct) / float(total)
            out.loc[mask] = out.loc[mask] * scale
        return out


# ---------------------------------------------------------------------------
# StopLoss (per-position trailing)
# ---------------------------------------------------------------------------
@dataclass
class StopLossRule:
    """Exit a position to cash once it has lost ``per_position_pct`` from
    its trailing peak.

    The engine threads the per-position entry/peak history via
    ``weights.attrs['_peak_prices']`` (a dict of universe_key -> peak price).
    If not provided, the rule walks the supplied price history itself.

    Parameters
    ----------
    per_position_pct : float
        Positive fraction. e.g. ``0.15`` exits when price ≤ 0.85 * peak.
    """

    per_position_pct: float
    name: str = "stop_loss"

    def __post_init__(self) -> None:
        if not (0.0 < self.per_position_pct <= 1.0):
            raise ValueError("per_position_pct must be in (0, 1]")

    def evaluate(
        self,
        weights: pd.Series,
        prices_eur: pd.DataFrame,
        ts: pd.Timestamp,
    ) -> pd.Series:
        w = _normalise(weights)
        if w.empty:
            return w

        peaks = weights.attrs.get("_peak_prices", {})
        # Slice prices up to ts; compute fallback peaks from raw history if engine
        # has not provided them yet (first-bar protection).
        hist = prices_eur.loc[:ts]
        if hist.empty:
            return w
        last_prices = hist.iloc[-1]

        out = w.copy()
        for key in out.index:
            if key not in last_prices.index:
                continue
            last = float(last_prices[key])
            if not np.isfinite(last) or last <= 0:
                continue
            peak = float(peaks.get(key, np.nan))
            if not np.isfinite(peak) or peak <= 0:
                # Fallback: peak across the supplied history.
                series = hist[key].dropna()
                if series.empty:
                    continue
                peak = float(series.cummax().iloc[-1])
            if peak <= 0:
                continue
            dd = last / peak - 1.0
            if dd <= -abs(self.per_position_pct):
                out[key] = 0.0
        return out


# ---------------------------------------------------------------------------
# MomentumEntry (gate)
# ---------------------------------------------------------------------------
@dataclass
class MomentumEntryRule:
    """Only allow exposure on names whose N-day return exceeds ``threshold``.

    Useful as an *entry gate*: positions whose N-day momentum is below the
    threshold are flattened (sent to cash). When momentum recovers, the
    position re-enters at its baseline target weight (provided upstream
    rules don't override).

    Parameters
    ----------
    lookback_days : int
        Window length for the simple return.
    threshold : float
        Minimum return over the window, e.g. ``0.0`` for "trend up only".
    """

    lookback_days: int
    threshold: float
    name: str = "momentum_entry"

    def __post_init__(self) -> None:
        if self.lookback_days < 2:
            raise ValueError("lookback_days must be >= 2")

    def evaluate(
        self,
        weights: pd.Series,
        prices_eur: pd.DataFrame,
        ts: pd.Timestamp,
    ) -> pd.Series:
        w = _normalise(weights)
        if w.empty:
            return w

        hist = prices_eur.loc[:ts]
        if len(hist) < self.lookback_days + 1:
            # Not enough history -> stay neutral, keep weights as-is.
            return w

        window = hist.iloc[-(self.lookback_days + 1) :]
        first = window.iloc[0]
        last = window.iloc[-1]
        # Compute per-asset momentum; treat NaN as failing the gate (= flatten).
        with np.errstate(divide="ignore", invalid="ignore"):
            mom = (last / first) - 1.0
        out = w.copy()
        for key in out.index:
            m = float(mom.get(key, np.nan)) if key in mom.index else np.nan
            if not np.isfinite(m) or m < self.threshold:
                out[key] = 0.0
        return out


# ---------------------------------------------------------------------------
# Registry helpers
# ---------------------------------------------------------------------------
@dataclass
class RuleSpec:
    """Lightweight serialisable handle for the Streamlit picker.

    The dashboard surfaces these and the engine instantiates the concrete
    Rule on demand.
    """

    rule_name: str
    params: dict = field(default_factory=dict)


_FACTORY: dict[str, type] = {
    "max_single_position": MaxSinglePositionRule,
    "max_drawdown_trigger": MaxDrawdownTriggerRule,
    "max_theme_cap": MaxThemeCapRule,
    "stop_loss": StopLossRule,
    "momentum_entry": MomentumEntryRule,
}


def build_rule(spec: RuleSpec) -> Rule:
    """Instantiate a concrete rule from a :class:`RuleSpec`."""
    cls = _FACTORY.get(spec.rule_name)
    if cls is None:
        raise KeyError(f"Unknown rule: {spec.rule_name!r}. Known: {sorted(_FACTORY)}")
    return cls(**spec.params)


def available_rules() -> list[str]:
    """Return the rule names exposed by :func:`build_rule`."""
    return sorted(_FACTORY)
