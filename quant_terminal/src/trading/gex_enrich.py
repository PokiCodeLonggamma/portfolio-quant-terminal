"""GEX enrichments — max pain, put/call ratio, 25Δ skew, OI delta tracker.

Pure functions, fed by an OptionContract chain. Cache-free; downstream
dashboards apply Streamlit-level caching.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pandas as pd

from src.common.schemas import OptionContract, OptionRight
from src.utils.config import PROJECT_ROOT
from src.utils.logging import get_logger

log = get_logger(__name__)

_OI_HISTORY_DIR = PROJECT_ROOT / "data" / "options_oi_history"


# ---------------------------------------------------------------------------
# Max pain — strike that minimises total option-holder payout at expiry
# ---------------------------------------------------------------------------
def max_pain(contracts: list[OptionContract], expiry=None) -> float | None:
    """Max-pain strike (writer's haven) for one expiry.

    If `expiry` is None and the chain spans several, picks the nearest expiry.
    Returns None when there's no usable OI data.
    """
    if not contracts:
        return None
    pool = [c for c in contracts if c.open_interest and c.open_interest > 0]
    if not pool:
        return None
    if expiry is not None:
        pool = [c for c in pool if c.expiry == expiry]
    else:
        # nearest expiry (by date)
        nearest = min({c.expiry for c in pool})
        pool = [c for c in pool if c.expiry == nearest]
    if not pool:
        return None
    strikes = sorted({c.strike for c in pool})
    if not strikes:
        return None
    best_strike = strikes[0]
    best_pain = float("inf")
    for s in strikes:
        # Option-holder payout at spot=s
        pain = 0.0
        for c in pool:
            oi = int(c.open_interest or 0)
            if c.right == OptionRight.CALL and s > c.strike:
                pain += (s - c.strike) * oi
            elif c.right == OptionRight.PUT and s < c.strike:
                pain += (c.strike - s) * oi
        if pain < best_pain:
            best_pain = pain
            best_strike = s
    return float(best_strike)


# ---------------------------------------------------------------------------
# Put / call ratio
# ---------------------------------------------------------------------------
def put_call_ratio(contracts: list[OptionContract], *, by: str = "oi") -> dict[str, float]:
    """Aggregate put/call ratio across the whole chain.

    `by`: "oi" (open interest) or "volume". Returns a dict with overall +
    nearest-expiry slices.
    """
    if not contracts:
        return {"overall_pc_ratio": 0.0, "nearest_pc_ratio": 0.0,
                "total_call": 0, "total_put": 0}

    def _val(c: OptionContract) -> int:
        v = c.open_interest if by == "oi" else c.volume
        return int(v or 0)

    total_call = sum(_val(c) for c in contracts if c.right == OptionRight.CALL)
    total_put = sum(_val(c) for c in contracts if c.right == OptionRight.PUT)

    nearest = min({c.expiry for c in contracts})
    near_call = sum(_val(c) for c in contracts if c.expiry == nearest and c.right == OptionRight.CALL)
    near_put = sum(_val(c) for c in contracts if c.expiry == nearest and c.right == OptionRight.PUT)

    return {
        "overall_pc_ratio": (total_put / total_call) if total_call else 0.0,
        "nearest_pc_ratio": (near_put / near_call) if near_call else 0.0,
        "total_call": total_call,
        "total_put": total_put,
        "near_expiry": nearest.isoformat(),
    }


# ---------------------------------------------------------------------------
# 25-delta skew — IV(put Δ -0.25) - IV(call Δ 0.25)
# ---------------------------------------------------------------------------
def skew_25_delta(contracts: list[OptionContract], expiry=None) -> dict[str, float | None]:
    """25Δ put IV minus 25Δ call IV per expiry. Positive = bearish skew."""
    if not contracts:
        return {"put_iv": None, "call_iv": None, "skew": None}
    pool = [c for c in contracts if c.iv is not None and c.delta is not None]
    if expiry is not None:
        pool = [c for c in pool if c.expiry == expiry]
    else:
        nearest = min({c.expiry for c in pool}) if pool else None
        pool = [c for c in pool if c.expiry == nearest] if nearest else []
    if not pool:
        return {"put_iv": None, "call_iv": None, "skew": None}

    calls = [c for c in pool if c.right == OptionRight.CALL]
    puts = [c for c in pool if c.right == OptionRight.PUT]
    if not calls or not puts:
        return {"put_iv": None, "call_iv": None, "skew": None}

    call_25 = min(calls, key=lambda c: abs(abs(c.delta) - 0.25))
    put_25 = min(puts, key=lambda c: abs(abs(c.delta) - 0.25))
    return {
        "put_iv": float(put_25.iv),
        "call_iv": float(call_25.iv),
        "put_strike": float(put_25.strike),
        "call_strike": float(call_25.strike),
        "skew": float(put_25.iv - call_25.iv),
    }


# ---------------------------------------------------------------------------
# OI delta tracker — needs a daily snapshot of (ticker, strike, right) -> OI
# ---------------------------------------------------------------------------
def _snapshot_path(ticker: str, asof) -> Path:
    _OI_HISTORY_DIR.mkdir(parents=True, exist_ok=True)
    return _OI_HISTORY_DIR / f"{ticker.upper()}__{asof.isoformat()}.parquet"


def snapshot_oi(contracts: list[OptionContract]) -> Path | None:
    """Write today's OI snapshot for a ticker (idempotent per day)."""
    if not contracts:
        return None
    ticker = contracts[0].underlying
    today = datetime.utcnow().date()
    rows = [{
        "ticker": c.underlying,
        "expiry": c.expiry.isoformat(),
        "strike": float(c.strike),
        "right": c.right.value,
        "open_interest": int(c.open_interest or 0),
        "volume": int(c.volume or 0),
    } for c in contracts]
    df = pd.DataFrame(rows)
    path = _snapshot_path(ticker, today)
    df.to_parquet(path, index=False)
    return path


def oi_delta_5d(ticker: str) -> pd.DataFrame:
    """Top-changing strikes over the last ~5 trading days vs today.

    Returns DataFrame[expiry, strike, right, oi_now, oi_5d_ago, delta_oi,
    delta_pct]. Empty if not enough history.
    """
    if not _OI_HISTORY_DIR.exists():
        return pd.DataFrame()
    snaps = sorted(_OI_HISTORY_DIR.glob(f"{ticker.upper()}__*.parquet"))
    if len(snaps) < 2:
        return pd.DataFrame()
    today_df = pd.read_parquet(snaps[-1])
    # Pick the snapshot closest to 5 trading days ago = ~7 calendar days
    past_df = pd.read_parquet(snaps[0]) if len(snaps) < 5 else pd.read_parquet(snaps[-5])

    merged = today_df.merge(
        past_df, on=["ticker", "expiry", "strike", "right"],
        suffixes=("_now", "_5d_ago"), how="left",
    )
    merged["delta_oi"] = merged["open_interest_now"] - merged["open_interest_5d_ago"].fillna(0)
    merged["delta_pct"] = merged.apply(
        lambda r: (r["delta_oi"] / r["open_interest_5d_ago"] * 100)
        if r["open_interest_5d_ago"] and r["open_interest_5d_ago"] > 0 else 0.0,
        axis=1,
    )
    return merged.sort_values("delta_oi", key=lambda s: s.abs(), ascending=False).head(20)
