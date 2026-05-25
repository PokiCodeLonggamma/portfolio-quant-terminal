"""VaR-contribution-based trim sizing.

Given a portfolio + per-position daily returns + a theme name + a target
percentage of the portfolio's total parametric-VaR that the theme should
contribute, this module suggests proportional trims on the theme's
positions to bring the contribution under the target.

The math:

  1. Compute per-position contributions to VaR via
     `src.portfolio.risk.marginal_var`. The function already returns
     ``rho_i * sigma_i * weight_i * (VaR/sigma_p)`` per position.
  2. Sum the theme's contributions -> `theme_contrib_pct`.
  3. If above target, scale the theme's weights uniformly by
     ``target_theme_pct / theme_contrib_pct`` (one-shot proportional cut).
  4. Convert the scale-factor into per-position trim amounts in EUR.

We don't add capital — only trim. If the contribution is already below
target the suggestions are all zeros.
"""
from __future__ import annotations

from typing import Any

import pandas as pd

from src.portfolio.risk import marginal_var, parametric_var
from src.utils.logging import get_logger

log = get_logger(__name__)


_PANEL_COLS = [
    "ticker", "theme", "weight_eur", "marginal_var", "contrib_pct_of_portfolio_var",
    "in_theme", "suggested_trim_eur", "suggested_weight_eur", "rationale",
]


def _portfolio_holdings_df(portfolio: Any) -> pd.DataFrame:
    """Return the underlying holdings DataFrame from a Portfolio wrapper.

    Falls back to interpreting the argument as a DataFrame directly so tests
    can pass a synthetic frame without instantiating a full Portfolio.
    """
    if portfolio is None:
        return pd.DataFrame(columns=["universe_key", "theme", "value_eur"])
    if hasattr(portfolio, "holdings"):
        return portfolio.holdings.copy()
    if isinstance(portfolio, pd.DataFrame):
        return portfolio.copy()
    raise TypeError(f"Cannot extract holdings from {type(portfolio)}")


def var_contribution_sizing(
    portfolio: Any,
    returns: pd.DataFrame,
    target_theme_pct: float,
    theme: str,
    *,
    alpha: float = 0.95,
) -> pd.DataFrame:
    """Suggest per-position trims to bring ``theme`` VaR contribution under target.

    Parameters
    ----------
    portfolio : Portfolio | DataFrame
        Must expose `holdings` with columns universe_key, theme, value_eur.
    returns : pd.DataFrame
        Per-position daily returns, columns = universe_key.
    target_theme_pct : float
        Target contribution of the theme to portfolio VaR (as a fraction).
        e.g. 0.30 means "theme should not exceed 30% of portfolio VaR".
    theme : str
        Theme name to act on (e.g. "Energy", "Quantum").
    """
    holdings = _portfolio_holdings_df(portfolio)
    if holdings.empty:
        return pd.DataFrame(columns=_PANEL_COLS)
    if "universe_key" not in holdings.columns or "theme" not in holdings.columns:
        return pd.DataFrame(columns=_PANEL_COLS)

    weights_eur = (
        holdings.set_index("universe_key")["value_eur"].astype(float)
    )
    total_ev = float(weights_eur.sum())
    if total_ev <= 0:
        return pd.DataFrame(columns=_PANEL_COLS)
    weights = weights_eur / total_ev

    # Restrict returns to columns we have weights for
    cols = [c for c in returns.columns if c in weights.index]
    if not cols:
        return pd.DataFrame(columns=_PANEL_COLS)
    rets = returns[cols].dropna(how="any")
    if rets.empty or len(rets) < 5:
        log.warning("var_contribution_sizing: not enough return samples")
        return pd.DataFrame(columns=_PANEL_COLS)

    w_aligned = weights.reindex(cols).fillna(0.0)
    contrib = marginal_var(rets, w_aligned, alpha=alpha)
    # Portfolio total parametric VaR (used to denominate contributions)
    port_ret = rets.dot(w_aligned)
    var_p = float(parametric_var(port_ret, alpha=alpha))
    # parametric_var returns a (mostly negative) loss; use |.| for fractions
    var_abs = abs(var_p) if var_p != 0 else 1e-9

    contrib_abs = contrib.abs()
    contrib_pct_total = contrib_abs / var_abs

    theme_map = holdings.set_index("universe_key")["theme"].astype(str)
    in_theme = theme_map.reindex(cols).fillna("") == theme

    theme_contrib_pct = float(contrib_pct_total[in_theme].sum())

    # Compute scale factor: if already below target, no trim
    if theme_contrib_pct <= target_theme_pct or theme_contrib_pct <= 0:
        scale = 1.0
    else:
        scale = float(target_theme_pct / theme_contrib_pct)
        scale = max(0.0, min(1.0, scale))

    rows: list[dict[str, Any]] = []
    for ticker in cols:
        w_eur = float(weights_eur.get(ticker, 0.0))
        in_t = bool(in_theme.get(ticker, False))
        if in_t and scale < 1.0:
            new_eur = w_eur * scale
            trim = new_eur - w_eur  # negative
            rationale = (
                f"theme {theme} contributed {theme_contrib_pct:.1%} of VaR "
                f"(target {target_theme_pct:.1%}) -> scale {scale:.2f}"
            )
        else:
            new_eur = w_eur
            trim = 0.0
            rationale = "no trim required"
        rows.append({
            "ticker": ticker,
            "theme": str(theme_map.get(ticker, "")),
            "weight_eur": w_eur,
            "marginal_var": float(contrib.get(ticker, 0.0)),
            "contrib_pct_of_portfolio_var": float(contrib_pct_total.get(ticker, 0.0)),
            "in_theme": in_t,
            "suggested_trim_eur": float(trim),
            "suggested_weight_eur": float(new_eur),
            "rationale": rationale,
        })

    out = pd.DataFrame(rows, columns=_PANEL_COLS)
    return out.sort_values(["in_theme", "contrib_pct_of_portfolio_var"], ascending=[False, False]).reset_index(drop=True)
