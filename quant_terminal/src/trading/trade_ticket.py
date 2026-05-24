"""Trade ticket generator — directional LONG_CALL / LONG_PUT only.

Encodes the user's hard gating rules (see brief):
    * IV rank > 80                    → refuse
    * Open interest on strike < 100   → refuse
    * Total debit > 2% of net EV      → refuse
    * Delta tolerance |Δ - 0.25| <= 0.05
    * DTE window 14–45 days

USD-denominated option prices are converted to EUR via `src.data.fx.to_eur`.
"""
from __future__ import annotations

from datetime import datetime
from typing import Callable, Literal

from src.common.schemas import OptionContract, OptionRight, TradeTicket
from src.data.fx import to_eur
from src.trading.delta_finder import closest_delta
from src.trading.iv_rank import iv_rank as _iv_rank
from src.trading.options_chain import fetch_chain as _fetch_chain
from src.utils.config import get_config
from src.utils.logging import get_logger

log = get_logger(__name__)

GATE_DEFAULTS = {
    "iv_rank_max": 80.0,
    "oi_min": 100,
    "debit_max_pct_net_ev": 0.02,
    "target_delta": 0.25,
    "dte_min": 14,
    "dte_max": 45,
    "delta_tolerance": 0.05,
}


def _resolve_mid_usd(contract: OptionContract) -> float | None:
    if contract.mid is not None and contract.mid > 0:
        return contract.mid
    if contract.bid is not None and contract.ask is not None and contract.bid > 0 and contract.ask > 0:
        return 0.5 * (contract.bid + contract.ask)
    if contract.last is not None and contract.last > 0:
        return contract.last
    return None


def _underlying_currency(ticker: str) -> str:
    """Best-effort currency from universe.yaml; default USD (options are US)."""
    try:
        return (get_config().currency_of(ticker) or "USD").upper()
    except Exception:
        return "USD"


