"""SEC company-facts (XBRL) reader.

EDGAR exposes per-company XBRL facts at:
  /api/xbrl/companyfacts/CIK<10digits>.json

Each fact lists every period the issuer reported a given GAAP/IFRS concept
in. We provide:

  * `company_facts(cik)`       — raw JSON dict.
  * `get_concept(cik, concept)` — DataFrame for a single concept.
  * `quarterly_cash_and_burn(ticker)` — derived quarterly cash + burn rate
    using a fallback ladder of concept names per metric so we work across
    GAAP vs IFRS filers.

Concept names drift between filers; the ladders below were assembled from
the most common GAAP US filer patterns. We pick the first concept that
resolves and document it in the returned `payload` column.
"""
from __future__ import annotations

from datetime import date, datetime
from functools import lru_cache
from typing import Any

import pandas as pd

from src.data_sec.edgar_client import edgar_json, pad_cik
from src.data_sec.forms_index import cik_for_ticker
from src.utils.cache import read as cache_read, write as cache_write
from src.utils.logging import get_logger

log = get_logger(__name__)


_FACTS_PATH = "/api/xbrl/companyfacts/CIK{cik}.json"


# ---------------------------------------------------------------------------
# Raw fetch
# ---------------------------------------------------------------------------
def company_facts(cik: str) -> dict[str, Any]:
    """Return the raw company-facts JSON for a CIK. Empty dict on miss."""
    cik10 = pad_cik(cik)
    cache_key = f"facts|{cik10}"
    cached = cache_read(cache_key, namespace="sec_xbrl", max_age_seconds=60 * 60 * 24)
    if cached is not None and not cached.empty:
        # cache stores a single-cell payload — round-trip via JSON
        import json
        try:
            return json.loads(cached.iloc[0, 0])
        except Exception:
            pass
    data = edgar_json(_FACTS_PATH.format(cik=cik10))
    if data:
        import json
        df = pd.DataFrame([{"payload": json.dumps(data)}])
        cache_write(cache_key, df, namespace="sec_xbrl")
    return data


def get_concept(cik: str, concept: str, *, taxonomy: str = "us-gaap") -> pd.DataFrame:
    """Return one DataFrame for ``concept`` (e.g. "CashAndCashEquivalentsAtCarryingValue")."""
    facts = company_facts(cik)
    if not facts:
        return pd.DataFrame()
    units_block = ((facts.get("facts") or {}).get(taxonomy) or {}).get(concept) or {}
    units = units_block.get("units") or {}
    rows: list[dict[str, Any]] = []
    for unit_label, items in units.items():
        for it in items or []:
            try:
                rows.append({
                    "concept": concept,
                    "taxonomy": taxonomy,
                    "unit": unit_label,
                    "val": float(it.get("val", 0.0)),
                    "fy": it.get("fy"),
                    "fp": it.get("fp"),
                    "form": it.get("form"),
                    "filed": it.get("filed"),
                    "start": it.get("start"),
                    "end": it.get("end"),
                    "accn": it.get("accn"),
                })
            except Exception as exc:                                   # noqa: BLE001
                log.debug("Skip XBRL row %s: %s", concept, exc)
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    for col in ("filed", "start", "end"):
        df[col] = pd.to_datetime(df[col], errors="coerce")
    return df


# ---------------------------------------------------------------------------
# Concept ladders
# ---------------------------------------------------------------------------
_CASH_CONCEPTS = [
    "CashAndCashEquivalentsAtCarryingValue",
    "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents",
    "Cash",
]
_OPCF_CONCEPTS = [
    "NetCashProvidedByUsedInOperatingActivities",
    "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations",
]
_CAPEX_CONCEPTS = [
    "PaymentsToAcquirePropertyPlantAndEquipment",
    "PaymentsForCapitalImprovements",
]
_LTD_CONCEPTS = [
    "LongTermDebt",
    "LongTermDebtNoncurrent",
]
_CONVERTIBLES_CONCEPTS = [
    "ConvertibleDebt",
    "ConvertibleNotesPayable",
    "ConvertibleDebtNoncurrent",
]
_SHARES_CONCEPTS = [
    "CommonStockSharesOutstanding",
    "EntityCommonStockSharesOutstanding",
]


