"""Black-Scholes pricer, inverse implied-volatility solver, and greeks.

Used **only** when the yfinance fallback fires inside `options_chain.fetch_chain`
(Alpaca already delivers greeks). All formulas follow Hull 10e, with continuous
compounding and a dividend yield `q` (0 by default; user can pass a non-zero
yield for ETFs that distribute monthly distributions e.g. URA, USO).

Convention:
  * `S`     spot price of underlier (listing currency).
  * `K`     strike (same currency).
  * `T`     year-fraction to expiry, computed as `(expiry - asof).days / 365`.
  * `r`    continuously-compounded risk-free rate (decimal, e.g. 0.04 = 4%).
  * `q`    continuous dividend yield (decimal).
  * `sigma`  annualised volatility (decimal, e.g. 0.45 = 45%).
  * `right`  `OptionRight.CALL` or `OptionRight.PUT`.

The inverse IV solver uses scipy `brentq` and bracket-widening — much more
numerically robust than Newton for the deep-OTM / near-expiry regime that
dominates retail option flow.
"""
from __future__ import annotations

import math
from typing import Iterable

from scipy.optimize import brentq
from scipy.stats import norm

from src.common.schemas import OptionContract, OptionRight
from src.utils.logging import get_logger

log = get_logger(__name__)

# ---------------------------------------------------------------------------
# Numerical guards
# ---------------------------------------------------------------------------
_MIN_T = 1e-6              # one-second time floor — avoids div/0 on expiry day
_MIN_SIGMA = 1e-4
_MAX_SIGMA = 5.0           # 500% vol — anything beyond is junk
_IV_TOL = 1e-6


def _d1_d2(
    S: float, K: float, T: float, r: float, sigma: float, q: float = 0.0,
) -> tuple[float, float]:
    """Hull eq. 14.5 — d1, d2 for a dividend-paying underlier."""
    T = max(T, _MIN_T)
    sigma = max(sigma, _MIN_SIGMA)
    vol_root_T = sigma * math.sqrt(T)
    d1 = (math.log(S / K) + (r - q + 0.5 * sigma * sigma) * T) / vol_root_T
    d2 = d1 - vol_root_T
    return d1, d2


# ---------------------------------------------------------------------------
# Pricer
# ---------------------------------------------------------------------------
def bs_price(
    S: float, K: float, T: float, r: float, sigma: float,
    right: OptionRight | str, q: float = 0.0,
) -> float:
    """Black-Scholes European option price."""
    right_str = right.value if isinstance(right, OptionRight) else str(right).upper()[:1]
    d1, d2 = _d1_d2(S, K, T, r, sigma, q)
    disc_r = math.exp(-r * max(T, _MIN_T))
    disc_q = math.exp(-q * max(T, _MIN_T))
    if right_str == "C":
        return S * disc_q * norm.cdf(d1) - K * disc_r * norm.cdf(d2)
    return K * disc_r * norm.cdf(-d2) - S * disc_q * norm.cdf(-d1)


def bs_delta(
    S: float, K: float, T: float, r: float, sigma: float,
    right: OptionRight | str, q: float = 0.0,
) -> float:
    """∂V/∂S."""
    right_str = right.value if isinstance(right, OptionRight) else str(right).upper()[:1]
    d1, _ = _d1_d2(S, K, T, r, sigma, q)
    disc_q = math.exp(-q * max(T, _MIN_T))
    if right_str == "C":
        return disc_q * norm.cdf(d1)
    return disc_q * (norm.cdf(d1) - 1.0)


def bs_gamma(
    S: float, K: float, T: float, r: float, sigma: float, q: float = 0.0,
) -> float:
    """∂²V/∂S² — identical for calls & puts."""
    T = max(T, _MIN_T)
    sigma = max(sigma, _MIN_SIGMA)
    d1, _ = _d1_d2(S, K, T, r, sigma, q)
    disc_q = math.exp(-q * T)
    return disc_q * norm.pdf(d1) / (S * sigma * math.sqrt(T))


def bs_theta(
    S: float, K: float, T: float, r: float, sigma: float,
    right: OptionRight | str, q: float = 0.0,
) -> float:
    """∂V/∂T expressed **per calendar day** (divide annual θ by 365)."""
    right_str = right.value if isinstance(right, OptionRight) else str(right).upper()[:1]
    T = max(T, _MIN_T)
    d1, d2 = _d1_d2(S, K, T, r, sigma, q)
    disc_r = math.exp(-r * T)
    disc_q = math.exp(-q * T)
    first = -(S * disc_q * norm.pdf(d1) * sigma) / (2.0 * math.sqrt(T))
    if right_str == "C":
        theta_y = first - r * K * disc_r * norm.cdf(d2) + q * S * disc_q * norm.cdf(d1)
    else:
        theta_y = first + r * K * disc_r * norm.cdf(-d2) - q * S * disc_q * norm.cdf(-d1)
    return theta_y / 365.0


