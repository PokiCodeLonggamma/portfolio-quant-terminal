"""Short Squeeze Scanner — template branchement SEC EDGAR + Finviz.

This module exposes a minimal interface that the user's existing scraper bot
can plug into. We provide:
  - `fetch_finviz_short_interest`: scrape Finviz screener (HTTP GET).
  - `fetch_sec_form_sho`: fetch SHO threshold securities list from EDGAR
    (uses the SEC_EMAIL header per SEC rules).
  - `merge_signals`: combine short interest, days-to-cover, and float into a
    composite "squeeze score" used by the dashboard.

The Streamlit tab in app.py reads these helpers; if the user has a more
sophisticated bot, they replace the body of these functions and the UI just
keeps working.
"""
from __future__ import annotations

from datetime import datetime

import pandas as pd
import requests

from src.utils.config import get_config
from src.utils.logging import get_logger

log = get_logger(__name__)

SEC_THRESHOLD_URL = "https://www.sec.gov/divisions/marketreg/regsho-threshold-data.htm"
FINVIZ_SCREENER_URL = (
    "https://finviz.com/screener.ashx?v=152&f=sh_short_o20,sh_short_a5"
    "&c=0,1,6,7,8,9,29,30,31,65,67,68"
)


def _sec_headers() -> dict[str, str]:
    cfg = get_config()
    email = cfg.secrets.sec_email or "anonymous@example.com"
    return {"User-Agent": f"quant-terminal {email}"}


def fetch_sec_form_sho() -> pd.DataFrame:
    """Pull SEC RegSHO threshold securities list. Returns empty df on failure."""
    try:
        resp = requests.get(SEC_THRESHOLD_URL, headers=_sec_headers(), timeout=15)
        resp.raise_for_status()
        tables = pd.read_html(resp.text)
        if not tables:
            return pd.DataFrame()
        df = tables[0]
        df.columns = [str(c).strip().lower().replace(" ", "_") for c in df.columns]
        df["fetched_at"] = datetime.utcnow()
        return df
    except Exception as exc:
        log.warning("SEC SHO fetch failed: %s", exc)
        return pd.DataFrame()


def fetch_finviz_short_interest() -> pd.DataFrame:
    """Fetch Finviz screener page, parse the tabular payload."""
    headers = {"User-Agent": "Mozilla/5.0 (quant-terminal scanner)"}
    try:
        resp = requests.get(FINVIZ_SCREENER_URL, headers=headers, timeout=15)
        resp.raise_for_status()
        tables = pd.read_html(resp.text)
        # Finviz returns several layout tables; pick the one with most rows
        screener = max(tables, key=lambda d: d.shape[0])
        screener.columns = [str(c).strip().lower().replace(" ", "_") for c in screener.columns]
        screener["fetched_at"] = datetime.utcnow()
        return screener
    except Exception as exc:
        log.warning("Finviz fetch failed: %s", exc)
        return pd.DataFrame()


def merge_signals(finviz: pd.DataFrame, sho: pd.DataFrame | None = None) -> pd.DataFrame:
    """Combine short-interest + days-to-cover into a composite score.

    Score = (short_pct_float_norm * 0.5) + (days_to_cover_norm * 0.5)
    Optionally boosted +0.1 if also on SEC SHO threshold list.
    """
    if finviz.empty:
        return finviz

    candidates = [c for c in finviz.columns if "short_float" in c or "float_short" in c or c == "short_float"]
    short_col = candidates[0] if candidates else None
    dtc_candidates = [c for c in finviz.columns if "days_to_cover" in c or c == "short_ratio"]
    dtc_col = dtc_candidates[0] if dtc_candidates else None
    if short_col is None or dtc_col is None:
        log.warning("Finviz columns missing — saw %s", finviz.columns.tolist())
        return finviz

    df = finviz.copy()
    df[short_col] = pd.to_numeric(df[short_col].astype(str).str.replace("%", "", regex=False), errors="coerce")
    df[dtc_col] = pd.to_numeric(df[dtc_col], errors="coerce")

    def _norm(s: pd.Series) -> pd.Series:
        rng = s.max() - s.min()
        return (s - s.min()) / rng if rng else s * 0.0

    df["squeeze_score"] = 0.5 * _norm(df[short_col].fillna(0)) + 0.5 * _norm(df[dtc_col].fillna(0))

    if sho is not None and not sho.empty:
        ticker_cols = [c for c in sho.columns if "symbol" in c or "ticker" in c]
        if ticker_cols:
            tickers = set(sho[ticker_cols[0]].astype(str).str.upper())
            df["on_sho"] = df.get("ticker", df.columns[0]).astype(str).str.upper().isin(tickers)
            df.loc[df["on_sho"], "squeeze_score"] = df.loc[df["on_sho"], "squeeze_score"] + 0.1

    return df.sort_values("squeeze_score", ascending=False)


# ---------------------------------------------------------------------------
# Persistence + integration helpers
# ---------------------------------------------------------------------------
def _store_path():
    from src.utils.config import PROJECT_ROOT
    p = PROJECT_ROOT / "data" / "squeeze"
    p.mkdir(parents=True, exist_ok=True)
    return p


def persist_scan(df: pd.DataFrame) -> None:
    """Save the latest scan to disk so it can be reused across tabs / alerts."""
    if df is None or df.empty:
        return
    path = _store_path() / "latest.parquet"
    try:
        df.to_parquet(path, index=False)
    except Exception as exc:
        log.warning("squeeze persist failed: %s", exc)


def latest_scan() -> pd.DataFrame:
    """Load the last persisted scan (empty DF if none)."""
    path = _store_path() / "latest.parquet"
    if not path.exists():
        return pd.DataFrame()
    try:
        return pd.read_parquet(path)
    except Exception:
        return pd.DataFrame()


def top_candidates(df: pd.DataFrame | None = None, *, n: int = 10,
                    min_score: float = 0.6) -> pd.DataFrame:
    """Return the top-N tickers above `min_score`. Uses persisted scan if df is None."""
    if df is None or df.empty:
        df = latest_scan()
    if df.empty or "squeeze_score" not in df.columns:
        return pd.DataFrame()
    return df[df["squeeze_score"] >= min_score].head(n).reset_index(drop=True)


def ticker_squeeze_score(ticker: str) -> float | None:
    """Lookup the squeeze score for one ticker from the persisted scan."""
    df = latest_scan()
    if df.empty:
        return None
    tk = ticker.upper()
    sym_col = next((c for c in df.columns if c.lower() in {"ticker", "symbol"}), df.columns[0])
    row = df[df[sym_col].astype(str).str.upper() == tk]
    if row.empty or "squeeze_score" not in row.columns:
        return None
    return float(row["squeeze_score"].iloc[0])
