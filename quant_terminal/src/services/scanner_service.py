"""Scanner service — wraps universe + short-squeeze scanners.

Two distinct scanners surface here:
  - **Universe scanner** (Δ-25 long calls/puts across the options universe)
  - **Squeeze scanner** (SHO threshold list + Finviz short interest merge)

Both are read-only and dependency-injected for testability.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

import pandas as pd

from src.common.schemas import OptionContract
from src.services.schemas import SqueezeRow, UniverseScanRow
from src.trading.universe_scanner import DEFAULT_UNIVERSE, scan_universe


def _default_chain_fetcher(ticker: str) -> list[OptionContract]:
    try:
        from src.trading.options_chain import fetch_chain
        return fetch_chain(ticker)
    except Exception:
        return []


def _default_spot_fetcher(ticker: str) -> float | None:
    try:
        from src.trading.options_chain import _safe_spot
        return _safe_spot(ticker)
    except Exception:
        return None


def _default_squeeze_fetcher() -> pd.DataFrame:
    """Return the latest persisted SHO + Finviz merged snapshot, or refresh."""
    try:
        from src.scanners.short_squeeze import (
            fetch_finviz_short_interest,
            fetch_sec_form_sho,
            latest_scan,
            merge_signals,
            persist_scan,
        )
        df = latest_scan()
        if df is None or df.empty:
            finviz = fetch_finviz_short_interest()
            sho = fetch_sec_form_sho()
            df = merge_signals(finviz, sho)
            persist_scan(df)
        return df if df is not None else pd.DataFrame()
    except Exception:
        return pd.DataFrame()


@dataclass
class ScannerService:
    """Read-only scanner orchestration."""
    chain_fetch_fn: Callable[[str], list[OptionContract]] = _default_chain_fetcher
    spot_fetch_fn: Callable[[str], float | None] = _default_spot_fetcher
    squeeze_fetch_fn: Callable[[], pd.DataFrame] = _default_squeeze_fetcher
    default_universe: list[str] = field(
        default_factory=lambda: list(DEFAULT_UNIVERSE)
    )

    # ------------------------------------------------------------------
    # Universe scan (Δ-25 long-call / long-put screen)
    # ------------------------------------------------------------------
    def scan_options_universe(
        self,
        *,
        universe: list[str] | None = None,
    ) -> list[UniverseScanRow]:
        ticks = universe if universe else self.default_universe
        # Build a per-ticker spot lookup (DataFrame contract for scan_universe)
        spot_lookup: dict[str, float] = {}
        for t in ticks:
            s = self.spot_fetch_fn(t)
            if s is not None:
                spot_lookup[t] = float(s)
        df = scan_universe(ticks, self.chain_fetch_fn, spot_lookup)
        if df is None or df.empty:
            return []
        rows: list[UniverseScanRow] = []
        for rec in df.to_dict(orient="records"):
            rows.append(UniverseScanRow(
                ticker=str(rec.get("ticker")),
                spot=float(rec.get("spot") or 0.0),
                chain_size=int(rec.get("chain_size") or 0),
                atm_iv_pct=rec.get("atm_iv_pct"),
                delta25_call_strike=rec.get("delta25_call_strike"),
                delta25_call_premium_usd=rec.get("delta25_call_premium_usd"),
                delta25_put_strike=rec.get("delta25_put_strike"),
                delta25_put_premium_usd=rec.get("delta25_put_premium_usd"),
                gamma_flip=rec.get("gamma_flip"),
                neg_gamma_lo=rec.get("neg_gamma_lo"),
                neg_gamma_hi=rec.get("neg_gamma_hi"),
                put_call_ratio=float(rec.get("put_call_ratio") or 0.0),
                score=float(rec.get("score") or 0.0),
                notes=str(rec.get("notes") or ""),
                asof=str(rec.get("asof") or ""),
            ))
        return rows

    # ------------------------------------------------------------------
    # Short-squeeze top-N
    # ------------------------------------------------------------------
    def get_squeeze_top(self, *, limit: int = 20) -> list[SqueezeRow]:
        df = self.squeeze_fetch_fn()
        if df is None or df.empty:
            return []
        # Map various legacy columns gracefully
        rows: list[SqueezeRow] = []
        for rec in df.head(limit).to_dict(orient="records"):
            rows.append(SqueezeRow(
                ticker=str(rec.get("Ticker") or rec.get("ticker") or ""),
                short_pct_float=_to_float(rec.get("ShortFloat") or rec.get("short_pct_float")),
                days_to_cover=_to_float(rec.get("ShortRatio") or rec.get("days_to_cover")),
                cost_to_borrow_pct=_to_float(rec.get("CTB") or rec.get("cost_to_borrow_pct")),
                utilization_pct=_to_float(rec.get("Util") or rec.get("utilization_pct")),
                on_sho_threshold=bool(rec.get("on_sho") or rec.get("on_sho_threshold")),
                composite_score=_to_float(rec.get("composite_score") or rec.get("score")),
            ))
        return rows


def _to_float(v) -> float | None:
    if v is None or v == "":
        return None
    try:
        f = float(v)
        if f != f:  # NaN
            return None
        return f
    except (TypeError, ValueError):
        return None
