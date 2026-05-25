"""Portfolio-level Greeks aggregation.

Combines:
  - **Stock positions** from `Portfolio.holdings` (Δ = signed quantity,
    Γ = Vega = Θ = 0).
  - **Open option positions** from `src.trading.journal.list_open()`.
    For each open trade we refetch the current chain to get up-to-date
    delta/gamma/theta/vega, then scale by `qty × 100 × sign(direction)`.

Outputs everything in EUR using `src.data.fx.to_eur` for USD-listed
underlyings (the typical case for Alpaca options).

Public surface:
  - `aggregate_greeks(portfolio, open_options_df, prices_eur, fetch_chain_fn)`
  - `theta_decay_schedule(portfolio_greeks_payload, days_ahead=30)`
  - `gamma_calendar(open_options_df, fetch_chain_fn)`
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Callable

import numpy as np
import pandas as pd

from src.common.schemas import OptionContract
from src.data.fx import to_eur
from src.portfolio.holdings import Portfolio
from src.utils.config import get_config
from src.utils.logging import get_logger

log = get_logger(__name__)

# Option contract multiplier (US equities/ETFs)
OPTION_MULTIPLIER = 100


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------
@dataclass
class PortfolioGreeks:
    """Aggregated portfolio-level Greeks, all in EUR."""

    total_delta_eur: float = 0.0           # Σ Δ_i × spot_i × qty (already in EUR)
    total_gamma_eur: float = 0.0           # Σ Γ_i × spot_i² × qty × 100 × 0.01 ("1% move PnL change")
    total_vega_eur: float = 0.0            # Σ Vega_i × qty × 100 (per 1 vol-point)
    total_theta_eur: float = 0.0           # Σ Θ_i × qty × 100 (per day, signed negative for long premium)
    beta_weighted_delta_eur: float = 0.0   # Σ β_i × Δ_i (vs SPY)
    n_stock_positions: int = 0
    n_option_positions: int = 0
    by_ticker: pd.DataFrame = field(default_factory=pd.DataFrame)

    def as_dict(self) -> dict[str, float]:
        return {
            "total_delta_eur": self.total_delta_eur,
            "total_gamma_eur": self.total_gamma_eur,
            "total_vega_eur": self.total_vega_eur,
            "total_theta_eur": self.total_theta_eur,
            "beta_weighted_delta_eur": self.beta_weighted_delta_eur,
            "n_stock_positions": float(self.n_stock_positions),
            "n_option_positions": float(self.n_option_positions),
        }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _sign_for_direction(direction: str) -> int:
    """LONG_CALL / LONG_PUT are both long premium → quantity is positive."""
    if not direction:
        return 1
    return 1 if direction.startswith("LONG_") else -1


def _spot_eur(ticker: str, prices_eur: pd.DataFrame) -> float | None:
    if prices_eur is None or prices_eur.empty:
        return None
    if ticker not in prices_eur.columns:
        return None
    series = prices_eur[ticker].dropna()
    if series.empty:
        return None
    return float(series.iloc[-1])


def _match_contract(
    contracts: list[OptionContract],
    contract_symbol: str | None,
    strike: float,
    expiry,
    direction: str,
) -> OptionContract | None:
    """Find the contract in the chain matching the journal row."""
    if not contracts:
        return None
    target_right = "C" if "CALL" in (direction or "") else "P"
    target_expiry = expiry if isinstance(expiry, date) else pd.Timestamp(expiry).date()
    # Try OCC symbol match first
    if contract_symbol:
        for c in contracts:
            if c.symbol == contract_symbol:
                return c
    # Fallback: strike + expiry + right
    candidates = [
        c for c in contracts
        if c.right.value == target_right
        and c.expiry == target_expiry
        and abs(float(c.strike) - float(strike)) < 0.01
    ]
    return candidates[0] if candidates else None


def _per_ticker_beta(prices_eur: pd.DataFrame, benchmark_returns: pd.Series | None,
                     window: int = 60) -> dict[str, float]:
    """Rolling univariate beta vs benchmark, computed on the trailing window."""
    if benchmark_returns is None or benchmark_returns.empty or prices_eur.empty:
        return {}
    returns = prices_eur.pct_change().dropna(how="all").tail(window)
    bench = benchmark_returns.reindex(returns.index).dropna()
    common = returns.index.intersection(bench.index)
    if len(common) < 10:
        return {}
    out: dict[str, float] = {}
    for col in returns.columns:
        y = returns.loc[common, col].dropna()
        x = bench.loc[y.index]
        if len(y) < 10:
            continue
        var_x = float(x.var(ddof=1))
        if var_x <= 0:
            continue
        cov_xy = float(y.cov(x))
        out[col] = cov_xy / var_x
    return out


# ---------------------------------------------------------------------------
# Main aggregator
# ---------------------------------------------------------------------------
def aggregate_greeks(
    portfolio: Portfolio,
    open_options_df: pd.DataFrame | None,
    prices_eur: pd.DataFrame,
    fetch_chain_fn: Callable[..., list[OptionContract]] | None = None,
    benchmark_returns: pd.Series | None = None,
) -> PortfolioGreeks:
    """Aggregate stock + options Greeks at portfolio level (all EUR).

    Parameters
    ----------
    portfolio:
        Already-enriched Portfolio (currencies, value_eur per row).
    open_options_df:
        Output of `src.trading.journal.list_open()`. May be empty / None.
    prices_eur:
        Wide DataFrame of EUR-normalised prices (date × universe_key) used
        to get spot prices and per-ticker betas.
    fetch_chain_fn:
        Optional injection for tests; defaults to
        `src.trading.options_chain.fetch_chain`.
    benchmark_returns:
        Optional SPY (or other) daily returns series for beta-weighting.

    Returns
    -------
    PortfolioGreeks
    """
    if fetch_chain_fn is None:
        from src.trading.options_chain import fetch_chain
        fetch_chain_fn = fetch_chain

    pg = PortfolioGreeks()
    rows: list[dict] = []

    # ---- 1. Stock contribution -------------------------------------------
    betas = _per_ticker_beta(prices_eur, benchmark_returns)
    if portfolio is not None and not portfolio.holdings.empty:
        for _, h in portfolio.holdings.iterrows():
            ticker = str(h["universe_key"])
            value_eur = float(h["value_eur"])
            # Δ_stock = market value in EUR (1 unit of stock = 1 EUR of delta exposure)
            stock_delta = value_eur
            pg.total_delta_eur += stock_delta
            b = betas.get(ticker, 1.0)
            pg.beta_weighted_delta_eur += b * stock_delta
            pg.n_stock_positions += 1
            rows.append({
                "ticker": ticker,
                "kind": "stock",
                "qty": float(h["quantity"]),
                "delta_eur": stock_delta,
                "gamma_eur": 0.0,
                "vega_eur": 0.0,
                "theta_eur": 0.0,
                "beta": b,
                "expiry": None,
                "strike": None,
            })

    # ---- 2. Option contribution ------------------------------------------
    if open_options_df is not None and not open_options_df.empty:
        cfg = get_config()
        # Group rows by ticker to fetch each chain once
        for ticker, sub in open_options_df.groupby("ticker"):
            ticker = str(ticker)
            try:
                chain = fetch_chain_fn(ticker)
            except Exception as exc:
                log.warning("Greeks: chain fetch failed for %s: %s", ticker, exc)
                continue
            # If we don't have an EUR spot, leave delta in option units; else convert
            spot_eur = _spot_eur(ticker, prices_eur)
            currency = cfg.currency_of(ticker) or "USD"
            for _, row in sub.iterrows():
                contract = _match_contract(
                    chain,
                    contract_symbol=row.get("contract_symbol"),
                    strike=float(row.get("strike", 0.0)),
                    expiry=row.get("expiry"),
                    direction=str(row.get("direction", "LONG_CALL")),
                )
                if contract is None or contract.delta is None:
                    log.debug("Greeks: no contract for %s @ %s", ticker, row.get("contract_symbol"))
                    continue
                qty = float(row.get("qty", 1.0)) * _sign_for_direction(str(row.get("direction", "")))
                # Stay in listing currency for the option side, then convert once at the end.
                spot_for_delta = spot_eur if spot_eur is not None else float(contract.strike)
                delta_local = (contract.delta or 0.0) * qty * OPTION_MULTIPLIER * spot_for_delta
                gamma_local = (contract.gamma or 0.0) * qty * OPTION_MULTIPLIER * (spot_for_delta ** 2) * 0.01
                vega_local = (contract.vega or 0.0) * qty * OPTION_MULTIPLIER
                theta_local = (contract.theta or 0.0) * qty * OPTION_MULTIPLIER

                if currency.upper() == "EUR":
                    delta_eur = delta_local
                    gamma_eur = gamma_local
                    vega_eur = vega_local
                    theta_eur = theta_local
                else:
                    delta_eur = to_eur(delta_local, currency)
                    gamma_eur = to_eur(gamma_local, currency)
                    vega_eur = to_eur(vega_local, currency)
                    theta_eur = to_eur(theta_local, currency)

                pg.total_delta_eur += delta_eur
                pg.total_gamma_eur += gamma_eur
                pg.total_vega_eur += vega_eur
                pg.total_theta_eur += theta_eur
                b = betas.get(ticker, 1.0)
                pg.beta_weighted_delta_eur += b * delta_eur
                pg.n_option_positions += 1
                rows.append({
                    "ticker": ticker,
                    "kind": str(row.get("direction", "OPTION")),
                    "qty": qty,
                    "delta_eur": delta_eur,
                    "gamma_eur": gamma_eur,
                    "vega_eur": vega_eur,
                    "theta_eur": theta_eur,
                    "beta": b,
                    "expiry": row.get("expiry"),
                    "strike": float(row.get("strike", 0.0)),
                })

    if rows:
        pg.by_ticker = pd.DataFrame(rows)
    return pg


# ---------------------------------------------------------------------------
# Theta decay schedule
# ---------------------------------------------------------------------------
def theta_decay_schedule(
    open_options_df: pd.DataFrame | None,
    fetch_chain_fn: Callable[..., list[OptionContract]] | None = None,
    days_ahead: int = 30,
) -> pd.DataFrame:
    """Daily theta P&L projection (EUR) for the next `days_ahead` days.

    Assumes theta is roughly constant short-term (a simplification — in
    reality theta accelerates as DTE → 0). Returns columns:
        day_offset (int), theta_eur (negative for long premium), cum_theta_eur
    """
    if open_options_df is None or open_options_df.empty:
        return pd.DataFrame(columns=["day_offset", "theta_eur", "cum_theta_eur"])

    if fetch_chain_fn is None:
        from src.trading.options_chain import fetch_chain
        fetch_chain_fn = fetch_chain

    cfg = get_config()
    today = date.today()
    daily_theta_total = 0.0
    for ticker, sub in open_options_df.groupby("ticker"):
        ticker = str(ticker)
        try:
            chain = fetch_chain_fn(ticker)
        except Exception:
            continue
        currency = cfg.currency_of(ticker) or "USD"
        for _, row in sub.iterrows():
            c = _match_contract(
                chain,
                contract_symbol=row.get("contract_symbol"),
                strike=float(row.get("strike", 0.0)),
                expiry=row.get("expiry"),
                direction=str(row.get("direction", "LONG_CALL")),
            )
            if c is None or c.theta is None:
                continue
            qty = float(row.get("qty", 1.0)) * _sign_for_direction(str(row.get("direction", "")))
            theta_local = (c.theta or 0.0) * qty * OPTION_MULTIPLIER
            theta_eur = theta_local if currency.upper() == "EUR" else to_eur(theta_local, currency)
            daily_theta_total += theta_eur

    rows = []
    cum = 0.0
    for d in range(days_ahead + 1):
        # Stop accruing theta past the earliest expiry where it would be zero anyway.
        cum += daily_theta_total
        rows.append({
            "day_offset": d,
            "date": today + timedelta(days=d),
            "theta_eur": daily_theta_total,
            "cum_theta_eur": cum,
        })
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Gamma calendar
# ---------------------------------------------------------------------------
def gamma_calendar(
    open_options_df: pd.DataFrame | None,
    fetch_chain_fn: Callable[..., list[OptionContract]] | None = None,
) -> pd.DataFrame:
    """One row per open option position with DTE + current gamma + projected gamma.

    Columns: ticker, contract_symbol, strike, expiry, dte_days, gamma_now,
             gamma_in_7d, gamma_in_14d, half_life_days
    `gamma_in_Nd` uses the rough Black-Scholes relation
        γ_T ≈ γ_now × sqrt(T_now / max(T_now - N, eps)).
    """
    if open_options_df is None or open_options_df.empty:
        return pd.DataFrame()

    if fetch_chain_fn is None:
        from src.trading.options_chain import fetch_chain
        fetch_chain_fn = fetch_chain

    rows = []
    today = date.today()
    for ticker, sub in open_options_df.groupby("ticker"):
        ticker = str(ticker)
        try:
            chain = fetch_chain_fn(ticker)
        except Exception:
            continue
        for _, row in sub.iterrows():
            c = _match_contract(
                chain,
                contract_symbol=row.get("contract_symbol"),
                strike=float(row.get("strike", 0.0)),
                expiry=row.get("expiry"),
                direction=str(row.get("direction", "LONG_CALL")),
            )
            if c is None or c.gamma is None:
                continue
            expiry = c.expiry if isinstance(c.expiry, date) else pd.Timestamp(c.expiry).date()
            dte = max(0, (expiry - today).days)
            t_now = max(1, dte) / 252.0
            # Project gamma forward
            def proj(days_forward: int) -> float:
                t_then = max(1, dte - days_forward) / 252.0
                if t_then <= 0:
                    return float("inf")
                return float(c.gamma) * np.sqrt(t_now / t_then)
            # Half-life: solve √(t_now / t_50) = 2 → t_50 = t_now / 4 → days_to_50 = t_now × (3/4) × 252
            half_life = int(round(dte * 0.75)) if dte > 0 else 0
            rows.append({
                "ticker": ticker,
                "contract_symbol": c.symbol,
                "strike": float(c.strike),
                "expiry": expiry,
                "dte_days": dte,
                "gamma_now": float(c.gamma),
                "gamma_in_7d": proj(7),
                "gamma_in_14d": proj(14),
                "days_to_half_gamma": half_life,
            })
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows).sort_values("dte_days")
