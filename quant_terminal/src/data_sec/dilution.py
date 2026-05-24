"""ATM / shelf-offering detection + dilution scoring.

Three signals feed the dilution_score (1-5):

  1. **Active S-3 shelf** — issuer has an effective registration on file.
     S-3 alone is permissive; you need a 424B5 prospectus supplement to
     actually sell shares ATM (At-The-Market). We scan the issuer's last
     365 days of S-3 / S-3/A filings and the last 90 days of 424B5
     supplements.

  2. **Convertibles outstanding** — XBRL `ConvertibleDebt` family.

  3. **8-K dilution catalysts** — 8-Ks whose primary doc text mentions
     "at-the-market", "ATM offering", "controlled equity offering", or
     "registration statement on Form S-3".

The score saturates at 5; rationale strings are accumulated for the UI.
"""
from __future__ import annotations

from datetime import date, timedelta

import pandas as pd

from src.common.schemas import DilutionAssessment
from src.data_sec.edgar_client import edgar_get
from src.data_sec.forms_index import cik_for_ticker, list_filings
from src.data_sec.xbrl_facts import convertibles_outstanding_usd, latest_shares_outstanding
from src.utils.cache import read as cache_read, write as cache_write
from src.utils.logging import get_logger

log = get_logger(__name__)


_ATM_KEYWORDS = (
    "at-the-market",
    "at the market",
    "ATM offering",
    "controlled equity offering",
    "sales agreement",
    "equity distribution agreement",
)


def _doc_text(filing_payload: dict, cik: str, accession: str) -> str:
    primary = (filing_payload or {}).get("primary_document") or ""
    if not primary:
        return ""
    cik_int = int(cik.lstrip("0") or "0")
    acc_no_dashes = accession.replace("-", "")
    url = f"https://www.sec.gov/Archives/edgar/data/{cik_int}/{acc_no_dashes}/{primary}"
    try:
        r = edgar_get(url, timeout=30.0)
    except Exception as exc:
        log.debug("doc fetch failed %s: %s", url, exc)
        return ""
    if r.status_code != 200:
        return ""
    # cheap text-ish extraction (we don't pay the BeautifulSoup tax here)
    text = r.text
    return text[:200_000]                                              # cap to keep CPU sane


def _keyword_hit(text: str) -> bool:
    low = text.lower()
    return any(kw.lower() in low for kw in _ATM_KEYWORDS)


def assess_dilution(ticker: str) -> DilutionAssessment:
    """Return a `DilutionAssessment` for ``ticker``.

    Degrades gracefully: when SEC data is unavailable the assessment has
    `dilution_score == 1` (unknown / low confidence) and a "no data"
    rationale.
    """
    safe = DilutionAssessment(
        ticker=ticker.upper() if ticker else "",
        atm_active=False,
        dilution_score=1,
        rationale=["no SEC data"],
    )
    if not ticker:
        return safe

    cik = cik_for_ticker(ticker)
    if cik is None:
        return safe

    cache_key = f"dilution|{ticker.upper()}"
    cached = cache_read(cache_key, namespace="sec_dilution", max_age_seconds=60 * 60 * 24)
    if cached is not None and not cached.empty:
        try:
            row = cached.iloc[0].to_dict()
            return DilutionAssessment(
                ticker=row["ticker"],
                atm_active=bool(row["atm_active"]),
                atm_remaining_usd=row.get("atm_remaining_usd"),
                convertibles_outstanding_usd=row.get("convertibles_outstanding_usd"),
                shares_outstanding=float(row.get("shares_outstanding") or 0.0),
                dilution_score=int(row["dilution_score"]),
                rationale=list(row.get("rationale_csv", "").split("||")) if row.get("rationale_csv") else [],
            )
        except Exception:
            pass

    rationale: list[str] = []
    score = 1
    atm_active = False
    convertibles_usd: float | None = None
    shares_out = 0.0

    today = date.today()

    s3_filings = list_filings(cik, forms=["S-3", "S-3/A"], since=today - timedelta(days=365), ticker=ticker.upper())
    if s3_filings:
        score += 1
        rationale.append(f"{len(s3_filings)} S-3 / S-3/A filings in last 12m")

    b5_filings = list_filings(cik, forms=["424B5"], since=today - timedelta(days=90), ticker=ticker.upper())
    if b5_filings:
        atm_active = True
        score += 2
        rationale.append(f"{len(b5_filings)} 424B5 prospectus supplement(s) in last 90d")

    # Convertibles
    convertibles_usd = convertibles_outstanding_usd(cik) or None
    if convertibles_usd and convertibles_usd > 0:
        score += 1
        rationale.append(f"convertibles outstanding ${convertibles_usd/1e6:,.0f}M")

    # Shares-outstanding (informational; doesn't increment score)
    shares_out = latest_shares_outstanding(cik) or 0.0

    # 8-K text-scan: only look at the most recent 8-K to keep request cost low
    if not atm_active:
        eight_ks = list_filings(cik, forms=["8-K"], since=today - timedelta(days=60), ticker=ticker.upper())
        for f in eight_ks[:3]:
            text = _doc_text(f.payload, cik, f.accession)
            if _keyword_hit(text):
                atm_active = True
                score += 1
                rationale.append(f"ATM keyword hit in 8-K {f.accession}")
                break

    score = max(1, min(5, score))
    if not rationale:
        rationale = ["no S-3 / 424B5 / convertibles detected"]

    out = DilutionAssessment(
        ticker=ticker.upper(),
        atm_active=atm_active,
        atm_remaining_usd=None,                                         # not parseable without prospectus body
        convertibles_outstanding_usd=convertibles_usd,
        shares_outstanding=shares_out,
        dilution_score=score,
        rationale=rationale,
    )

    cache_df = pd.DataFrame([{
        "ticker": out.ticker,
        "atm_active": out.atm_active,
        "atm_remaining_usd": out.atm_remaining_usd,
        "convertibles_outstanding_usd": out.convertibles_outstanding_usd,
        "shares_outstanding": out.shares_outstanding,
        "dilution_score": out.dilution_score,
        "rationale_csv": "||".join(out.rationale),
    }])
    cache_write(cache_key, cache_df, namespace="sec_dilution")
    return out


_PANEL_COLS = [
    "ticker", "dilution_score", "atm_active", "convertibles_outstanding_usd",
    "shares_outstanding", "rationale",
]


def portfolio_dilution_panel(tickers: list[str]) -> pd.DataFrame:
    """Vectorised version: one row per ticker, sorted by score desc."""
    rows = []
    for t in tickers:
        a = assess_dilution(t)
        rows.append({
            "ticker": a.ticker,
            "dilution_score": a.dilution_score,
            "atm_active": a.atm_active,
            "convertibles_outstanding_usd": a.convertibles_outstanding_usd or 0.0,
            "shares_outstanding": a.shares_outstanding,
            "rationale": " ; ".join(a.rationale),
        })
    if not rows:
        return pd.DataFrame(columns=_PANEL_COLS)
    return pd.DataFrame(rows).sort_values("dilution_score", ascending=False).reset_index(drop=True)