def bs_vega(
    S: float, K: float, T: float, r: float, sigma: float, q: float = 0.0,
) -> float:
    """∂V/∂σ — expressed per **1.00 vol point** (multiply by 0.01 for per-pct)."""
    T = max(T, _MIN_T)
    d1, _ = _d1_d2(S, K, T, r, sigma, q)
    disc_q = math.exp(-q * T)
    return S * disc_q * norm.pdf(d1) * math.sqrt(T)


# ---------------------------------------------------------------------------
# Inverse — implied volatility
# ---------------------------------------------------------------------------
def bs_iv(
    price: float, S: float, K: float, T: float, r: float,
    right: OptionRight | str, q: float = 0.0,
) -> float | None:
    """Recover σ such that BS price ≈ observed `price`.

    Returns None if the option is below intrinsic value (no arbitrage-free σ
    exists), or if the brentq solver diverges.
    """
    right_str = right.value if isinstance(right, OptionRight) else str(right).upper()[:1]
    if price is None or price <= 0 or S <= 0 or K <= 0 or T <= 0:
        return None

    # Intrinsic guard — no σ recovers a price below intrinsic (would imply
    # negative time value).
    disc_r = math.exp(-r * T)
    disc_q = math.exp(-q * T)
    if right_str == "C":
        intrinsic = max(0.0, S * disc_q - K * disc_r)
    else:
        intrinsic = max(0.0, K * disc_r - S * disc_q)
    if price < intrinsic - 1e-8:
        return None

    def _residual(sig: float) -> float:
        return bs_price(S, K, T, r, sig, right_str, q) - price

    try:
        lo, hi = _MIN_SIGMA, _MAX_SIGMA
        f_lo, f_hi = _residual(lo), _residual(hi)
        # Widen bracket if needed (cheap; price could be very rich)
        widen = 0
        while f_lo * f_hi > 0 and widen < 4:
            hi *= 2.0
            f_hi = _residual(hi)
            widen += 1
        if f_lo * f_hi > 0:
            return None
        sigma = brentq(_residual, lo, hi, xtol=_IV_TOL, maxiter=200)
        return float(sigma)
    except Exception as exc:
        log.debug("bs_iv solver failed (S=%.2f K=%.2f T=%.4f px=%.4f): %s", S, K, T, price, exc)
        return None


# Alias kept for naming-flexibility with PHASE1 plan + brief
implied_vol = bs_iv


# ---------------------------------------------------------------------------
# Batch helper — used by yfinance fallback in options_chain
# ---------------------------------------------------------------------------
def enrich_with_greeks(
    contracts: Iterable[OptionContract], *, spot: float, r: float = 0.04, q: float = 0.0,
) -> list[OptionContract]:
    """Populate iv/delta/gamma/theta/vega in-place on a list of contracts.

    Mid-price preferred; falls back to `last` then bid/ask average. Contracts
    already carrying a non-None `iv` are skipped (Alpaca already supplied them).
    """
    enriched: list[OptionContract] = []
    for c in contracts:
        if c.delta is not None and c.gamma is not None and c.iv is not None:
            enriched.append(c)
            continue
        # Choose a reference price
        px = c.mid
        if px is None and c.bid is not None and c.ask is not None:
            px = 0.5 * (c.bid + c.ask)
        if px is None:
            px = c.last
        if px is None or px <= 0:
            enriched.append(c)
            continue

        T = max((c.expiry - c.snapshot_ts.date()).days / 365.0, _MIN_T)
        iv = c.iv
        if iv is None:
            iv = bs_iv(px, spot, c.strike, T, r, c.right, q)
        if iv is None or iv <= 0:
            enriched.append(c)
            continue

        c2 = c.model_copy(update={
            "iv": iv,
            "delta": bs_delta(spot, c.strike, T, r, iv, c.right, q),
            "gamma": bs_gamma(spot, c.strike, T, r, iv, q),
            "theta": bs_theta(spot, c.strike, T, r, iv, c.right, q),
            "vega": bs_vega(spot, c.strike, T, r, iv, q),
            "mid": px,
        })
        enriched.append(c2)
    return enriched
