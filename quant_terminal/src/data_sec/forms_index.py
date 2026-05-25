"""SEC submissions / full-text search index.

`cik_for_ticker` resolves a ticker to a 10-digit CIK using the public
`company_tickers.json` endpoint (cached aggressively — that file changes
very rarely).

`list_filings` walks the per-issuer `submissions/CIK*.json` and filters on
form types + a `since` cutoff, returning typed `FilingEvent` rows.

`fulltext_search` proxies the EFTS full-text endpoint
(https://efts.sec.gov/LATEST/search-index) for keyword scans across the
whole filing corpus (used by the ATM/S-3 dilution detector).
"""
from __future__ import annotations

import json
from datetime import date, datetime
from functools import lru_cache
from typing import Any

import pandas as pd

from src.common.schemas import FilingEvent
from src.data_sec.edgar_client import WWW_BASE, edgar_json, pad_cik
from src.utils.cache import read as cache_read, write as cache_write
from src.utils.logging import get_logger

log = get_logger(__name__)

_TICKERS_PATH = "https://www.sec.gov/files/company_tickers.json"
_SUBMISSIONS_TMPL = "/submissions/CIK{cik}.json"
_EFTS_SEARCH = "https://efts.sec.gov/LATEST/search-index"


# ---------------------------------------------------------------------------
# Ticker -> CIK
# ---------------------------------------------------------------------------
@lru_cache(maxsize=1)
def _ticker_table() -> dict[str, str]:
    """Lower-cased ticker -> 10-digit CIK. Cached for the life of the process."""
    cached = cache_read("ticker_table_v1", namespace="sec_form4", max_age_seconds=60 * 60 * 24 * 7)
    if cached is not None and not cached.empty:
        return dict(zip(cached["ticker"].astype(str), cached["cik"].astype(str)))

    data = edgar_json(_TICKERS_PATH)
    if not data:
        return {}
    rows: list[tuple[str, str]] = []
    # SEC payload: {"0": {"cik_str": 320193, "ticker": "AAPL", "title": "..."}, ...}
    src = data.values() if isinstance(data, dict) else []
    for entry in src:
        if not isinstance(entry, dict):
            continue
        tk = str(entry.get("ticker", "")).strip().upper()
        ck = entry.get("cik_str", "")
        if tk and ck:
            rows.append((tk, pad_cik(ck)))
    df = pd.DataFrame(rows, columns=["ticker", "cik"])
    cache_write("ticker_table_v1", df, namespace="sec_form4")
    return dict(zip(df["ticker"], df["cik"]))


def cik_for_ticker(ticker: str) -> str | None:
    """Return 10-digit CIK for ``ticker`` or None when unknown."""
    if not ticker:
        return None
    t = ticker.strip().upper()
    return _ticker_table().get(t)


# ---------------------------------------------------------------------------
# Submissions API (filings list per issuer)
# ---------------------------------------------------------------------------
def _submissions_payload(cik: str) -> dict[str, Any]:
    cik10 = pad_cik(cik)
    return edgar_json(_SUBMISSIONS_TMPL.format(cik=cik10))


def _filing_url(cik: str, accession: str, primary_doc: str) -> str:
    acc_no_dashes = accession.replace("-", "")
    cik_int = int(cik.lstrip("0") or "0")
    if primary_doc:
        return f"{WWW_BASE}/Archives/edgar/data/{cik_int}/{acc_no_dashes}/{primary_doc}"
    return f"{WWW_BASE}/cgi-bin/browse-edgar?action=getcompany&CIK={cik_int}&type=&dateb=&owner=include&count=40"


def _safe_date(value: Any) -> date | None:
    if not value:
        return None
    if isinstance(value, date):
        return value
    try:
        return datetime.strptime(str(value), "%Y-%m-%d").date()
    except Exception:
        return None


