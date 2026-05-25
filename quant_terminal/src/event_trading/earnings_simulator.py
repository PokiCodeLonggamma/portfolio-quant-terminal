"""Earnings reaction simulator.

Given a long-option position + a (spot %, IV %) shock, re-price the
contract using Black-Scholes and surface the PnL per contract and in EUR.

The IV crush default is -30 % (typical post-earnings IV deflation).
"""
from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd
from scipy.stats import norm

from src.common.schemas import EarningsScenario, OptionContract
from src.utils.logging import get_logger

log = get_logger(__name__)


# Black-Scholes call/put pricing -------------------------------------------
def _bs_price(S: float, K: float, T: float, r: float, sigma: float,
              q: float = 0.0, right: str = "C") -> float:
    if T <= 0 or sigma <= 0:
        # Intrinsic only
        intrinsic = max(S - K, 0.0) if right == "C" else max(K - S, 0.0)
        return float(intrinsic)
    d1 = (np.log(S / K) + (r - q + 0.5 * sigma ** 2) * T) / (sigma * np.sqrt(T))
    d2 = d1 - sigma * np.sqrt(T)
    if right == "C":
        return float(S * np.exp(-q * T) * norm.cdf(d1) - K * np.exp(-r * T) * norm.cdf(d2))
    return float(K * np.exp(-r * T) * norm.cdf(-d2) - S * np.exp(-q * T) * norm.cdf(-d1))


def simulate_position(
    contract: OptionContract,
    qty: int,
    spot_shock_pct: float,
    iv_shock_pct: float = -0.30,
    *,
    spot: float | None = None,
    rf_annual: float = 0.04,
    fx_to_eur: float = 1.10,
    today: date | None = None,
) -> EarningsScenario | None:
    """Re-price `contract` under (spot_shock, iv_shock). Returns EarningsScenario.

    `spot` is the current underlying price. If None, falls back to `contract.strike`
    (rough but lets the function never crash on a fresh chain).
    """
    if contract is None:
        return None
    today = today or date.today()
    iv_now = float(contract.iv or 0.0)
    if iv_now <= 0:
        log.warning("Cannot simulate %s — missing IV", contract.symbol)
        return None
    spot_now = float(spot) if spot and spot > 0 else float(contract.strike)

    dte = max(0, (contract.expiry - today).days)
    T = dte / 365.0

    price_now = float(contract.mid or contract.last or contract.bid or 0.0)

    # Apply shocks
    spot_after = spot_now * (1.0 + spot_shock_pct)
    iv_after = max(0.0001, iv_now * (1.0 + iv_shock_pct))
    right = "C" if contract.right.value == "C" else "P"
    price_after = _bs_price(spot_after, contract.strike, T, rf_annual, iv_after, right=right)

    pnl_per_contract = (price_after - price_now) * 100
    pnl_total_local = pnl_per_contract * qty
    pnl_total_eur = pnl_total_local / fx_to_eur if fx_to_eur else pnl_total_local

    return EarningsScenario(
        ticker=contract.underlying,
        contract_symbol=contract.symbol,
        spot_now=float(spot_now),
        spot_after=float(spot_after),
        iv_now=float(iv_now),
        iv_after=float(iv_after),
        price_now=float(price_now),
        price_after=float(price_after),
        pnl_per_contract_local=float(pnl_per_contract),
        pnl_total_eur=float(pnl_total_eur),
        notes=(
            f"spot {spot_shock_pct * 100:+.1f}% · iv {iv_shock_pct * 100:+.1f}% · "
            f"{dte}d to expiry"
        ),
    )


def shock_grid(
    contract: OptionContract,
    qty: int,
    spot_shocks: list[float],
    iv_shocks: list[float],
    *,
    spot: float | None = None,
    rf_annual: float = 0.04,
    fx_to_eur: float = 1.10,
    today: date | None = None,
) -> pd.DataFrame:
    """Cartesian grid of (spot_shock, iv_shock) → PnL EUR per scenario."""
    rows = []
    for s in spot_shocks:
        for v in iv_shocks:
            scen = simulate_position(contract, qty, s, v, spot=spot,
                                      rf_annual=rf_annual, fx_to_eur=fx_to_eur,
                                      today=today)
            if scen is None:
                continue
            rows.append({
                "spot_shock_pct": s * 100,
                "iv_shock_pct": v * 100,
                "pnl_eur": scen.pnl_total_eur,
                "price_after": scen.price_after,
            })
    return pd.DataFrame(rows)
