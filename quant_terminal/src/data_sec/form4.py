"""Form 4 (insider transactions) XML parser + ticker-level aggregation.

The SEC publishes one Form 4 XML per accession. We parse the
`nonDerivativeTransaction` block (open-market buys, sells, grants, exercises)
into a flat list of ``InsiderTransaction`` rows. Derivative-only filings
(option grants without exercise) are skipped — they don't move the share
count in a meaningful way for insider sentiment.

Transaction codes per SEC docs:
  P  = open-market purchase
  S  = open-market sale
  A  = grant
  M  = exercise of derivative
  F  = payment of tax via shares
  D  = sale to issuer
  G  = bona fide gift
  X  = exercise of in-the-money derivative
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any
from xml.etree import ElementTree as ET

import pandas as pd

from src.common.schemas import FilingEvent, InsiderTransaction
from src.data_sec.edgar_client import WWW_BASE, edgar_get, pad_cik
from src.data_sec.forms_index import cik_for_ticker, list_filings
from src.utils.cache import read as cache_read, write as cache_write
from src.utils.logging import get_logger

log = get_logger(__name__)


# ---------------------------------------------------------------------------
# XML helpers
# ---------------------------------------------------------------------------
def _txt(elem: ET.Element | None, *path: str) -> str:
    if elem is None:
        return ""
    cur: ET.Element | None = elem
    for tag in path:
        if cur is None:
            return ""
        cur = cur.find(tag)
    return (cur.text or "").strip() if cur is not None and cur.text else ""


def _value(elem: ET.Element | None, *path: str) -> str:
    """Form 4 wraps actual values in `<value>...</value>` children."""
    return _txt(elem, *path, "value")


def _safe_float(s: str) -> float:
    try:
        return float(s)
    except (ValueError, TypeError):
        return 0.0


def _safe_date(s: str) -> date | None:
    if not s:
        return None
    for fmt in ("%Y-%m-%d", "%m/%d/%Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def _reporter_role(owner_node: ET.Element | None) -> str:
    if owner_node is None:
        return "unknown"
    rel = owner_node.find("reportingOwnerRelationship")
    if rel is None:
        return "unknown"
    if (rel.findtext("isOfficer") or "").strip() in ("1", "true"):
        title = (rel.findtext("officerTitle") or "officer").strip()
        return title or "officer"
    if (rel.findtext("isDirector") or "").strip() in ("1", "true"):
        return "director"
    if (rel.findtext("isTenPercentOwner") or "").strip() in ("1", "true"):
        return "10%owner"
    if (rel.findtext("isOther") or "").strip() in ("1", "true"):
        return "other"
    return "unknown"


# ---------------------------------------------------------------------------
# Public parser
# ---------------------------------------------------------------------------
def parse_form4_xml(xml_text: str, *, accession: str = "", ticker: str | None = None) -> list[InsiderTransaction]:
    """Parse a Form 4 XML string into a list of `InsiderTransaction` rows."""
    if not xml_text:
        return []
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as exc:
        log.warning("Form 4 XML parse failed (acc=%s): %s", accession, exc)
        return []

    # Owner block
    owner = root.find("reportingOwner")
    reporter_name = _txt(owner, "reportingOwnerId", "rptOwnerName") or "unknown"
    cik_owner = (_txt(owner, "reportingOwnerId", "rptOwnerCik") or "0").lstrip("0") or "0"
    cik_owner = pad_cik(cik_owner)
    role = _reporter_role(owner)

    # Issuer block — gives us the ticker fallback
    issuer = root.find("issuer")
    issuer_ticker = (_txt(issuer, "issuerTradingSymbol") or "").strip().upper() or None
    eff_ticker = (ticker or issuer_ticker)

    out: list[InsiderTransaction] = []
    for tx in root.findall(".//nonDerivativeTransaction"):
        tx_date = _safe_date(_value(tx, "transactionDate"))
        if tx_date is None:
            continue
        code = _value(tx, "transactionCoding", "transactionCode") or "?"
        shares = _safe_float(_value(tx, "transactionAmounts", "transactionShares"))
        price = _safe_float(_value(tx, "transactionAmounts", "transactionPricePerShare"))
        ad = (_value(tx, "transactionAmounts", "transactionAcquiredDisposedCode") or "").upper()
        signed_shares = shares if ad == "A" else -shares if ad == "D" else shares
        post_holding = _safe_float(_value(tx, "postTransactionAmounts", "sharesOwnedFollowingTransaction"))
        try:
            out.append(
                InsiderTransaction(
                    cik=cik_owner,
                    reporter_name=reporter_name,
                    reporter_role=role,
                    ticker=eff_ticker,
                    transaction_date=tx_date,
                    code=code,
                    shares=signed_shares,
                    price=price,
                    value_usd=abs(signed_shares) * price,
                    post_holding_shares=post_holding,
                    accession=accession,
                )
            )
        except Exception as exc:                                       # noqa: BLE001
            log.debug("Skip Form 4 row in %s: %s", accession, exc)
            continue
    return out


def parse_form4(filing: FilingEvent) -> list[InsiderTransaction]:
    """Fetch + parse the primary XML of one Form 4 filing."""
    if filing.form != "4":
        return []
    primary = (filing.payload or {}).get("primary_document") or ""
    if not primary:
        return []

    cik_int = int(filing.cik.lstrip("0") or "0")
    acc_no_dashes = filing.accession.replace("-", "")
    xml_url = f"{WWW_BASE}/Archives/edgar/data/{cik_int}/{acc_no_dashes}/{primary}"
    try:
        resp = edgar_get(xml_url)
    except Exception as exc:                                           # noqa: BLE001
        log.warning("Form 4 fetch failed acc=%s: %s", filing.accession, exc)
        return []
    if resp.status_code != 200:
        return []
    return parse_form4_xml(resp.text, accession=filing.accession, ticker=filing.ticker)


# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------
_EMPTY_SUMMARY_COLS = [
    "ticker", "net_shares", "net_usd", "n_buyers", "n_sellers", "last_filing",
]


def insider_summary(ticker: str, *, lookback_days: int = 180) -> pd.DataFrame:
    """Aggregate the last ``lookback_days`` of Form 4 activity for ``ticker``.

    Returns a single-row DataFrame with the columns documented in the plan
    (ticker, net_shares, net_usd, n_buyers, n_sellers, last_filing). Empty
    DataFrame on data unavailability so the UI can `df.empty` check.
    """
    if not ticker:
        return pd.DataFrame(columns=_EMPTY_SUMMARY_COLS)

    cik = cik_for_ticker(ticker)
    if cik is None:
        log.info("insider_summary: unknown ticker %s", ticker)
        return pd.DataFrame(columns=_EMPTY_SUMMARY_COLS)

    cache_key = f"summary|{ticker}|{lookback_days}"
    cached = cache_read(cache_key, namespace="sec_form4", max_age_seconds=60 * 60 * 6)
    if cached is not None and not cached.empty:
        return cached

    since = date.today() - timedelta(days=lookback_days)
    filings = list_filings(cik, forms=["4"], since=since, ticker=ticker.upper())
    rows: list[InsiderTransaction] = []
    # cap to keep dev-loop fast; 100 form-4s is ~3 months of dense activity
    for f in filings[:100]:
        rows.extend(parse_form4(f))

    if not rows:
        empty = pd.DataFrame(columns=_EMPTY_SUMMARY_COLS)
        return empty

    df = pd.DataFrame([r.model_dump() for r in rows])
    buyers_mask = df["shares"] > 0
    sellers_mask = df["shares"] < 0
    out = pd.DataFrame([{
        "ticker": ticker.upper(),
        "net_shares": float(df["shares"].sum()),
        "net_usd": float((df["shares"] * df["price"]).sum()),
        "n_buyers": int(df.loc[buyers_mask, "reporter_name"].nunique()),
        "n_sellers": int(df.loc[sellers_mask, "reporter_name"].nunique()),
        "last_filing": df["transaction_date"].max(),
    }])
    cache_write(cache_key, out, namespace="sec_form4")
    return out