def build_ticket(
    ticker: str,
    direction: Literal["LONG_CALL", "LONG_PUT"],
    target_delta: float,
    max_debit_eur: float | None,
    net_ev_eur: float,
    dte_window: tuple[int, int] = (14, 45),
    *,
    iv_rank_val: float | None = None,
    fetch_chain_fn: Callable[..., list[OptionContract]] | None = None,
    iv_rank_fn: Callable[[str], float] | None = None,
    gates: dict | None = None,
) -> TradeTicket:
    """Produce a `TradeTicket`. All gates evaluated; `refused_reasons` populated
    when any check fails, but the ticket is **still returned** so the UI can
    explain to the user *why* the trade was rejected.

    Optional `fetch_chain_fn` / `iv_rank_fn` injection points exist for tests
    that need full determinism.
    """
    g = {**GATE_DEFAULTS, **(gates or {})}
    fetch = fetch_chain_fn or _fetch_chain
    iv_fn = iv_rank_fn or (lambda t: _iv_rank(t))
    refused: list[str] = []

    # 1. Pull chain restricted to the DTE window
    contracts = fetch(ticker, target_dte_window=dte_window)
    right = OptionRight.CALL if direction == "LONG_CALL" else OptionRight.PUT

    # 2. Pick the closest-delta contract
    pick = closest_delta(
        contracts, target_delta=target_delta, right=right,
        tolerance=float(g["delta_tolerance"]),
    )
    snapshot_ts = datetime.utcnow()

    # If nothing meets the delta criterion at all, return an empty ticket with
    # one refusal line — UI handles the rest.
    if pick is None:
        return TradeTicket(
            ticker=ticker, direction=direction,
            expiry=snapshot_ts.date(), strike=0.0,
            mid_eur=0.0, debit_eur=0.0,
            target_delta=target_delta, actual_delta=0.0,
            breakeven=0.0, rr_1_to_1=0.0, pct_of_net_ev=0.0,
            refused_reasons=[
                f"No contract within ±{g['delta_tolerance']} of target delta "
                f"{target_delta} in DTE window {dte_window}."
            ],
            contract_symbol="",
            snapshot_ts=snapshot_ts,
        )

    # 3. Price → EUR
    mid_usd = _resolve_mid_usd(pick) or 0.0
    debit_usd = mid_usd * 100.0   # one contract = 100 shares
    ccy = _underlying_currency(ticker)
    mid_eur = to_eur(mid_usd, ccy)
    debit_eur = to_eur(debit_usd, ccy)

    # 4. Breakeven & R/R
    if direction == "LONG_CALL":
        breakeven = pick.strike + mid_usd
    else:
        breakeven = max(0.0, pick.strike - mid_usd)
    # R/R 1:1 = profit if underlying moves +1 expected move ~= +1 sigma. Use
    # IV * sqrt(T) as expected move pct, multiplied by strike.
    T = max((pick.expiry - snapshot_ts.date()).days / 365.0, 1e-4)
    sigma = pick.iv or 0.30
    expected_move = sigma * (T ** 0.5) * pick.strike
    if mid_usd > 0:
        # Long call: payoff at +EM = max(0, S+EM - K) - mid;   loss at -EM = mid
        # Long put : payoff at -EM = max(0, K - (S-EM)) - mid; loss at +EM = mid
        spot_proxy = pick.strike / max(abs(pick.delta or 0.25), 1e-4) * abs(pick.delta or 0.25)
        # Simpler: assume current spot ≈ strike / (1 +/- expected pct). For
        # ticket purposes we approximate spot ≈ pick.strike (delta ≈ 0.25
        # call sits modestly OTM; close enough for an R/R rule-of-thumb).
        if direction == "LONG_CALL":
            payoff_up = max(0.0, (pick.strike + expected_move) - pick.strike) - mid_usd
        else:
            payoff_up = max(0.0, pick.strike - (pick.strike - expected_move)) - mid_usd
        rr = payoff_up / mid_usd if mid_usd > 0 else 0.0
        _ = spot_proxy  # silence unused
    else:
        rr = 0.0

    pct_of_net_ev = (debit_eur / net_ev_eur) if net_ev_eur and net_ev_eur > 0 else 0.0

    # 5. Hard gates
    # 5a. IV rank
    iv_rank_actual = iv_rank_val if iv_rank_val is not None else float(iv_fn(ticker))
    if iv_rank_actual > float(g["iv_rank_max"]):
        refused.append(
            f"IV rank {iv_rank_actual:.1f} > {g['iv_rank_max']:.0f} (paying rich premium)."
        )
    # 5b. OI
    oi = pick.open_interest or 0
    if oi < int(g["oi_min"]):
        refused.append(f"Open interest {oi} < {g['oi_min']} (illiquid strike).")
    # 5c. Debit vs net EV
    debit_cap_pct = float(g["debit_max_pct_net_ev"])
    if pct_of_net_ev > debit_cap_pct:
        refused.append(
            f"Debit {debit_eur:.2f}€ = {pct_of_net_ev * 100:.2f}% of net EV "
            f"> {debit_cap_pct * 100:.1f}% cap."
        )
    # 5d. max_debit_eur (optional user-imposed)
    if max_debit_eur is not None and debit_eur > max_debit_eur:
        refused.append(f"Debit {debit_eur:.2f}€ > user max {max_debit_eur:.2f}€.")
    # 5e. mid price sanity
    if mid_usd <= 0:
        refused.append("No quotable mid price (illiquid contract).")

    return TradeTicket(
        ticker=ticker,
        direction=direction,
        expiry=pick.expiry,
        strike=pick.strike,
        mid_eur=mid_eur,
        debit_eur=debit_eur,
        target_delta=target_delta,
        actual_delta=float(pick.delta or 0.0),
        breakeven=breakeven,
        rr_1_to_1=float(rr),
        pct_of_net_ev=pct_of_net_ev,
        refused_reasons=refused,
        contract_symbol=pick.symbol,
        snapshot_ts=snapshot_ts,
    )


# ---------------------------------------------------------------------------
# Aliases matching the Phase 1 plan public interface
# ---------------------------------------------------------------------------
def generate_ticket(
    ticker: str, *,
    direction: Literal["LONG_CALL", "LONG_PUT"],
    net_ev_eur: float,
    target_delta: float = 0.25,
    max_debit_eur: float | None = None,
    dte_window: tuple[int, int] = (14, 45),
) -> TradeTicket:
    return build_ticket(
        ticker, direction, target_delta, max_debit_eur, net_ev_eur, dte_window,
    )


def evaluate_gates(ticket: TradeTicket, *, iv_rank_val: float) -> list[str]:
    """Re-evaluate gates against a pre-built ticket (used by the UI when the
    user tweaks gating parameters live)."""
    reasons: list[str] = []
    if iv_rank_val > GATE_DEFAULTS["iv_rank_max"]:
        reasons.append(f"IV rank {iv_rank_val:.1f} > {GATE_DEFAULTS['iv_rank_max']:.0f}.")
    if ticket.pct_of_net_ev > GATE_DEFAULTS["debit_max_pct_net_ev"]:
        reasons.append(
            f"Debit {ticket.pct_of_net_ev * 100:.2f}% > "
            f"{GATE_DEFAULTS['debit_max_pct_net_ev'] * 100:.1f}% cap."
        )
    return reasons
