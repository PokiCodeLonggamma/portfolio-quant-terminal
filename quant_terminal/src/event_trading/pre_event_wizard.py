"""Pre-event wizard — for a given upcoming event, rank candidate setups.

Workflow:
1. User picks an event (or category + horizon).
2. For each candidate ticker in the trading universe:
     - fetch the chain (Alpaca/yfinance) close to the event date
     - find the delta-0.25 call AND put (or straddle)
     - compute implied move (ATM straddle / spot) and IV rank
     - compare to historical_avg_move_pct(ticker, category)
3. Rank by `expected_value_score` = historical_avg_move / implied_move,
   penalised by IV-rank (high IV = expensive premium).
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Callable, Iterable

import pandas as pd

from src.common.schemas import CalendarEvent, EventSetup, OptionContract, OptionRight
from src.event_trading.event_sensitivity import historical_avg_move_pct
from src.utils.logging import get_logger

log = get_logger(__name__)


def _closest_delta(contracts: list[OptionContract], target: float,
                   right: OptionRight) -> OptionContract | None:
    candidates = [c for c in contracts if c.right == right and c.delta is not None]
    if not candidates:
        return None
    target_abs = abs(target)

    def _key(c: OptionContract) -> float:
        return abs(abs(float(c.delta)) - target_abs)

    return sorted(candidates, key=_key)[0]


def _atm_straddle_implied_move(
    contracts: list[OptionContract],
    spot: float,
    expiry: date,
) -> float | None:
    if not contracts or spot <= 0:
        return None
    same_expiry = [c for c in contracts if c.expiry == expiry]
    if not same_expiry:
        return None
    # Pick the call + put nearest spot
    calls = [c for c in same_expiry if c.right == OptionRight.CALL]
    puts  = [c for c in same_expiry if c.right == OptionRight.PUT]
    if not calls or not puts:
        return None
    atm_call = sorted(calls, key=lambda c: abs(c.strike - spot))[0]
    atm_put  = sorted(puts,  key=lambda c: abs(c.strike - spot))[0]
    call_px = float(atm_call.mid or atm_call.last or atm_call.bid or 0.0)
    put_px = float(atm_put.mid or atm_put.last or atm_put.bid or 0.0)
    if call_px <= 0 or put_px <= 0:
        return None
    return float((call_px + put_px) / spot)  # decimal (e.g. 0.08 = 8%)


def candidates_for_event(
    event: CalendarEvent,
    universe: Iterable[str],
    *,
    spot_lookup: dict[str, float] | None = None,
    fetch_chain_fn: Callable[..., list[OptionContract]] | None = None,
    iv_rank_lookup: Callable[[str], float] | None = None,
    fx_to_eur: float = 1.10,
    target_delta: float = 0.25,
) -> pd.DataFrame:
    """Return a DataFrame of EventSetup rows, ranked by expected-value score."""
    spot_lookup = spot_lookup or {}
    rows: list[dict] = []
    target_expiry = (event.start.date() + timedelta(days=14))  # 14d post-event default

    for t in sorted(set(universe)):
        spot = spot_lookup.get(t)
        if spot is None:
            continue
        if fetch_chain_fn is None:
            continue
        try:
            chain = fetch_chain_fn(t)
        except Exception as exc:
            log.warning("chain fetch failed for %s: %s", t, exc)
            continue
        if not chain:
            continue
        # Use the first expiry >= target_expiry
        expiries = sorted({c.expiry for c in chain if c.expiry >= target_expiry})
        if not expiries:
            continue
        expiry = expiries[0]

        call = _closest_delta(
            [c for c in chain if c.expiry == expiry],
            target=target_delta, right=OptionRight.CALL,
        )
        put = _closest_delta(
            [c for c in chain if c.expiry == expiry],
            target=target_delta, right=OptionRight.PUT,
        )
        implied = _atm_straddle_implied_move(chain, spot, expiry)
        historical = historical_avg_move_pct(t, event.category) or 0.0
        iv_rank = float(iv_rank_lookup(t)) if iv_rank_lookup else None

        # Build setup for both directions and pick the better one
        for direction, contract in (("LONG_CALL", call), ("LONG_PUT", put)):
            if contract is None:
                continue
            debit_usd = (contract.mid or contract.last or contract.ask or 0.0) * 100
            score = 0.0
            rationale: list[str] = []
            if implied:
                # We pay implied_move × 100 in premium; we expect historical move
                ratio = (historical / 100.0) / max(implied, 1e-6)
                score = ratio * 100
                rationale.append(f"hist {historical:.1f}% / impl {implied * 100:.1f}% → {ratio:.2f}")
            if iv_rank is not None:
                # Penalise high IV rank (expensive vol)
                penalty = max(0.0, (iv_rank - 50.0) * 0.5)
                score -= penalty
                rationale.append(f"IV rank {iv_rank:.0f} (penalty {penalty:.0f})")

            rows.append({
                "ticker": t,
                "event_id": event.event_id,
                "event_category": event.category,
                "direction": direction,
                "iv_rank": iv_rank,
                "implied_move_pct": float(implied * 100) if implied else None,
                "historical_avg_move_pct": historical,
                "target_delta": target_delta,
                "strike": float(contract.strike),
                "expiry": expiry,
                "debit_usd": float(debit_usd),
                "debit_eur": float(debit_usd / fx_to_eur) if fx_to_eur else None,
                "score": float(score),
                "rationale": " · ".join(rationale),
            })

    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows).sort_values("score", ascending=False)
    return df
