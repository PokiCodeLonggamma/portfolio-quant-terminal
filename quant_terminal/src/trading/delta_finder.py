"""Closest-delta strike picker.

The user trades at the **foot of the gamma curve** — target |delta| ≈ 0.25
(brief). This module picks the contract from a fetched chain whose absolute
delta is closest to the target, within a tolerance band.

Notes
-----
* Calls have delta in [0, 1], puts in [-1, 0]. We always compare on `|delta|`.
* If multiple contracts tie on |delta - target|, we tie-break on:
    1. shorter spread (ask - bid) — better fill
    2. higher OI
    3. nearer-the-money strike
* Returns `None` if no contract satisfies `|delta_actual - target| <= tolerance`.
"""
from __future__ import annotations

import pandas as pd

from src.common.schemas import OptionContract, OptionRight
from src.utils.logging import get_logger

log = get_logger(__name__)

DEFAULT_TOLERANCE = 0.05


def closest_delta(
    contracts: list[OptionContract],
    target_delta: float = 0.25,
    right: OptionRight | str = OptionRight.CALL,
    tolerance: float = DEFAULT_TOLERANCE,
) -> OptionContract | None:
    """Return the OptionContract whose |delta| is closest to `target_delta`.

    Parameters
    ----------
    contracts     : pre-fetched chain (already enriched with greeks).
    target_delta  : positive target in [0, 1] (we compare against |delta|).
    right         : restrict to CALL or PUT.
    tolerance     : maximum acceptable |delta_actual - target|. None if exceeded.
    """
    right_val = right if isinstance(right, OptionRight) else OptionRight(str(right)[:1].upper())
    candidates = [
        c for c in contracts
        if c.right == right_val and c.delta is not None
    ]
    if not candidates:
        return None

    def _score(c: OptionContract) -> tuple[float, float, float, float]:
        spread = (
            (c.ask or 1e9) - (c.bid or 0.0)
            if (c.ask is not None and c.bid is not None)
            else 1e9
        )
        oi_inv = -float(c.open_interest or 0)
        moneyness = abs(c.strike)
        return (abs(abs(c.delta) - target_delta), spread, oi_inv, moneyness)

    best = min(candidates, key=_score)
    if abs(abs(best.delta) - target_delta) > tolerance:
        return None
    return best


def candidates_table(
    contracts: list[OptionContract],
    *,
    target_delta: float = 0.25,
    right: OptionRight | str | None = None,
) -> pd.DataFrame:
    """Sort candidates by closeness to target delta — useful in dashboards."""
    if right is not None:
        right_val = right if isinstance(right, OptionRight) else OptionRight(str(right)[:1].upper())
        pool = [c for c in contracts if c.right == right_val and c.delta is not None]
    else:
        pool = [c for c in contracts if c.delta is not None]
    if not pool:
        return pd.DataFrame()
    rows = []
    for c in pool:
        rows.append({
            "symbol": c.symbol,
            "expiry": c.expiry,
            "right": c.right.value,
            "strike": c.strike,
            "delta": c.delta,
            "abs_delta_minus_target": abs(abs(c.delta) - target_delta),
            "iv": c.iv,
            "gamma": c.gamma,
            "bid": c.bid, "ask": c.ask, "mid": c.mid,
            "open_interest": c.open_interest,
            "volume": c.volume,
        })
    return pd.DataFrame(rows).sort_values("abs_delta_minus_target").reset_index(drop=True)
