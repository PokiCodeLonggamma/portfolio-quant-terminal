"""Cross-asset service — live quote enrichment + heatmap.

Replaces the inline ``_quote_one`` / ``_quote_rows`` helpers from
``src/decision/cross_asset_dashboard.py`` so the same logic can be reused
by FastAPI (``/api/cross-asset/quotes``) and any future client.

Design
------
- Dependency-injected ``quote_fetch_fn`` for testability — production
  defaults to a yfinance fetcher.
- All public methods return Pydantic v2 DTOs from :mod:`src.services.schemas`.
- No Streamlit / no Plotly / no caching here — caching is the FastAPI layer's
  responsibility (Phase 3, Redis).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Callable

from src.services.schemas import HeatmapRow, Quote, QuoteBatch
from src.universe.cross_asset import get_universe, resolve_symbol


# ---------------------------------------------------------------------------
# Default fetcher — uses yfinance .history() with auto_adjust=True
# ---------------------------------------------------------------------------
def _yfinance_fetcher(symbol: str) -> dict:
    """Production fetcher — yfinance 10-day history → last + 1d% + 5d%.

    Returns a dict shape (NOT a pydantic Quote) so the function stays cheap
    and easy to stub in tests.
    """
    if not symbol:
        return {"last": None, "chg_1d_pct": None, "chg_5d_pct": None}
    try:
        import yfinance as yf
        tk = yf.Ticker(symbol)
        hist = tk.history(period="10d", auto_adjust=True)
        if hist is None or hist.empty or "Close" not in hist.columns:
            return {"last": None, "chg_1d_pct": None, "chg_5d_pct": None}
        closes = hist["Close"].dropna()
        if closes.empty:
            return {"last": None, "chg_1d_pct": None, "chg_5d_pct": None}
        last = float(closes.iloc[-1])
        chg_1d = None
        chg_5d = None
        if len(closes) >= 2:
            chg_1d = (last / float(closes.iloc[-2]) - 1.0) * 100.0
        if len(closes) >= 6:
            chg_5d = (last / float(closes.iloc[-6]) - 1.0) * 100.0
        return {"last": last, "chg_1d_pct": chg_1d, "chg_5d_pct": chg_5d}
    except Exception:
        return {"last": None, "chg_1d_pct": None, "chg_5d_pct": None}


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------
@dataclass
class CrossAssetService:
    """Pure orchestration over the cross-asset universe + a quote fetcher."""

    quote_fetch_fn: Callable[[str], dict] = _yfinance_fetcher

    # --- single quote --------------------------------------------------------
    def get_quote(self, logical: str) -> Quote:
        """Resolve ``logical`` → yfinance symbol → fetch → Quote."""
        yf_symbol = resolve_symbol(logical, flavor="yfinance")
        raw = self.quote_fetch_fn(yf_symbol)
        # Detect whether the injected fetcher is the production yfinance one;
        # tests pass a custom callable.
        source = "yfinance" if self.quote_fetch_fn is _yfinance_fetcher else "stub"
        return Quote(
            logical=logical,
            last=raw.get("last"),
            chg_1d_pct=raw.get("chg_1d_pct"),
            chg_5d_pct=raw.get("chg_5d_pct"),
            asof=datetime.utcnow(),
            source=source,
        )

    # --- batch ---------------------------------------------------------------
    def get_quotes_batch(self, logicals: list[str]) -> QuoteBatch:
        """Resolve and fetch a batch of quotes — deduplicates and preserves order."""
        seen: set[str] = set()
        unique: list[str] = []
        for lg in logicals:
            if lg not in seen:
                seen.add(lg)
                unique.append(lg)
        quotes = [self.get_quote(lg) for lg in unique]
        resolved = sum(1 for q in quotes if q.last is not None)
        return QuoteBatch(
            quotes=quotes,
            requested=len(unique),
            resolved=resolved,
            asof=datetime.utcnow(),
        )

    # --- heatmap -------------------------------------------------------------
    def get_heatmap_rows(self) -> list[HeatmapRow]:
        """Return every yfinance-mapped contract enriched with 1d/5d perf.

        Rows where ``chg_1d_pct`` is None are filtered out (no fetched data).
        Sorted descending by 1d %.
        """
        universe = get_universe()
        rows: list[HeatmapRow] = []
        for ac in universe.asset_classes:
            for spec in ac.contracts:
                if not spec.yfinance:
                    continue
                raw = self.quote_fetch_fn(spec.yfinance)
                chg_1d = raw.get("chg_1d_pct")
                chg_5d = raw.get("chg_5d_pct")
                if chg_1d is None:
                    continue
                rows.append(HeatmapRow(
                    asset_class=ac.label,
                    logical=spec.logical,
                    name=spec.name,
                    chg_1d_pct=chg_1d,
                    chg_5d_pct=chg_5d,
                ))
        rows.sort(key=lambda r: r.chg_1d_pct or 0.0, reverse=True)
        return rows
