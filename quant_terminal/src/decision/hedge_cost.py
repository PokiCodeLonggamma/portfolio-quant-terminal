"""Hedge cost — module I.

Two structures:

* **Protective collar** (`compute_collar`) — buy an OTM put + sell a
  further-OTM call at the same expiry; net premium is usually a small
  debit (sometimes credit). We pick the strikes closest to the requested
  offset and use mid prices when available.
* **Linear alternatives** (`linear_futures_alternatives`) — for 3x leveraged
  ETPs (or any holding without a healthy single-name option market) we
  suggest index futures / vanilla ETFs as cheap directional hedges.

Cluster 5 must NOT be a top-level hard import: we import inside the
function so the decision tests can monkeypatch `fetch_chain` without the
whole `src.trading.options_chain` module needing to be importable
end-to-end in CI.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Callable

import pandas as pd
import yaml

from src.common.schemas import CollarQuote, OptionContract, OptionRight
from src.utils.cache import read as cache_read, write as cache_write
from src.utils.config import get_config
from src.utils.logging import get_logger

log = get_logger(__name__)

_NS = "decision_hedge"


# Mappings for 3x ETPs / commodity exposures -> linear alternatives.
# Stored as code defaults; users can override via config/hedge_defaults.yaml.
_DEFAULT_LINEAR_MAP: dict[str, list[dict[str, str]]] = {
    "3OIL.L": [
        {"hedge": "USO", "kind": "ETF", "rationale": "linear WTI exposure (1x)"},
        {"hedge": "CL=F", "kind": "future", "rationale": "WTI crude futures, no roll drag overnight"},
        {"hedge": "SCO", "kind": "ETF", "rationale": "inverse WTI (-2x) for short bias"},
    ],
    "3DES.L": [
        {"hedge": "EXSA.DE", "kind": "ETF", "rationale": "linear DAX exposure"},
        {"hedge": "FDAX", "kind": "future", "rationale": "DAX index future (Eurex)"},
        {"hedge": "DAXX.L", "kind": "ETF", "rationale": "iShares Core DAX UCITS"},
    ],
    "3USL.L": [
        {"hedge": "SPY", "kind": "ETF", "rationale": "S&P 500 linear ETF"},
        {"hedge": "ES=F", "kind": "future", "rationale": "S&P 500 E-mini future"},
    ],
    "3LGO.L": [
        {"hedge": "GLD", "kind": "ETF", "rationale": "linear gold ETF"},
        {"hedge": "GC=F", "kind": "future", "rationale": "gold futures"},
    ],
}


def _load_linear_map() -> dict[str, list[dict[str, str]]]:
    cfg = get_config()
    path: Path = cfg.data_dir.parent / "config" / "hedge_defaults.yaml"
    merged = {k: list(v) for k, v in _DEFAULT_LINEAR_MAP.items()}
    if not path.exists():
        return merged
    try:
        with path.open("r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        for k, v in (data.get("linear_alternatives") or {}).items():
            if isinstance(v, list):
                merged[str(k).upper()] = list(v)
    except Exception as exc:
        log.warning("hedge_defaults.yaml unreadable, using defaults: %s", exc)
    return merged


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _spot_eur(ticker: str) -> float | None:
    """Best-effort spot in EUR. Lazy-imports loaders + fx."""
    try:
        from src.data.fx import convert_to_eur
        from src.data.loaders import load_one
        end = datetime.utcnow()
        start = end - timedelta(days=10)
        series = load_one(ticker, start, end)
        if series is None or series.empty:
            return None
        last = float(series.dropna().iloc[-1])
        currency = get_config().currency_of(ticker)
        if currency.upper() == "EUR":
            return last
        return float(convert_to_eur(last, currency))
    except Exception as exc:
        log.debug("spot_eur failed for %s: %s", ticker, exc)
        return None


def _resolve_chain_fetcher() -> Callable[..., list[OptionContract]]:
    """Lazy import so tests can monkeypatch."""
    from src.trading.options_chain import fetch_chain  # noqa: WPS433
    return fetch_chain


def _option_price(c: OptionContract) -> float | None:
    """Pick a sensible execution price: mid > last > ask > bid."""
    for v in (c.mid, c.last, c.ask, c.bid):
        if v is not None and v > 0:
            return float(v)
    return None


def _pick_strike(
    chain: list[OptionContract],
    *,
    right: OptionRight,
    target_strike: float,
) -> OptionContract | None:
    cands = [c for c in chain if c.right == right and _option_price(c) is not None]
    if not cands:
        return None
    return min(cands, key=lambda c: abs(c.strike - target_strike))


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def compute_collar(
    ticker: str,
    position_eur: float,
    *,
    dte_days: int = 90,
    call_otm_pct: float = 0.15,
    put_otm_pct: float = 0.10,
    spot_eur: float | None = None,
    chain: list[OptionContract] | None = None,
    fetch_chain: Callable[..., list[OptionContract]] | None = None,
) -> CollarQuote | None:
    """Compute a protective-collar quote for a long position.

    Buys an OTM put ``put_otm_pct`` below spot and sells a call
    ``call_otm_pct`` above spot, with the closest available expiry to
    ``dte_days``.

    Returns None if no usable chain is found.

    Test seam: ``fetch_chain`` and/or pre-built ``chain`` can be supplied
    so unit tests don't hit the network.
    """
    t = (ticker or "").upper().strip()
    if not t:
        return None
    if position_eur is None or position_eur <= 0:
        log.warning("compute_collar: non-positive position_eur for %s", t)
        return None

    spot = spot_eur if spot_eur is not None else _spot_eur(t)
    if spot is None or spot <= 0:
        log.info("compute_collar: no spot for %s", t)
        return None

    target_dte = max(7, int(dte_days))
    window = (max(7, target_dte - 30), target_dte + 30)

    cache_key = f"{t}|{position_eur:.0f}|{target_dte}|{call_otm_pct:.3f}|{put_otm_pct:.3f}"
    cached = cache_read(cache_key, namespace=_NS, max_age_seconds=15 * 60)
    if cached is not None and not cached.empty:
        try:
            row = cached.iloc[0].to_dict()
            return CollarQuote(
                ticker=row["ticker"],
                underlying_px_eur=float(row["underlying_px_eur"]),
                expiry=date.fromisoformat(row["expiry"]),
                long_put_strike=float(row["long_put_strike"]),
                short_call_strike=float(row["short_call_strike"]),
                put_debit_eur=float(row["put_debit_eur"]),
                call_credit_eur=float(row["call_credit_eur"]),
                net_premium_eur=float(row["net_premium_eur"]),
                cost_pct_notional=float(row["cost_pct_notional"]),
                breakeven_low=float(row["breakeven_low"]),
                breakeven_high=float(row["breakeven_high"]),
                max_loss_eur=float(row["max_loss_eur"]),
                max_gain_eur=float(row["max_gain_eur"]),
                notes=row.get("notes", ""),
            )
        except Exception:
            pass

    if chain is None:
        fetcher = fetch_chain or _resolve_chain_fetcher()
        try:
            chain = fetcher(t, target_dte_window=window) or []
        except Exception as exc:
            log.info("compute_collar: fetch_chain failed for %s: %s", t, exc)
            return None
    if not chain:
        return None

    # Choose the expiry closest to target_dte; tie-break to the later expiry
    today = date.today()
    expiries = sorted({c.expiry for c in chain})
    if not expiries:
        return None
    best_exp = min(expiries, key=lambda e: (abs((e - today).days - target_dte), -(e - today).days))
    chain_at_exp = [c for c in chain if c.expiry == best_exp]

    target_put_strike = spot * (1.0 - float(put_otm_pct))
    target_call_strike = spot * (1.0 + float(call_otm_pct))

    put = _pick_strike(chain_at_exp, right=OptionRight.PUT, target_strike=target_put_strike)
    call = _pick_strike(chain_at_exp, right=OptionRight.CALL, target_strike=target_call_strike)
    if put is None or call is None:
        log.info("compute_collar: missing put or call for %s @ %s", t, best_exp)
        return None

    put_px = _option_price(put) or 0.0
    call_px = _option_price(call) or 0.0

    # Number of "shares-equivalent" the position represents in EUR
    shares_equiv = position_eur / spot
    # Each contract = 100 shares (standard US); approximate exposure ratio
    contracts = max(1.0, shares_equiv / 100.0)

    put_debit_eur = put_px * 100.0 * contracts
    call_credit_eur = call_px * 100.0 * contracts
    net_premium_eur = put_debit_eur - call_credit_eur

    # P/L envelope at expiry vs spot today (collar economics):
    # below put strike: loss = (put_strike - spot) - net_premium  (per share)
    # above call strike: gain = (call_strike - spot) - net_premium (per share)
    per_share_max_loss = (spot - put.strike) - (net_premium_eur / max(shares_equiv, 1e-9))
    per_share_max_gain = (call.strike - spot) - (net_premium_eur / max(shares_equiv, 1e-9))
    max_loss_eur = -float(abs(per_share_max_loss) * shares_equiv)
    max_gain_eur = float(per_share_max_gain * shares_equiv)

    breakeven_low = float(put.strike + (net_premium_eur / max(shares_equiv, 1e-9)))
    breakeven_high = float(call.strike + (net_premium_eur / max(shares_equiv, 1e-9)))
    cost_pct = float(net_premium_eur / position_eur) if position_eur > 0 else 0.0

    out = CollarQuote(
        ticker=t,
        underlying_px_eur=float(spot),
        expiry=best_exp,
        long_put_strike=float(put.strike),
        short_call_strike=float(call.strike),
        put_debit_eur=float(put_debit_eur),
        call_credit_eur=float(call_credit_eur),
        net_premium_eur=float(net_premium_eur),
        cost_pct_notional=cost_pct,
        breakeven_low=breakeven_low,
        breakeven_high=breakeven_high,
        max_loss_eur=max_loss_eur,
        max_gain_eur=max_gain_eur,
        notes=(
            f"put {put.symbol} @ ${put_px:.2f}, "
            f"call {call.symbol} @ ${call_px:.2f}, "
            f"~{contracts:.1f} contracts"
        ),
    )

    try:
        cache_df = pd.DataFrame([{
            "ticker": out.ticker,
            "underlying_px_eur": out.underlying_px_eur,
            "expiry": out.expiry.isoformat(),
            "long_put_strike": out.long_put_strike,
            "short_call_strike": out.short_call_strike,
            "put_debit_eur": out.put_debit_eur,
            "call_credit_eur": out.call_credit_eur,
            "net_premium_eur": out.net_premium_eur,
            "cost_pct_notional": out.cost_pct_notional,
            "breakeven_low": out.breakeven_low,
            "breakeven_high": out.breakeven_high,
            "max_loss_eur": out.max_loss_eur,
            "max_gain_eur": out.max_gain_eur,
            "notes": out.notes,
        }])
        cache_write(cache_key, cache_df, namespace=_NS)
    except Exception as exc:
        log.debug("collar cache write failed for %s: %s", t, exc)

    return out


def linear_futures_alternatives(ticker: str) -> list[dict[str, Any]]:
    """Return linear / vanilla hedge alternatives for ``ticker``.

    Useful for 3x leveraged ETPs (e.g. 3DES.L, 3OIL.L) and other
    instruments whose option markets are too thin to collar.

    Returns an empty list when no mapping exists.
    """
    mapping = _load_linear_map()
    t = (ticker or "").upper().strip()
    return list(mapping.get(t, []))


# ---------------------------------------------------------------------------
# Portfolio-level panel (one row per holding)
# ---------------------------------------------------------------------------
_PANEL_COLS = [
    "ticker", "structure", "expiry", "long_put_strike", "short_call_strike",
    "net_premium_eur", "cost_pct_notional", "max_loss_eur", "max_gain_eur",
    "linear_alternatives", "notes",
]


def portfolio_hedge_panel(
    portfolio: Any,
    *,
    dte_days: int = 90,
    call_otm_pct: float = 0.15,
    put_otm_pct: float = 0.10,
    fetch_chain: Callable[..., list[OptionContract]] | None = None,
) -> pd.DataFrame:
    """Build a hedge-cost panel for every position. Linear alternatives are
    surfaced when no collar can be priced."""
    if portfolio is None or not hasattr(portfolio, "holdings"):
        return pd.DataFrame(columns=_PANEL_COLS)
    rows: list[dict[str, Any]] = []
    for _, h in portfolio.holdings.iterrows():
        t = str(h.get("universe_key") or h.get("symbol") or "").upper()
        if not t:
            continue
        position_eur = float(h.get("value_eur", 0.0) or 0.0)
        if position_eur <= 0:
            continue
        quote = compute_collar(
            t, position_eur,
            dte_days=dte_days,
            call_otm_pct=call_otm_pct,
            put_otm_pct=put_otm_pct,
            fetch_chain=fetch_chain,
        )
        alts = linear_futures_alternatives(t)
        alts_str = ", ".join(f"{a.get('hedge', '?')} ({a.get('kind', '')})" for a in alts) if alts else ""
        if quote is None:
            rows.append({
                "ticker": t,
                "structure": "n/a",
                "expiry": None,
                "long_put_strike": None,
                "short_call_strike": None,
                "net_premium_eur": None,
                "cost_pct_notional": None,
                "max_loss_eur": None,
                "max_gain_eur": None,
                "linear_alternatives": alts_str,
                "notes": "no chain available — use linear alternatives",
            })
        else:
            rows.append({
                "ticker": t,
                "structure": "collar",
                "expiry": quote.expiry,
                "long_put_strike": quote.long_put_strike,
                "short_call_strike": quote.short_call_strike,
                "net_premium_eur": quote.net_premium_eur,
                "cost_pct_notional": quote.cost_pct_notional,
                "max_loss_eur": quote.max_loss_eur,
                "max_gain_eur": quote.max_gain_eur,
                "linear_alternatives": alts_str,
                "notes": quote.notes,
            })
    if not rows:
        return pd.DataFrame(columns=_PANEL_COLS)
    return pd.DataFrame(rows)
