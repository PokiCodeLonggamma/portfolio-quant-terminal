"""13F-HR information-table parser + smart-money tape.

13F-HR is a quarterly filing by institutional investment managers with
>$100M in AUM. The "information table" inside the filing is an XML document
listing every reportable holding (cusip, shares, value in $thousands).

We parse it into typed `Holding13F` rows and build a per-ticker smart-money
tape that counts how many funds hold each ticker, the QoQ delta, and lists
the top-5 funds by USD value.

The SEC publishes 13F XML with a default namespace
(http://www.sec.gov/edgar/document/thirteenf/informationtable) — we strip
namespaces during parse for simplicity.
"""
from __future__ import annotations

import re
from collections import defaultdict
from datetime import date
from typing import Any
from xml.etree import ElementTree as ET

import pandas as pd

from src.common.schemas import FilingEvent, Holding13F
from src.data_sec.edgar_client import WWW_BASE, edgar_get, pad_cik
from src.data_sec.forms_index import list_filings
from src.utils.cache import read as cache_read, write as cache_write
from src.utils.logging import get_logger

log = get_logger(__name__)


# ---------------------------------------------------------------------------
# Namespace-agnostic XML parse
# ---------------------------------------------------------------------------
_NS_PATTERN = re.compile(r"\{[^}]+\}")


def _strip_ns(xml_text: str) -> str:
    return _NS_PATTERN.sub("", xml_text)


def _val(node: ET.Element | None, *tags: str) -> str:
    if node is None:
        return ""
    cur: ET.Element | None = node
    for t in tags:
        if cur is None:
            return ""
        cur = cur.find(t)
    return (cur.text or "").strip() if cur is not None and cur.text else ""


def _safe_int(s: str) -> int:
    try:
        return int(float(s))
    except (ValueError, TypeError):
        return 0


def parse_13f_xml(
    xml_text: str,
    *,
    cik_fund: str = "",
    fund_name: str = "",
    period_of_report: date | None = None,
) -> list[Holding13F]:
    """Parse a 13F information-table XML string. Robust to SEC namespace tags."""
    if not xml_text or not period_of_report:
        return []
    try:
        root = ET.fromstring(_strip_ns(xml_text))
    except ET.ParseError as exc:
        log.warning("13F XML parse failed for fund %s: %s", fund_name, exc)
        return []

    out: list[Holding13F] = []
    for ent in root.findall(".//infoTable"):
        cusip = _val(ent, "cusip").strip()
        name = _val(ent, "nameOfIssuer")
        shares = _safe_int(_val(ent, "shrsOrPrnAmt", "sshPrnamt"))
        value_kusd = _safe_int(_val(ent, "value"))
        if not cusip or not name:
            continue
        try:
            out.append(
                Holding13F(
                    cik_fund=cik_fund,
                    fund_name=fund_name,
                    cusip=cusip,
                    ticker=None,                 # ticker mapping is a CUSIP DB problem; out of scope
                    name_of_issuer=name,
                    shares=shares,
                    value_usd_000=value_kusd,
                    period_of_report=period_of_report,
                )
            )
        except Exception as exc:                                       # noqa: BLE001
            log.debug("Skip 13F row cusip=%s: %s", cusip, exc)
    return out