def _first_resolvable(cik: str, ladder: list[str]) -> tuple[str, pd.DataFrame]:
    for c in ladder:
        df = get_concept(cik, c)
        if not df.empty:
            return c, df
    return "", pd.DataFrame()


# ---------------------------------------------------------------------------
# Derived: quarterly cash + burn
# ---------------------------------------------------------------------------
_CB_COLS = ["period_end", "cash_eq", "op_cf", "fcf", "burn_qoq"]


def quarterly_cash_and_burn(ticker: str) -> pd.DataFrame:
    """Quarterly cash + burn snapshot for ``ticker``.

    Columns: period_end (Timestamp), cash_eq, op_cf, fcf, burn_qoq.
    """
    if not ticker:
        return pd.DataFrame(columns=_CB_COLS)

    cik = cik_for_ticker(ticker)
    if cik is None:
        log.info("quarterly_cash_and_burn: unknown ticker %s", ticker)
        return pd.DataFrame(columns=_CB_COLS)

    _, cash_df = _first_resolvable(cik, _CASH_CONCEPTS)
    _, opcf_df = _first_resolvable(cik, _OPCF_CONCEPTS)
    _, capex_df = _first_resolvable(cik, _CAPEX_CONCEPTS)

    if cash_df.empty and opcf_df.empty:
        return pd.DataFrame(columns=_CB_COLS)

    # Cash is a *point-in-time* concept — take the latest filing for each end-date.
    def _point_in_time(df: pd.DataFrame) -> pd.Series:
        if df.empty:
            return pd.Series(dtype=float)
        d = df.sort_values("filed").drop_duplicates(subset=["end"], keep="last")
        s = pd.Series(d["val"].values, index=d["end"])
        return s.sort_index()

    # OpCF / Capex are *period* concepts — keep only Q-ish (~75-105 day) rows.
    def _period(df: pd.DataFrame) -> pd.Series:
        if df.empty:
            return pd.Series(dtype=float)
        d = df.copy()
        d["start"] = pd.to_datetime(d["start"], errors="coerce")
        d["end"] = pd.to_datetime(d["end"], errors="coerce")
        d = d.dropna(subset=["start", "end"])
        d["days"] = (d["end"] - d["start"]).dt.days
        d = d[(d["days"] >= 75) & (d["days"] <= 105)]
        d = d.sort_values("filed").drop_duplicates(subset=["end"], keep="last")
        return pd.Series(d["val"].values, index=d["end"]).sort_index()

    cash = _point_in_time(cash_df)
    opcf = _period(opcf_df)
    capex = _period(capex_df)
    if cash.empty and opcf.empty:
        return pd.DataFrame(columns=_CB_COLS)

    idx = sorted(set(cash.index) | set(opcf.index))
    out = pd.DataFrame({
        "period_end": idx,
        "cash_eq": [float(cash.get(d, float("nan"))) for d in idx],
        "op_cf": [float(opcf.get(d, float("nan"))) for d in idx],
    })
    out["fcf"] = [
        float(opcf.get(d, 0.0)) - float(capex.get(d, 0.0)) if d in opcf.index else float("nan")
        for d in idx
    ]
    out["burn_qoq"] = -out["fcf"]                                       # +ve burn = cash consumed
    return out[_CB_COLS]


# ---------------------------------------------------------------------------
# Convenience getters used by dilution.py / cash_runway.py
# ---------------------------------------------------------------------------
def latest_shares_outstanding(cik: str) -> float:
    _, df = _first_resolvable(cik, _SHARES_CONCEPTS)
    if df.empty:
        return 0.0
    df = df.sort_values("filed")
    return float(df["val"].iloc[-1])


def convertibles_outstanding_usd(cik: str) -> float:
    _, df = _first_resolvable(cik, _CONVERTIBLES_CONCEPTS)
    if df.empty:
        return 0.0
    df = df.sort_values("filed")
    return float(df["val"].iloc[-1])
