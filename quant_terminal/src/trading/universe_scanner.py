"""Options universe scanner.

For a list of tickers, scan all chains and rank the best Δ-25 long
call / long put setups by a composite score combining:
  - Implied move vs realised vol (cheap/expensive premium)
  - IV rank (low IV = cheap; high IV = expensive)
  - GEX setup (negative gamma zone around spot = potentially explosive)
  - OI depth (avoid illiquid strikes)
  - Squeeze score if available

Output is a tidy DataFrame consumable by render_universe_scanner.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Callable

import pandas as pd

from src.common.schemas import OptionContract, OptionRight
from src.trading.gex import compute_gex, gamma_flip_strike, negative_gamma_zone
from src.trading.gex_enrich import put_call_ratio
from src.trading.iv_analytics import iv_term_structure
from src.utils.logging import get_logger

log = get_logger(__name__)


# Default trading universe — sector ETFs + portfolio volatile names.
DEFAULT_UNIVERSE: list[str] = [
    # Sector ETFs
    "SPY", "QQQ", "XLE", "XLF", "URA", "ARKX", "QTUM", "SMH", "SOXX",
    "GDX", "USO",
    # Speculative single names from the portfolio + watchlists
    "ASTS", "RDW", "BKSY", "IONQ", "RKLB", "AAOI", "QS", "ONDS", "CCJ",
    "GOOG", "AAPL", "TSLA",
]


@dataclass
class ScanResult:
    ticker: str
    spot: float | None
    chain_size: int
    atm_iv: float | None
    delta25_call_strike: float | None
    delta25_call_premium: float | None
    delta25_put_strike: float | None
    delta25_put_premium: float | None
    gamma_flip: float | None
    neg_gamma_zone: tuple[float | None, float | None]
    put_call_ratio: float
    score: float
    notes: list[str]


def _closest_delta(
    contracts: list[OptionContract], target: float, right: OptionRight,
) -> OptionContract | None:
    pool = [c for c in contracts if c.right == right and c.delta is not None]
    if not pool:
        return None
    return min(pool, key=lambda c: abs(abs(float(c.delta)) - abs(target)))


def _scan_one(
    ticker: str,
    fetch_chain_fn: Callable[..., list[OptionContract]],
    spot_lookup: dict[str, float],
) -> ScanResult | None:
    spot = spot_lookup.get(ticker)
    # Fallback: when the loaded portfolio's prices_eur doesn't cover this
    # ticker (e.g. SPY/QQQ scanned without DEGIRO upload), pull spot from
    # yfinance fast_info via the chain helper. Without this fallback the
    # scanner returns nothing on Streamlit Cloud cold-starts.
    if spot is None or spot <= 0:
        try:
            from src.trading.options_chain import _safe_spot
            spot = _safe_spot(ticker)
        except Exception as exc:
            log.debug("scanner: %s spot fallback failed: %s", ticker, exc)
            return None
    if spot is None or spot <= 0:
        return None
    try:
        chain = fetch_chain_fn(ticker)
    except Exception as exc:
        log.debug("scanner: %s chain fetch failed: %s", ticker, exc)
        return None
    if not chain:
        return None

    notes: list[str] = []
    # ATM IV from term-structure (nearest expiry)
    ts = iv_term_structure(chain, spot)
    atm_iv = float(ts["atm_iv_avg"].dropna().iloc[0]) if not ts.empty and not ts["atm_iv_avg"].dropna().empty else None

    # Δ-25 setups on nearest expiry
    nearest = min({c.expiry for c in chain}) if chain else None
    near_pool = [c for c in chain if c.expiry == nearest] if nearest else []
    call25 = _closest_delta(near_pool, 0.25, OptionRight.CALL)
    put25 = _closest_delta(near_pool, -0.25, OptionRight.PUT)

    # GEX
    gex_df = compute_gex(chain, spot)
    flip = gamma_flip_strike(gex_df)
    lo, hi = negative_gamma_zone(gex_df, spot=spot, pct=0.05)
    pc_dict = put_call_ratio(chain)

    # Composite score
    score = 0.0
    if call25 is not None and call25.iv is not None:
        # Low IV = cheap = bullish bias score
        score += max(0.0, 50.0 - call25.iv * 100)
        notes.append(f"call25 IV {call25.iv * 100:.0f}%")
    if (lo is not None and hi is not None) and (lo <= spot <= hi):
        score += 25.0
        notes.append(f"spot inside negative-gamma zone [{lo:.1f}, {hi:.1f}]")
    if pc_dict["overall_pc_ratio"] > 1.5:
        score += 10.0
        notes.append(f"PC ratio {pc_dict['overall_pc_ratio']:.2f} (bearish skew)")
    elif pc_dict["overall_pc_ratio"] < 0.5:
        score += 10.0
        notes.append(f"PC ratio {pc_dict['overall_pc_ratio']:.2f} (bullish skew)")

    return ScanResult(
        ticker=ticker,
        spot=spot,
        chain_size=len(chain),
        atm_iv=atm_iv,
        delta25_call_strike=float(call25.strike) if call25 else None,
        delta25_call_premium=(float(call25.mid or call25.last or 0.0) * 100) if call25 else None,
        delta25_put_strike=float(put25.strike) if put25 else None,
        delta25_put_premium=(float(put25.mid or put25.last or 0.0) * 100) if put25 else None,
        gamma_flip=flip,
        neg_gamma_zone=(lo, hi),
        put_call_ratio=float(pc_dict["overall_pc_ratio"]),
        score=score,
        notes=notes,
    )


def scan_universe(
    universe: list[str] | None,
    fetch_chain_fn: Callable[..., list[OptionContract]],
    spot_lookup: dict[str, float],
) -> pd.DataFrame:
    """Run the scanner across `universe` (default DEFAULT_UNIVERSE).

    Returns a DataFrame sorted by composite score desc with columns:
      ticker, spot, atm_iv, delta25_call_strike, delta25_call_premium,
      delta25_put_strike, delta25_put_premium, gamma_flip,
      neg_gamma_lo, neg_gamma_hi, put_call_ratio, score, notes,
      asof.
    """
    if not universe:
        universe = DEFAULT_UNIVERSE
    now = datetime.utcnow().isoformat(timespec="seconds")
    rows = []
    for t in sorted(set(universe)):
        res = _scan_one(t, fetch_chain_fn, spot_lookup)
        if res is None:
            continue
        rows.append({
            "ticker": res.ticker,
            "spot": res.spot,
            "chain_size": res.chain_size,
            "atm_iv_pct": round(res.atm_iv * 100, 1) if res.atm_iv else None,
            "delta25_call_strike": res.delta25_call_strike,
            "delta25_call_premium_usd": round(res.delta25_call_premium, 1) if res.delta25_call_premium else None,
            "delta25_put_strike": res.delta25_put_strike,
            "delta25_put_premium_usd": round(res.delta25_put_premium, 1) if res.delta25_put_premium else None,
            "gamma_flip": res.gamma_flip,
            "neg_gamma_lo": res.neg_gamma_zone[0],
            "neg_gamma_hi": res.neg_gamma_zone[1],
            "put_call_ratio": round(res.put_call_ratio, 2),
            "score": round(res.score, 1),
            "notes": " · ".join(res.notes),
            "asof": now,
        })
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows).sort_values("score", ascending=False).reset_index(drop=True)