def list_filings(
    cik: str,
    *,
    forms: list[str],
    since: date | None = None,
    ticker: str | None = None,
) -> list[FilingEvent]:
    """List filings for one CIK, filtered by form type.

    Form names follow SEC convention exactly ("4", "13F-HR", "13D", "13G",
    "13D/A", "13G/A", "10-Q", "10-K", "S-3", "S-3/A", "424B5", "8-K").
    """
    payload = _submissions_payload(cik)
    if not payload:
        return []

    recent = (payload.get("filings") or {}).get("recent") or {}
    accession_numbers = recent.get("accessionNumber") or []
    form_arr = recent.get("form") or []
    filed_arr = recent.get("filingDate") or []
    period_arr = recent.get("reportDate") or []
    primary_doc_arr = recent.get("primaryDocument") or []

    accepted_forms = {f.strip() for f in forms}
    cik10 = pad_cik(cik)
    out: list[FilingEvent] = []

    n = min(len(accession_numbers), len(form_arr), len(filed_arr))
    for i in range(n):
        form = str(form_arr[i]).strip()
        if accepted_forms and form not in accepted_forms:
            continue
        filed = _safe_date(filed_arr[i])
        if filed is None:
            continue
        if since is not None and filed < since:
            continue
        accession = str(accession_numbers[i])
        primary = str(primary_doc_arr[i]) if i < len(primary_doc_arr) else ""
        period = _safe_date(period_arr[i]) if i < len(period_arr) else None
        url = _filing_url(cik10, accession, primary)

        # Pydantic v2 strict-Literal: skip forms we don't model
        try:
            out.append(
                FilingEvent(
                    cik=cik10,
                    ticker=ticker,
                    form=form,                # type: ignore[arg-type]
                    accession=accession,
                    filed=filed,
                    period_of_report=period,
                    url=url,
                    payload={"primary_document": primary},
                )
            )
        except Exception as exc:                                       # noqa: BLE001
            log.debug("Skip filing form=%s acc=%s: %s", form, accession, exc)
            continue
    return out


# ---------------------------------------------------------------------------
# Full-text search (EFTS)
# ---------------------------------------------------------------------------
def fulltext_search(
    query: str,
    *,
    forms: list[str] | None = None,
    dateRange: tuple[date, date] | None = None,
    limit: int = 50,
) -> list[FilingEvent]:
    """Search SEC EFTS for ``query`` and return matching filings.

    The EFTS endpoint replies with a JSON envelope at `hits.hits[*]._source`
    containing `adsh`, `form`, `file_date`, `display_names`, `ciks`.
    """
    params: dict[str, Any] = {"q": f'"{query}"', "dateRange": "custom"}
    if dateRange:
        params["startdt"] = dateRange[0].isoformat()
        params["enddt"] = dateRange[1].isoformat()
    else:
        params.pop("dateRange", None)
    if forms:
        params["forms"] = ",".join(forms)

    data = edgar_json(_EFTS_SEARCH, params=params)
    if not data:
        return []
    hits = (((data.get("hits") or {}).get("hits")) or [])[:limit]

    accepted_forms = {f.strip() for f in (forms or [])}
    out: list[FilingEvent] = []
    for h in hits:
        src = h.get("_source") or {}
        form = str(src.get("form", "")).strip()
        if accepted_forms and form not in accepted_forms:
            continue
        accession = str(src.get("adsh") or h.get("_id") or "").strip()
        filed = _safe_date(src.get("file_date"))
        if not accession or filed is None:
            continue
        ciks = src.get("ciks") or []
        primary_cik = pad_cik(ciks[0]) if ciks else ""
        url = (
            f"{WWW_BASE}/cgi-bin/browse-edgar?action=getcompany&CIK={primary_cik}"
            f"&type={form}&dateb=&owner=include&count=10"
        )
        try:
            out.append(
                FilingEvent(
                    cik=primary_cik,
                    ticker=None,
                    form=form,                                # type: ignore[arg-type]
                    accession=accession,
                    filed=filed,
                    period_of_report=None,
                    url=url,
                    payload={"display_names": src.get("display_names", []), "raw": src},
                )
            )
        except Exception as exc:                                       # noqa: BLE001
            log.debug("Skip EFTS hit form=%s: %s", form, exc)
    return out


# ---------------------------------------------------------------------------
# Diagnostics helper (handy in notebooks; not used by tests)
# ---------------------------------------------------------------------------
def dump_known_universe() -> str:
    table = _ticker_table()
    return json.dumps({"n_tickers": len(table)}, indent=2)
