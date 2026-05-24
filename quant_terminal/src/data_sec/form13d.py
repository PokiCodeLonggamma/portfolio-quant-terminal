"""13D / 13G beneficial-ownership filings.

Form 13D is filed within 10 days of an entity acquiring >5% beneficial
ownership of a US-listed equity (an "activist" position). 13G is the
passive-investor flavour. Either can be amended (13D/A, 13G/A).

For our purposes we just need the *list* of recent 13D/13G filings against
a ticker — the parsing of the SC 13D HTML body is out of scope (the form
is free-text).
"""
from __future__ import annotations

from datetime import date, timedelta

from src.common.schemas import FilingEvent
from src.data_sec.forms_index import cik_for_ticker, list_filings
from src.utils.logging import get_logger

log = get_logger(__name__)


_FORM_SET = ["13D", "13G", "13D/A", "13G/A", "SC 13D", "SC 13G"]


def detect_13d_13g(ticker: str, *, since: date | None = None) -> list[FilingEvent]:
    """Return 13D/13G filings for ``ticker`` since the given date.

    Note that 13D filings are usually made *by the acquirer* not the issuer
    — so this function actually queries the issuer's submissions feed where
    the SEC cross-references inbound filings via the EDGAR "owner=include"
    flag. The submissions API returns those cross-refs in the same recent
    array as own filings.
    """
    if not ticker:
        return []
    cik = cik_for_ticker(ticker)
    if cik is None:
        log.info("detect_13d_13g: unknown ticker %s", ticker)
        return []
    if since is None:
        since = date.today() - timedelta(days=180)
    # The Pydantic Literal accepts only the SEC short forms — the
    # submissions API uses those, not "SC 13D".
    accepted = [f for f in _FORM_SET if f in ("13D", "13G", "13D/A", "13G/A")]
    return list_filings(cik, forms=accepted, since=since, ticker=ticker.upper())
