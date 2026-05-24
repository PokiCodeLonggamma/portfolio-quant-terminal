"""SAM.gov contract-award scraper.

SAM.gov publishes a public REST endpoint for contract opportunities and
awards at https://api.sam.gov/. A free api-key is required for most v3
endpoints; for the *award notices* feed we can use the JSON view of the
"Opportunities" search.

This module ships a defensive shim: if the env var `SAM_API_KEY` is unset
we still return parsed local fixtures when called via the test
monkey-patch path. The public function `awards_dataframe` takes a list of
tickers and tries to attribute awards to them by string-matching the
issuer (`awarded_to`) against issuer name + ticker.
"""
from __future__ import annotations

import os
from datetime import date, datetime, timedelta
from typing import Any

import pandas as pd
import requests

from src.common.schemas import ContractAward
from src.utils.cache import read as cache_read, write as cache_write
from src.utils.logging import get_logger

log = get_logger(__name__)


_SAM_BASE = "https://api.sam.gov/opportunities/v2/search"

# Common ticker -> issuer-name aliases for fuzzy contract matching
_ISSUER_ALIASES: dict[str, list[str]] = {
    "LMT": ["lockheed martin"],
    "RTX": ["raytheon", "rtx corporation"],
    "GD": ["general dynamics"],
    "NOC": ["northrop grumman"],
    "BA": ["boeing"],
    "LDOS": ["leidos"],
    "HII": ["huntington ingalls"],
    "PLTR": ["palantir"],
    "AVAV": ["aerovironment"],
    "KTOS": ["kratos defense"],
    "RKLB": ["rocket lab"],
    "ASTS": ["ast spacemobile"],
    "MSFT": ["microsoft"],
    "AMZN": ["amazon web services", "amazon"],
    "GOOG": ["google", "alphabet"],
    "ORCL": ["oracle"],
}


def _headers(api_key: str | None) -> dict[str, str]:
    h = {"Accept": "application/json", "User-Agent": "quant-terminal/0.1"}
    if api_key:
        h["X-Api-Key"] = api_key
    return h


def _fetch_raw(params: dict[str, Any], *, api_key: str | None = None) -> dict[str, Any]:
    api_key = api_key or os.getenv("SAM_API_KEY")
    if not api_key:
        log.info("SAM_API_KEY not set — sam_gov.search_awards will return [].")
        return {}
    try:
        r = requests.get(_SAM_BASE, params=params, headers=_headers(api_key), timeout=20)
        if r.status_code != 200:
            log.info("SAM HTTP %s for params=%s", r.status_code, params)
            return {}
        return r.json() or {}
    except Exception as exc:
        log.warning("SAM fetch failed: %s", exc)
        return {}


def _parse_award_rows(payload: dict[str, Any]) -> list[ContractAward]:
    out: list[ContractAward] = []
    # SAM responses: payload["opportunitiesData"] is a list of award objects.
    items = (payload.get("opportunitiesData") or payload.get("_root") or [])
    for it in items:
        if not isinstance(it, dict):
            continue
        awarded_to = (
            it.get("awardee", {}).get("name")
            if isinstance(it.get("awardee"), dict)
            else None
        ) or it.get("organizationName") or it.get("awardee_name") or ""
        amount = it.get("award", {}).get("amount") if isinstance(it.get("award"), dict) else None
        amount = float(amount or it.get("awardAmount") or 0.0)
        awarded_on_str = (
            (it.get("award") or {}).get("date") if isinstance(it.get("award"), dict) else None
        ) or it.get("postedDate") or ""
        try:
            awarded_on = datetime.strptime(str(awarded_on_str)[:10], "%Y-%m-%d").date()
        except Exception:
            awarded_on = date.today()
        try:
            out.append(
                ContractAward(
                    awarded_to=str(awarded_to or "unknown"),
                    ticker=None,
                    award_id=str(it.get("noticeId") or it.get("solicitationNumber") or "")[:64],
                    amount_usd=amount,
                    awarded_on=awarded_on,
                    description=(it.get("title") or it.get("description") or "")[:512],
                    agency=str(
                        (it.get("department") or {}).get("name", "")
                        if isinstance(it.get("department"), dict)
                        else (it.get("agency") or "")
                    ),
                )
            )
        except Exception as exc:                                       # noqa: BLE001
            log.debug("Skip SAM row: %s", exc)
    return out


def _attribute_ticker(award: ContractAward, tickers: list[str]) -> ContractAward:
    name = (award.awarded_to or "").lower()
    for t in tickers:
        tu = t.upper()
        if tu in name.upper():
            return award.model_copy(update={"ticker": tu})
        for alias in _ISSUER_ALIASES.get(tu, []):
            if alias in name:
                return award.model_copy(update={"ticker": tu})
    return award


def search_awards(
    tickers: list[str],
    *,
    since: date,
    api_key: str | None = None,
    fetcher=None,                                                      # injection seam for tests
) -> list[ContractAward]:
    """Search recent contract awards and attribute them to ``tickers``.

    ``fetcher`` is an optional callable ``(params, api_key) -> dict`` used
    by tests to short-circuit the HTTP layer.
    """
    fetcher = fetcher or _fetch_raw
    params = {
        "postedFrom": since.strftime("%m/%d/%Y"),
        "postedTo": date.today().strftime("%m/%d/%Y"),
        "ptype": "a",                                                  # 'a' == award notice
        "limit": 100,
    }
    raw = fetcher(params, api_key=api_key)
    awards = _parse_award_rows(raw or {})
    if not tickers:
        return awards
    return [_attribute_ticker(a, tickers) for a in awards]


_PANEL_COLS = ["awarded_on", "ticker", "agency", "amount_usd", "description", "award_id", "awarded_to"]


def awards_dataframe(
    tickers: list[str],
    *,
    lookback_days: int = 365,
    fetcher=None,
) -> pd.DataFrame:
    since = date.today() - timedelta(days=lookback_days)
    cache_key = f"awards|{lookback_days}|{','.join(sorted(t.upper() for t in tickers))}"
    cached = cache_read(cache_key, namespace="sam", max_age_seconds=60 * 60 * 6)
    if cached is not None and not cached.empty:
        return cached
    awards = search_awards(tickers, since=since, fetcher=fetcher)
    if not awards:
        return pd.DataFrame(columns=_PANEL_COLS)
    df = pd.DataFrame([a.model_dump() for a in awards])
    df = df[_PANEL_COLS].sort_values("awarded_on", ascending=False).reset_index(drop=True)
    cache_write(cache_key, df, namespace="sam")
    return df