def parse_13f_information_table(filing: FilingEvent) -> list[Holding13F]:
    """Fetch + parse a 13F-HR's information-table.

    The "primary document" is usually the human-readable cover; the
    information table itself sits in a sibling XML file. We try a small set
    of common names — `infotable.xml`, `informationtable.xml`, plus the
    filing's index.json document list as a fallback.
    """
    if filing.form != "13F-HR":
        return []

    cik_int = int(filing.cik.lstrip("0") or "0")
    acc_no_dashes = filing.accession.replace("-", "")
    base = f"{WWW_BASE}/Archives/edgar/data/{cik_int}/{acc_no_dashes}"

    xml_text = ""
    for candidate in ("informationtable.xml", "infotable.xml", "form13fInfoTable.xml"):
        try:
            r = edgar_get(f"{base}/{candidate}")
        except Exception:
            continue
        if r.status_code == 200 and "<" in r.text:
            xml_text = r.text
            break

    if not xml_text:
        # fallback: read index.json to enumerate document list
        try:
            r = edgar_get(f"{base}/index.json")
        except Exception:
            r = None
        if r is not None and r.status_code == 200:
            try:
                items = (r.json().get("directory") or {}).get("item") or []
            except Exception:
                items = []
            for it in items:
                name = (it.get("name") or "").lower()
                if name.endswith(".xml") and ("info" in name or "table" in name):
                    try:
                        rr = edgar_get(f"{base}/{it['name']}")
                    except Exception:
                        continue
                    if rr.status_code == 200:
                        xml_text = rr.text
                        break

    if not xml_text:
        return []
    return parse_13f_xml(
        xml_text,
        cik_fund=filing.cik,
        fund_name=(filing.payload or {}).get("fund_name", "") or "",
        period_of_report=filing.period_of_report or filing.filed,
    )


# ---------------------------------------------------------------------------
# Smart-money tape (cross-fund aggregator)
# ---------------------------------------------------------------------------
_EMPTY_TAPE_COLS = ["ticker", "n_funds_long", "qoq_delta_funds", "sum_value_usd", "top5_funds"]


def smart_money_tape(
    fund_holdings_by_quarter: dict[str, list[Holding13F]] | None = None,
    *,
    tickers: list[str] | None = None,
    quarter: str | None = None,
) -> pd.DataFrame:
    """Aggregate per-ticker fund presence across the smart-money universe.

    The function intentionally accepts already-parsed holdings keyed by
    quarter string (``"2025Q1"``) so the UI / app can fetch+parse with its
    own concurrency policy. ``tickers`` filters output rows; ``quarter``
    selects which quarter becomes "now" — the immediately prior one is used
    for the QoQ delta.

    Falls back to an empty DataFrame when no holdings are supplied.
    """
    if not fund_holdings_by_quarter:
        return pd.DataFrame(columns=_EMPTY_TAPE_COLS)

    quarters_sorted = sorted(fund_holdings_by_quarter.keys())
    if quarter is None:
        quarter = quarters_sorted[-1]
    if quarter not in fund_holdings_by_quarter:
        log.info("smart_money_tape: quarter %s missing; falling back to latest", quarter)
        quarter = quarters_sorted[-1]
    prior = quarters_sorted[quarters_sorted.index(quarter) - 1] if quarters_sorted.index(quarter) > 0 else None

    def _counts(holdings: list[Holding13F]) -> dict[str, dict[str, Any]]:
        per_issuer: dict[str, dict[str, Any]] = defaultdict(
            lambda: {"funds": set(), "value": 0, "top": []}
        )
        for h in holdings:
            key = (h.name_of_issuer or "").upper()
            per_issuer[key]["funds"].add(h.fund_name)
            per_issuer[key]["value"] += h.value_usd_000
            per_issuer[key]["top"].append((h.fund_name, h.value_usd_000))
        return per_issuer

    now_idx = _counts(fund_holdings_by_quarter[quarter])
    prior_idx = _counts(fund_holdings_by_quarter[prior]) if prior else {}

    ticker_filter = {t.strip().upper() for t in (tickers or [])}
    rows = []
    for issuer, agg in now_idx.items():
        if ticker_filter and issuer not in ticker_filter:
            continue
        top5 = sorted(agg["top"], key=lambda x: x[1], reverse=True)[:5]
        prior_funds = prior_idx.get(issuer, {}).get("funds", set())
        rows.append({
            "ticker": issuer,
            "n_funds_long": len(agg["funds"]),
            "qoq_delta_funds": len(agg["funds"]) - len(prior_funds),
            "sum_value_usd": int(agg["value"]) * 1000,                # USD (k$ -> $)
            "top5_funds": ", ".join(f"{name} ({int(val/1000):,}M$)" for name, val in top5),
        })

    if not rows:
        return pd.DataFrame(columns=_EMPTY_TAPE_COLS)
    return pd.DataFrame(rows).sort_values("sum_value_usd", ascending=False).reset_index(drop=True)
