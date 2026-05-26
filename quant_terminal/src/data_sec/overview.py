"""Cross-ticker Smart-Money overview — rolls up everything in one view.

Instead of asking the user to pick a ticker, this module:
  * Iterates the portfolio + watchlist universe in parallel (best effort).
  * Aggregates insider, dilution, runway, and contract data into ranked
    cross-ticker tables ready for rendering.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Iterable

import pandas as pd

from src.data_sec.cash_runway import assess_runway
from src.data_sec.dilution import assess_dilution
from src.data_sec.form4 import insider_summary
from src.utils.logging import get_logger

log = get_logger(__name__)


def _safe_call(fn, *args, **kw):
    try:
        return fn(*args, **kw)
    except Exception as exc:
        log.debug("overview call %s failed: %s", getattr(fn, "__name__", fn), exc)
        return None


# ---------------------------------------------------------------------------
# Insider activity — global top buyers + sellers across the universe
# ---------------------------------------------------------------------------
def insider_activity_overview(
    universe: Iterable[str], *, lookback_days: int = 90, max_workers: int = 6,
) -> pd.DataFrame:
    """Concatenate Form-4 summaries across the universe. Sorted by gross USD."""
    universe = sorted(set(t for t in universe if t))
    frames: list[pd.DataFrame] = []
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futures = {ex.submit(_safe_call, insider_summary, t,
                              lookback_days=lookback_days): t for t in universe}
        for fut in as_completed(futures):
            df = fut.result()
            if df is None or df.empty:
                continue
            df = df.copy()
            df["ticker"] = futures[fut]
            frames.append(df)
    if not frames:
        return pd.DataFrame(columns=[
            "ticker", "reporter_name", "reporter_role", "transaction_date",
            "code", "shares", "price", "value_usd",
        ])
    full = pd.concat(frames, ignore_index=True)
    # Best-effort column normalisation
    if "value_usd" in full.columns:
        full = full.sort_values("value_usd", key=lambda s: s.abs(), ascending=False)
    return full.reset_index(drop=True)


# ---------------------------------------------------------------------------
# Dilution radar — cross-ticker
# ---------------------------------------------------------------------------
def dilution_overview(universe: Iterable[str], *, max_workers: int = 6) -> pd.DataFrame:
    universe = sorted(set(t for t in universe if t))
    rows = []
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futures = {ex.submit(_safe_call, assess_dilution, t): t for t in universe}
        for fut in as_completed(futures):
            assessment = fut.result()
            if assessment is None:
                continue
            try:
                rows.append(assessment.model_dump())
            except Exception:
                rows.append(getattr(assessment, "dict", lambda: {})())
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    return df.sort_values(["dilution_score"], ascending=False).reset_index(drop=True)


# ---------------------------------------------------------------------------
# Cash runway — cross-ticker
# ---------------------------------------------------------------------------
def runway_overview(universe: Iterable[str], *, max_workers: int = 6) -> pd.DataFrame:
    universe = sorted(set(t for t in universe if t))
    rows = []
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futures = {ex.submit(_safe_call, assess_runway, t): t for t in universe}
        for fut in as_completed(futures):
            assessment = fut.result()
            if assessment is None:
                continue
            try:
                rows.append(assessment.model_dump())
            except Exception:
                rows.append(getattr(assessment, "dict", lambda: {})())
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    # Lowest runway first — these are the most at risk
    if "runway_quarters" in df.columns:
        df["runway_quarters"] = pd.to_numeric(df["runway_quarters"], errors="coerce")
        df = df.sort_values("runway_quarters", ascending=True)
    return df.reset_index(drop=True)


# ---------------------------------------------------------------------------
# Headline KPIs computed from the three sub-rollups
# ---------------------------------------------------------------------------
def kpi_strip(insider_df: pd.DataFrame, dilution_df: pd.DataFrame,
              runway_df: pd.DataFrame) -> dict[str, float | int | str]:
    out = {}
    if insider_df is not None and not insider_df.empty and "value_usd" in insider_df.columns:
        buys = insider_df[insider_df["value_usd"] > 0]
        sells = insider_df[insider_df["value_usd"] < 0]
        out["insider_buy_usd"] = float(buys["value_usd"].sum())
        out["insider_sell_usd"] = float(sells["value_usd"].sum())
        if not buys.empty:
            out["top_insider_buy_ticker"] = str(buys.iloc[0].get("ticker", ""))
        else:
            out["top_insider_buy_ticker"] = "—"
    else:
        out.update(insider_buy_usd=0.0, insider_sell_usd=0.0, top_insider_buy_ticker="—")

    if dilution_df is not None and not dilution_df.empty and "dilution_score" in dilution_df.columns:
        risky = dilution_df[dilution_df["dilution_score"] >= 4]
        out["n_high_dilution"] = int(len(risky))
        out["high_dilution_tickers"] = ", ".join(risky["ticker"].astype(str).head(5).tolist())
    else:
        out.update(n_high_dilution=0, high_dilution_tickers="—")

    if runway_df is not None and not runway_df.empty and "runway_quarters" in runway_df.columns:
        short = runway_df[runway_df["runway_quarters"] < 2.0]
        out["n_runway_short"] = int(len(short))
        out["runway_short_tickers"] = ", ".join(short["ticker"].astype(str).head(5).tolist())
    else:
        out.update(n_runway_short=0, runway_short_tickers="—")

    return out
