"""Earnings IV Crush Forecaster.

A long-call/put trader's biggest killer pre-earnings is **IV crush**: the post-
event collapse of implied vol that destroys time-value even if direction was
right. This module estimates the size of that crush and projects whether a
proposed position would survive it.

Approach
--------
1. **Historical crush stats (per ticker)** — for each earnings date in the
   past N quarters, compute realised post-event return vs pre-event IV. A
   simple proxy is used when historical IV is unavailable: the **realised
   move ÷ pre-event implied move** ratio, capped at sensible bounds.

2. **Crush ratio estimate** — typical empirical pattern: IV halves on the
   open after earnings (50-65% crush). We expose the ratio as a parameter
   (default 0.55, meaning IV drops 45%).

3. **Survival model** — given a current option (strike, expiry, IV, premium),
   estimate the post-event value using Black-Scholes with the crushed IV and
   solve for the spot move needed to recover the entry debit.

The output is decision-ready: "spot must move ≥ X% to break even after IV
crushes from 95% → 52%". The trader sees, before clicking Buy, whether the
implied move covers their breakeven.

Inputs that matter
------------------
* current_iv : pre-event IV (read from chain at the chosen strike)
* spot       : underlying price
* strike     : option strike
* dte        : days-to-expiry on the trade date
* premium    : current option premium per share
* right      : CALL or PUT
* crush_ratio: IV multiplier after earnings (e.g. 0.55 → 45% crush)
* days_held  : how many days after earnings the trader holds (default 1)

NOTE: this module is **pure modelling** — no scrapers, no data fetches. The
caller passes in chain-derived inputs.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from src.common.schemas import OptionRight
from src.trading.greeks import bs_price


@dataclass
class CrushScenario:
    pre_iv: float                   # IV before event (decimal, e.g. 0.95)
    post_iv: float                  # IV after event (decimal)
    crush_ratio: float              # post_iv / pre_iv
    pre_premium_per_share: float    # entry premium
    post_premium_no_move: float     # premium right after crush, spot unchanged
    breakeven_spot: float           # spot required to recover entry debit
    breakeven_move_pct: float       # (breakeven_spot - spot) / spot
    survives_implied_move: bool     # is breakeven within ±implied_move?
    implied_move_pct: float | None  # implied move % (None if not provided)
    pl_at_implied_move: float | None  # P&L per share if spot moves by implied move


def estimate_post_iv(pre_iv: float, crush_ratio: float = 0.55) -> float:
    """Apply the crush multiplier (default 0.55 → 45% drop)."""
    return max(0.01, float(pre_iv) * float(crush_ratio))


def implied_move_pct(atm_iv: float, dte_days: int) -> float:
    """Standard implied 1σ move: σ × √(dte/365)."""
    return float(atm_iv) * np.sqrt(max(dte_days, 1) / 365.0)


def crush_scenario(
    *,
    spot: float,
    strike: float,
    dte_days: int,
    pre_iv: float,
    premium: float,
    right: OptionRight | str,
    crush_ratio: float = 0.55,
    days_held: int = 1,
    risk_free: float = 0.04,
    implied_move: float | None = None,
) -> CrushScenario:
    """Forecast the post-event option value and breakeven spot.

    Parameters
    ----------
    spot, strike, dte_days, pre_iv, premium, right : option specs at entry
    crush_ratio : multiplicative IV decline (0.55 ≈ 45% crush — typical earnings)
    days_held   : trading days held after earnings before exit (1 = next-day exit)
    risk_free   : continuously-compounded rate
    implied_move: optional pre-event 1σ implied move (decimal). When provided,
                  the scenario tells whether the breakeven is inside this move.
    """
    if pre_iv <= 0 or premium <= 0 or spot <= 0:
        raise ValueError("pre_iv, premium and spot must be positive")
    post_iv = estimate_post_iv(pre_iv, crush_ratio)
    post_dte_years = max((dte_days - days_held) / 365.0, 1e-6)

    # Post-event premium at unchanged spot
    post_premium_no_move = bs_price(
        S=spot, K=strike, T=post_dte_years, r=risk_free,
        sigma=post_iv, right=right,
    )

    # Solve for breakeven spot: post-event premium = entry premium.
    # Search numerically over a wide bracket (50% below to 100% above spot).
    spots = np.linspace(spot * 0.5, spot * 2.0, 600)
    prices = np.array([
        bs_price(S=s, K=strike, T=post_dte_years, r=risk_free,
                 sigma=post_iv, right=right)
        for s in spots
    ])
    diffs = prices - premium
    # For long call: breakeven is the smallest spot where post-price >= premium.
    # For long put : the largest such spot.
    right_str = right.value if isinstance(right, OptionRight) else str(right).upper()[:1]
    if right_str == "C":
        idx = np.argmax(diffs >= 0) if (diffs >= 0).any() else len(spots) - 1
    else:
        positive = diffs >= 0
        idx = len(positive) - 1 - np.argmax(positive[::-1]) if positive.any() else 0
    breakeven_spot = float(spots[idx])
    breakeven_move = (breakeven_spot - spot) / spot

    survives = False
    pl_at_im = None
    if implied_move is not None and implied_move > 0:
        # Survives if abs(breakeven move) ≤ implied move
        survives = abs(breakeven_move) <= implied_move
        # Estimate P&L at exactly the implied move (right-direction)
        target_spot = spot * (1 + implied_move) if right_str == "C" else spot * (1 - implied_move)
        post_at_im = bs_price(
            S=target_spot, K=strike, T=post_dte_years, r=risk_free,
            sigma=post_iv, right=right,
        )
        pl_at_im = float(post_at_im - premium)

    return CrushScenario(
        pre_iv=float(pre_iv),
        post_iv=float(post_iv),
        crush_ratio=float(crush_ratio),
        pre_premium_per_share=float(premium),
        post_premium_no_move=float(post_premium_no_move),
        breakeven_spot=breakeven_spot,
        breakeven_move_pct=float(breakeven_move),
        survives_implied_move=bool(survives),
        implied_move_pct=float(implied_move) if implied_move else None,
        pl_at_implied_move=pl_at_im,
    )


def crush_grid(
    *,
    spot: float, strike: float, dte_days: int,
    pre_iv: float, premium: float, right: OptionRight | str,
    crush_ratios: list[float] | None = None,
    days_held: int = 1,
    risk_free: float = 0.04,
) -> list[CrushScenario]:
    """Build a sensitivity grid across plausible crush ratios (40% → 70% crush)."""
    crush_ratios = crush_ratios or [0.30, 0.40, 0.50, 0.55, 0.60, 0.70]
    return [
        crush_scenario(
            spot=spot, strike=strike, dte_days=dte_days, pre_iv=pre_iv,
            premium=premium, right=right, crush_ratio=cr, days_held=days_held,
            risk_free=risk_free,
        )
        for cr in crush_ratios
    ]


__all__ = [
    "CrushScenario", "crush_scenario", "crush_grid",
    "estimate_post_iv", "implied_move_pct",
]
