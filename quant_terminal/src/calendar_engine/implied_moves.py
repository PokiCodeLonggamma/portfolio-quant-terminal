"""Implied move from the ATM straddle.

Given a ticker and a target days-to-expiry (DTE), this module finds the
closest expiry quoted on the chain, locates the at-the-money call + put,
and returns the implied move as ``straddle_mid / spot``.

The function is intentionally lenient: if the chain is empty, if the ATM
strike has no quotes, or if the spot is unknown, we return ``None`` instead
of raising.

Public API
----------
* `implied_move(ticker, dte_days=30) -> float | None`
* `implied_move_summary(ticker, dte_days=30) -> dict`
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

from src.common.schemas import OptionContract, OptionRight
from src.utils.logging import get_logger

log = get_logger(__name__)


def _safe_spot(ticker: str) -> float | None:
    """Best-effort spot fetch via the shared loader."""
    try:
        from src.data.loaders import load_one
        end = datetime.utcnow()
        start = end - timedelta(days=10)
        s = load_one(ticker, start, end)
        if s is None or s.empty:
            return None
        return float(s.dropna().iloc[-1])
    except Exception as exc:
        log.debug("spot lookup failed for %s: %s", ticker, exc)
        return None


def _pick_expiry(chain: list[OptionContract], dte_days: int) -> date | None:
    if not chain:
        return None
    today = date.today()
    expiries = sorted({c.expiry for c in chain})
    if not expiries:
        return None
    # Closest to target dte, prefer future expiries.
    future = [e for e in expiries if e >= today]
    candidates = future or expiries
    target = today + timedelta(days=int(dte_days))
    return min(candidates, key=lambda e: abs((e - target).days))


def _atm_straddle_mid(
    chain: list[OptionContract], expiry: date, spot: float,
) -> float | None:
    """Return mid(call) + mid(put) at the strike closest to spot, or None."""
    if not chain or spot is None or spot <= 0:
        return None
    same_exp = [c for c in chain if c.expiry == expiry]
    if not same_exp:
        return None
    strikes = sorted({c.strike for c in same_exp})
    if not strikes:
        return None
    k = min(strikes, key=lambda s: abs(s - spot))
    call = next(
        (c for c in same_exp if c.strike == k and c.right == OptionRight.CALL),
        None,
    )
    put = next(
        (c for c in same_exp if c.strike == k and c.right == OptionRight.PUT),
        None,
    )

    def _quote(c: OptionContract | None) -> float | None:
        if c is None:
            return None
        if c.mid is not None and c.mid > 0:
            return float(c.mid)
        if c.bid is not None and c.ask is not None and c.bid > 0 and c.ask > 0:
            return 0.5 * (float(c.bid) + float(c.ask))
        if c.last is not None and c.last > 0:
            return float(c.last)
        return None

    c_px = _quote(call)
    p_px = _quote(put)
    if c_px is None or p_px is None:
        return None
    return c_px + p_px


def implied_move(
    ticker: str,
    dte_days: int = 30,
    *,
    fetch_chain_fn=None,
    spot: float | None = None,
) -> float | None:
    """Return implied move % (decimal) for `ticker` at the chosen expiry.

    Parameters
    ----------
    ticker
        Universe ticker (e.g. ``"ASTS"``).
    dte_days
        Target days-to-expiry — the function picks the closest available
        expiry on the chain.
    fetch_chain_fn
        Optional override (used by tests).  Defaults to
        :func:`src.trading.options_chain.fetch_chain`.
    spot
        Optional override (used by tests).  Defaults to a fresh
        :func:`_safe_spot` call.
    """
    if fetch_chain_fn is None:
        try:
            from src.trading.options_chain import fetch_chain as _fc
            fetch_chain_fn = _fc
        except Exception as exc:
            log.debug("options_chain unavailable: %s", exc)
            return None

    try:
        chain = fetch_chain_fn(
            ticker, target_dte_window=(max(1, dte_days - 14), dte_days + 30),
        )
    except TypeError:
        # custom fetch_chain in tests may have a simpler signature
        try:
            chain = fetch_chain_fn(ticker)
        except Exception as exc:
            log.debug("fetch_chain failed for %s: %s", ticker, exc)
            return None
    except Exception as exc:
        log.debug("fetch_chain failed for %s: %s", ticker, exc)
        return None

    if not chain:
        return None

    expiry = _pick_expiry(chain, dte_days)
    if expiry is None:
        return None
    if spot is None:
        spot = _safe_spot(ticker)
    if spot is None or spot <= 0:
        return None
    straddle = _atm_straddle_mid(chain, expiry, spot)
    if straddle is None:
        return None
    move = straddle / spot
    if move <= 0:
        return None
    return float(move)


def implied_move_summary(
    ticker: str, dte_days: int = 30, *, fetch_chain_fn=None, spot: float | None = None,
) -> dict:
    """Verbose variant used by the earnings board.

    Returns dict with keys ``{ticker, dte_days, expiry, spot, straddle, move_pct}``.
    Any field can be ``None`` if not computable.
    """
    if fetch_chain_fn is None:
        try:
            from src.trading.options_chain import fetch_chain as _fc
            fetch_chain_fn = _fc
        except Exception:
            fetch_chain_fn = None
    if fetch_chain_fn is None:
        return {"ticker": ticker, "dte_days": dte_days, "expiry": None,
                "spot": None, "straddle": None, "move_pct": None}
    try:
        chain = fetch_chain_fn(ticker)
    except Exception:
        chain = []
    if spot is None:
        spot = _safe_spot(ticker)
    expiry = _pick_expiry(chain, dte_days)
    straddle = (
        _atm_straddle_mid(chain, expiry, spot)
        if (chain and expiry is not None and spot is not None and spot > 0)
        else None
    )
    move = (straddle / spot) if (straddle is not None and spot) else None
    return {
        "ticker": ticker, "dte_days": dte_days,
        "expiry": expiry, "spot": spot, "straddle": straddle,
        "move_pct": move,
    }
