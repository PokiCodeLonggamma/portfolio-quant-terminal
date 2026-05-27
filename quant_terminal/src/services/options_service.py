"""Options service — orchestrates chain fetch + GEX + IV analytics + vol surface.

Wraps the pure modules in ``src/trading/`` behind a clean service interface
that returns Pydantic v2 DTOs. Used by:
  - FastAPI (Phase 2 — ``/api/options/{ticker}/{chain|gex|vol_surface}``)
  - Streamlit dashboards (``src/trading/dashboards.py``)
  - Tests, alerts engine, daily brief, scanners, etc.

Dependency-injected ``chain_fetch_fn`` lets tests pass deterministic fixtures
without hitting yfinance or Alpaca.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Callable

from src.common.schemas import OptionContract
from src.services.schemas import (
    GexBucket,
    GexSummary,
    IVTermStructurePoint,
)
from src.trading.gex import (
    compute_gex,
    gamma_flip_strike,
    negative_gamma_zone,
)
from src.trading.gex_enrich import put_call_ratio
from src.trading.iv_analytics import iv_term_structure


def _wall_strikes(gex_df) -> tuple[float | None, float | None]:
    """Call wall = strike with largest positive net GEX.
    Put wall  = strike with largest absolute negative net GEX."""
    if gex_df is None or gex_df.empty or "net_gex_usd" not in gex_df.columns:
        return None, None
    try:
        pos = gex_df[gex_df["net_gex_usd"] > 0]
        cw = float(pos.loc[pos["net_gex_usd"].idxmax(), "strike"]) if not pos.empty else None
        neg = gex_df[gex_df["net_gex_usd"] < 0]
        pw = float(neg.loc[neg["net_gex_usd"].idxmin(), "strike"]) if not neg.empty else None
        return cw, pw
    except Exception:
        return None, None


# ---------------------------------------------------------------------------
# Default chain fetcher — defers to src.trading.options_chain.fetch_chain
# ---------------------------------------------------------------------------
def _default_chain_fetcher(ticker: str) -> list[OptionContract]:
    """Production fetcher — uses Alpaca primary, yfinance fallback."""
    try:
        from src.trading.options_chain import fetch_chain
        return fetch_chain(ticker)
    except Exception:
        return []


def _default_spot_fetcher(ticker: str) -> float | None:
    """Production spot fetcher — uses yfinance fast_info."""
    try:
        from src.trading.options_chain import _safe_spot
        return _safe_spot(ticker)
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------
@dataclass
class OptionsService:
    """Pure orchestration over the options engine.

    Methods return Pydantic DTOs, never DataFrames.
    """
    chain_fetch_fn: Callable[[str], list[OptionContract]] = _default_chain_fetcher
    spot_fetch_fn: Callable[[str], float | None] = _default_spot_fetcher

    # -------------------------------------------------------------------------
    # Raw chain (POD list)
    # -------------------------------------------------------------------------
    def get_chain(self, ticker: str) -> list[OptionContract]:
        """Fetch the full options chain — already typed by src.common.schemas."""
        return self.chain_fetch_fn(ticker)

    # -------------------------------------------------------------------------
    # GEX
    # -------------------------------------------------------------------------
    def get_gex_summary(self, ticker: str, *, max_buckets: int = 40) -> GexSummary | None:
        """Build a GEX summary DTO.

        Returns ``None`` if chain or spot fetch fails. Caller (FastAPI) maps
        that to a 404 / 503.
        """
        spot = self.spot_fetch_fn(ticker)
        if spot is None or spot <= 0:
            return None
        chain = self.chain_fetch_fn(ticker)
        if not chain:
            return None
        df = compute_gex(chain, spot)
        if df is None or df.empty:
            return None
        flip = gamma_flip_strike(df)
        lo, hi = negative_gamma_zone(df, spot=spot, pct=0.05)
        pc = put_call_ratio(chain)
        cw, pw = _wall_strikes(df)
        # Buckets — top N rows by absolute net GEX
        buckets: list[GexBucket] = []
        sliced = df.reindex(
            df["net_gex_usd"].abs().sort_values(ascending=False).index
        ).head(max_buckets)
        for _, row in sliced.iterrows():
            buckets.append(GexBucket(
                strike=float(row.get("strike", 0.0)),
                call_gex=float(row.get("call_gex_usd", 0.0)),
                put_gex=float(row.get("put_gex_usd", 0.0)),
                net_gex=float(row.get("net_gex_usd", 0.0)),
            ))
        buckets.sort(key=lambda b: b.strike)
        return GexSummary(
            ticker=ticker,
            spot=float(spot),
            gamma_flip=float(flip) if flip is not None else None,
            neg_gamma_lo=float(lo) if lo is not None else None,
            neg_gamma_hi=float(hi) if hi is not None else None,
            call_wall=float(cw) if cw is not None else None,
            put_wall=float(pw) if pw is not None else None,
            overall_pc_ratio=float(pc.get("overall_pc_ratio", 0.0)),
            n_strikes=int(len(df)),
            asof=datetime.utcnow(),
            buckets=buckets,
        )

    # -------------------------------------------------------------------------
    # IV term structure
    # -------------------------------------------------------------------------
    def get_iv_term_structure(self, ticker: str) -> list[IVTermStructurePoint]:
        """Return one point per expiry — ATM IV averaged across calls/puts."""
        spot = self.spot_fetch_fn(ticker)
        if spot is None or spot <= 0:
            return []
        chain = self.chain_fetch_fn(ticker)
        if not chain:
            return []
        df = iv_term_structure(chain, spot)
        if df is None or df.empty:
            return []
        points: list[IVTermStructurePoint] = []
        for _, row in df.iterrows():
            atm = row.get("atm_iv_avg")
            try:
                atm_val = float(atm) if atm is not None and atm == atm else None  # noqa: PLR0124 (NaN check)
            except (TypeError, ValueError):
                atm_val = None
            expiry_val = row.get("expiry")
            if expiry_val is None:
                continue
            # expiry might be a numpy datetime or a python date
            if hasattr(expiry_val, "date"):
                expiry_val = expiry_val.date()
            dte = int(row.get("dte_days", 0))
            contango = row.get("contango_proxy")
            try:
                cval = float(contango) if contango is not None and contango == contango else None  # noqa: PLR0124
            except (TypeError, ValueError):
                cval = None
            points.append(IVTermStructurePoint(
                expiry=expiry_val,
                dte_days=dte,
                atm_iv_avg=atm_val,
                contango_proxy=cval,
            ))
        return points

    # -------------------------------------------------------------------------
    # Health / availability
    # -------------------------------------------------------------------------
    def chain_available(self, ticker: str) -> bool:
        """Quick check — does the upstream return a non-empty chain?"""
        try:
            chain = self.chain_fetch_fn(ticker)
        except Exception:
            return False
        return bool(chain)
