"""Backtest simulation engine — applies a stack of :class:`Rule` objects
to a portfolio of EUR-normalised price history.

Design choices
--------------
- Daily-bar replay. The portfolio holds a vector of target weights; each
  bar, we revalue using realised returns, apply rules, then optionally
  rebalance at the period boundary.
- Cash earns nothing (rf = 0). The residual ``1 - weights.sum()`` lives
  in cash and shocks-absorb when rules de-risk.
- Two NAV traces are produced in a single pass to keep things cheap:
  the **baseline** (no rules, pure buy-and-hold rebalanced on the same
  cadence) and the **ruled** NAV.
- Trigger events are logged per (timestamp, rule) so the dashboard can
  render a transparent audit trail.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Literal

import numpy as np
import pandas as pd

from src.backtest.rules import Rule
from src.utils.logging import get_logger

log = get_logger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _rebalance_index(
    index: pd.DatetimeIndex, freq: str
) -> set[pd.Timestamp]:
    """Return the set of bars at which we rebalance to target weights.

    ``freq`` accepts pandas offset aliases: ``"M"``, ``"Q"``, ``"W"``, ``"D"``,
    or the literal ``"never"``.
    """
    if freq.lower() == "never":
        return set()
    if freq.upper() == "D":
        return set(index)
    # Use the *last* trading day inside each pandas period as the rebalance bar.
    try:
        grouped = pd.Series(index, index=index).groupby(
            pd.Grouper(freq=freq)
        ).max()
    except (ValueError, TypeError):
        log.warning("Unknown rebalance freq %s -- defaulting to monthly", freq)
        grouped = pd.Series(index, index=index).groupby(
            pd.Grouper(freq="M")
        ).max()
    return set(pd.to_datetime(grouped.dropna().values))


def _align_weights(
    initial_weights: pd.Series, columns: Iterable[str]
) -> pd.Series:
    cols = list(columns)
    w = initial_weights.reindex(cols).fillna(0.0).astype(float).clip(lower=0.0)
    total = float(w.sum())
    if total > 1.0:
        # Rescale so total exposure <= 1 (residual = cash bucket).
        w = w / total
    return w


def _apply_rule_stack(
    rules: list[Rule],
    weights: pd.Series,
    prices_eur: pd.DataFrame,
    ts: pd.Timestamp,
    nav_history: list[float],
    peak_prices: dict[str, float],
) -> tuple[pd.Series, list[dict]]:
    """Apply rules in sequence; log any rule that changes the vector."""
    triggers: list[dict] = []
    current = weights.copy()
    # Thread hints used by some rules (DD trigger, stop-loss) via attrs.
    current.attrs["_nav_hint"] = list(nav_history)
    current.attrs["_peak_prices"] = dict(peak_prices)

    for rule in rules:
        before = current.copy()
        after = rule.evaluate(before, prices_eur, ts)
        # The Protocol does not enforce attrs propagation; rehydrate them so
        # subsequent rules in the stack still benefit from the same hints.
        after = after.copy()
        after.attrs["_nav_hint"] = current.attrs["_nav_hint"]
        after.attrs["_peak_prices"] = current.attrs["_peak_prices"]

        if not np.allclose(
            before.fillna(0.0).values, after.fillna(0.0).values, atol=1e-9
        ):
            triggers.append(
                {
                    "ts": ts,
                    "rule": getattr(rule, "name", rule.__class__.__name__),
                    "weight_delta": float(after.sum() - before.sum()),
                    "n_positions_changed": int(
                        (~np.isclose(before.values, after.values, atol=1e-9)).sum()
                    ),
                }
            )
        current = after
    # Drop the hints from the returned series so they don't leak globally.
    current.attrs.pop("_nav_hint", None)
    current.attrs.pop("_peak_prices", None)
    return current, triggers


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
@dataclass
class SimulationResult:
    """Full simulation output.

    Attributes
    ----------
    history : pd.DataFrame
        Indexed by date with columns ``nav_baseline``, ``nav_ruled``,
        ``cash_ruled``, ``exposure_ruled``, plus per-asset ruled weights
        prefixed by ``w_``.
    triggers : pd.DataFrame
        Tidy log of rule firings (ts, rule, n_positions_changed, weight_delta).
    initial_eur : float
        Starting capital.
    """

    history: pd.DataFrame
    triggers: pd.DataFrame
    initial_eur: float

    @property
    def baseline_nav(self) -> pd.Series:
        return self.history["nav_baseline"].astype(float)

    @property
    def ruled_nav(self) -> pd.Series:
        return self.history["nav_ruled"].astype(float)


def simulate(
    prices_eur: pd.DataFrame,
    initial_weights: pd.Series,
    rules: list[Rule] | None = None,
    rebalance_freq: Literal["never", "D", "W", "M", "Q"] = "M",
    initial_eur: float = 10_000.0,
) -> SimulationResult:
    """Run the daily-bar backtest.

    Parameters
    ----------
    prices_eur : pd.DataFrame
        Wide panel of EUR prices (date x universe_key). NaNs are forward-filled
        internally to keep returns finite.
    initial_weights : pd.Series
        Target weights at t=0 (universe_key -> weight). Residual is cash.
    rules : list[Rule] | None
        Stack of rules applied IN ORDER each bar. ``None`` => buy-and-hold
        (still rebalanced on cadence).
    rebalance_freq : str
        ``"never" | "D" | "W" | "M" | "Q"``. The ruled portfolio re-applies
        the rule stack each bar regardless, but only realigns to target
        weights at period boundaries.
    initial_eur : float
        Starting capital in EUR.

    Returns
    -------
    SimulationResult
    """
    rules = list(rules or [])
    if prices_eur is None or prices_eur.empty:
        return SimulationResult(
            history=pd.DataFrame(),
            triggers=pd.DataFrame(columns=["ts", "rule", "n_positions_changed", "weight_delta"]),
            initial_eur=float(initial_eur),
        )

    # Sort, forward-fill, drop leading all-NaN rows.
    prices = prices_eur.sort_index().ffill().dropna(how="all")
    if prices.empty:
        return SimulationResult(
            history=pd.DataFrame(),
            triggers=pd.DataFrame(columns=["ts", "rule", "n_positions_changed", "weight_delta"]),
            initial_eur=float(initial_eur),
        )

    target_w = _align_weights(initial_weights, prices.columns)
    cols = list(target_w.index)
    daily_ret = prices[cols].pct_change().fillna(0.0)

    rebal_dates = _rebalance_index(prices.index, rebalance_freq)
    # Always rebalance on the first bar.
    rebal_dates.add(prices.index[0])

    n = len(prices.index)
    nav_baseline = np.zeros(n, dtype=float)
    nav_ruled = np.zeros(n, dtype=float)
    cash_ruled = np.zeros(n, dtype=float)
    exposure_ruled = np.zeros(n, dtype=float)
    weight_path = np.zeros((n, len(cols)), dtype=float)

    # State
    w_base = target_w.copy()
    w_rule = target_w.copy()
    cash_base = 1.0 - float(w_base.sum())
    cash_rule = 1.0 - float(w_rule.sum())
    nav_b = float(initial_eur)
    nav_r = float(initial_eur)
    peak_prices: dict[str, float] = {
        c: float(prices.iloc[0][c]) for c in cols if np.isfinite(prices.iloc[0][c])
    }
    nav_history_ruled: list[float] = [nav_r]

    trigger_records: list[dict] = []

    for i, ts in enumerate(prices.index):
        r = daily_ret.iloc[i]

        # 1) Apply realised returns to the weight vectors (drifted weights)
        if i > 0:
            growth = 1.0 + r.values
            # Baseline drift
            w_base_vals = w_base.values * growth
            base_total = float(w_base_vals.sum()) + cash_base
            nav_b *= base_total
            if base_total > 0:
                w_base = pd.Series(w_base_vals / base_total, index=cols)
                cash_base = cash_base / base_total
            # Ruled drift
            w_rule_vals = w_rule.values * growth
            rule_total = float(w_rule_vals.sum()) + cash_rule
            nav_r *= rule_total
            if rule_total > 0:
                w_rule = pd.Series(w_rule_vals / rule_total, index=cols)
                cash_rule = cash_rule / rule_total
            nav_history_ruled.append(nav_r)

            # Update trailing peaks
            for c in cols:
                px = float(prices.iloc[i][c])
                if not np.isfinite(px):
                    continue
                peak_prices[c] = max(peak_prices.get(c, px), px)

        # 2) Periodic rebalance (always reseats baseline to target; rules layer
        #    on top for the ruled portfolio).
        if ts in rebal_dates:
            w_base = target_w.copy()
            cash_base = 1.0 - float(w_base.sum())
            w_rule = target_w.copy()
            cash_rule = 1.0 - float(w_rule.sum())

        # 3) Apply rule stack to the ruled portfolio every bar.
        if rules:
            new_w, triggers = _apply_rule_stack(
                rules, w_rule, prices, ts, nav_history_ruled, peak_prices
            )
            # Clip & cap so total exposure ≤ 1 (residual cash). Rules MAY produce
            # totals >1 if they're additive; normalise defensively.
            new_w = new_w.clip(lower=0.0)
            total = float(new_w.sum())
            if total > 1.0:
                new_w = new_w / total
                total = 1.0
            cash_rule = 1.0 - total
            w_rule = new_w
            trigger_records.extend(triggers)

        nav_baseline[i] = nav_b
        nav_ruled[i] = nav_r
        cash_ruled[i] = cash_rule * nav_r
        exposure_ruled[i] = float(w_rule.sum())
        weight_path[i, :] = w_rule.values

    history = pd.DataFrame(
        {
            "nav_baseline": nav_baseline,
            "nav_ruled": nav_ruled,
            "cash_ruled": cash_ruled,
            "exposure_ruled": exposure_ruled,
        },
        index=prices.index,
    )
    weight_df = pd.DataFrame(
        weight_path, index=prices.index, columns=[f"w_{c}" for c in cols]
    )
    history = pd.concat([history, weight_df], axis=1)

    # Floor NAVs at 0 defensively — shouldn't be needed with weights >= 0 but
    # gives the API its "NAV >= 0" guarantee.
    history["nav_baseline"] = history["nav_baseline"].clip(lower=0.0)
    history["nav_ruled"] = history["nav_ruled"].clip(lower=0.0)
    history["cash_ruled"] = history["cash_ruled"].clip(lower=0.0)

    triggers = (
        pd.DataFrame(trigger_records)
        if trigger_records
        else pd.DataFrame(columns=["ts", "rule", "n_positions_changed", "weight_delta"])
    )

    return SimulationResult(
        history=history,
        triggers=triggers,
        initial_eur=float(initial_eur),
    )
