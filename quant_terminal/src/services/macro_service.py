"""Macro service — VIX + term structure + DXY + US10Y + SPY-200d.

A lightweight wrapper around yfinance for the /markets/macro page. The
heavier macro regime classification (inflation/growth/policy) already
lives in ``src/macro/regime.py`` but is not surfaced here in P5a (it
will land in P5b or later if needed).

Dependency-injected fetcher makes the service offline-testable.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Callable, Literal

from src.services.schemas import MacroRegimeSnapshot

TermStructure = Literal["contango", "backwardation", "flat"]


def _yfinance_macro_fetcher() -> dict:
    """Production fetcher — pulls VIX, ^VIX9D, DXY, ^TNX, SPY closes."""
    out = {
        "vix_level": None,
        "vix_short": None,
        "vix_long": None,
        "dxy": None,
        "us10y_yield": None,
        "spy_close": None,
        "spy_ma200": None,
    }
    try:
        import yfinance as yf
        # Use download (multi-ticker, lighter) over per-ticker .history
        tickers = "^VIX ^VIX9D ^VIX3M DX-Y.NYB ^TNX SPY"
        df = yf.download(
            tickers, period="260d", progress=False,
            auto_adjust=True, threads=False,
        )
        if df is None or df.empty:
            return out
        # df is MultiIndex (field, ticker) after yfinance v0.2+
        closes = df["Close"] if "Close" in df.columns else df
        if hasattr(closes, "iloc") and len(closes) > 0:
            try:
                out["vix_level"] = float(closes["^VIX"].dropna().iloc[-1])
            except (KeyError, IndexError):
                pass
            try:
                out["vix_short"] = float(closes["^VIX9D"].dropna().iloc[-1])
            except (KeyError, IndexError):
                pass
            try:
                out["vix_long"] = float(closes["^VIX3M"].dropna().iloc[-1])
            except (KeyError, IndexError):
                pass
            try:
                out["dxy"] = float(closes["DX-Y.NYB"].dropna().iloc[-1])
            except (KeyError, IndexError):
                pass
            try:
                out["us10y_yield"] = float(closes["^TNX"].dropna().iloc[-1])
            except (KeyError, IndexError):
                pass
            try:
                spy_series = closes["SPY"].dropna()
                if len(spy_series) > 0:
                    out["spy_close"] = float(spy_series.iloc[-1])
                if len(spy_series) >= 200:
                    out["spy_ma200"] = float(spy_series.tail(200).mean())
            except (KeyError, IndexError):
                pass
        return out
    except Exception:
        return out


def _classify_term(short: float | None, long: float | None) -> TermStructure | None:
    """short=^VIX9D, long=^VIX3M. Backwardation when short>long (stress)."""
    if short is None or long is None:
        return None
    if abs(short - long) < 0.3:
        return "flat"
    return "backwardation" if short > long else "contango"


@dataclass
class MacroService:
    """Pure orchestration over yfinance macro symbols."""
    fetch_fn: Callable[[], dict] = _yfinance_macro_fetcher

    def get_snapshot(self) -> MacroRegimeSnapshot:
        raw = self.fetch_fn()
        spy_above_200d: bool | None = None
        if raw.get("spy_close") is not None and raw.get("spy_ma200") is not None:
            spy_above_200d = raw["spy_close"] > raw["spy_ma200"]
        return MacroRegimeSnapshot(
            vix_level=raw.get("vix_level"),
            vix_term_structure=_classify_term(
                raw.get("vix_short"), raw.get("vix_long"),
            ),
            dxy=raw.get("dxy"),
            us10y_yield=raw.get("us10y_yield"),
            spy_above_200d=spy_above_200d,
            asof=datetime.utcnow(),
        )
