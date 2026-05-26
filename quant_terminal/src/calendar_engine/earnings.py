"""Earnings calendar — yfinance primary, Nasdaq HTML scrape fallback.

Public API
----------
* `fetch_earnings(tickers)` — returns `list[CalendarEvent]` with category
  ``"earnings"``.  Each event carries the next earnings date plus the
  consensus EPS estimate in ``payload``.
* `next_earnings_date(ticker)` — convenience single-ticker accessor.

Sources
-------
1. **yfinance** — `Ticker.calendar` (a dict on modern yfinance versions; a
   one-row DataFrame on older versions).  We support both shapes.
2. **Nasdaq earnings calendar** HTML page — only invoked when yfinance
   returns NaT/None.  Pure best-effort; failures are logged at ``debug``
   level so they don't pollute production logs.

Cache
-----
Namespace ``cal_earnings``, 6-hour TTL (earnings dates rarely move
intra-day so an aggressive TTL keeps us off the rate-limiters).
"""
from __future__ import annotations

import hashlib
from datetime import date, datetime, time, timedelta
from typing import Any

import pandas as pd

from src.common.schemas import CalendarEvent
from src.utils.cache import read as cache_read, write as cache_write
from src.utils.config import get_config
from src.utils.logging import get_logger

log = get_logger(__name__)

_CACHE_NS = "cal_earnings"
_CACHE_TTL_SECONDS = 6 * 3600


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def _event_id(ticker: str, when: date) -> str:
    raw = f"earnings|{ticker.upper()}|{when.isoformat()}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def _coerce_date(value: Any) -> date | None:
    """Accept date | datetime | pd.Timestamp | str | list-of-them → date."""
    if value is None:
        return None
    # yfinance sometimes returns a list of 2 dates (range); we take the first.
    if isinstance(value, (list, tuple)):
        for v in value:
            d = _coerce_date(v)
            if d is not None:
                return d
        return None
    if isinstance(value, pd.Timestamp):
        if pd.isna(value):
            return None
        return value.date()
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value[:10])
        except ValueError:
            try:
                return pd.to_datetime(value).date()  # type: ignore[union-attr]
            except Exception:
                return None
    return None


def _coerce_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (list, tuple)) and value:
        return _coerce_float(value[0])
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    if pd.isna(f):
        return None
    return f


# ---------------------------------------------------------------------------
# yfinance path
# ---------------------------------------------------------------------------
def _yfinance_calendar(ticker: str) -> tuple[date | None, float | None]:
    """Return (next_earnings_date, eps_estimate) or (None, None)."""
    cfg = get_config()
    yf_sym = cfg.yfinance_symbol(ticker) or ticker
    try:
        import yfinance as yf
    except ImportError:
        log.error("yfinance not installed; cannot fetch earnings for %s", ticker)
        return None, None
    try:
        tk = yf.Ticker(yf_sym)
        cal = tk.calendar
    except Exception as exc:
        log.debug("yfinance.calendar failed for %s: %s", yf_sym, exc)
        return None, None

    if cal is None:
        return None, None

    # Modern yfinance (>=0.2.30): dict-like
    if isinstance(cal, dict):
        d = _coerce_date(cal.get("Earnings Date"))
        est = _coerce_float(cal.get("Earnings Average"))
        return d, est

    # Older yfinance: DataFrame with columns indexed by event row(s)
    if isinstance(cal, pd.DataFrame):
        if cal.empty:
            return None, None
        # Often the next earnings sits in a "Earnings Date" row or column.
        try:
            row_names = [str(r).lower() for r in cal.index]
            if any("earnings" in n for n in row_names):
                ed_row = cal.iloc[[i for i, n in enumerate(row_names) if "earnings" in n][0]]
                d = _coerce_date(ed_row.iloc[0])
                return d, None
            # Fallback: take first cell that parses as date
            for v in cal.values.flatten():
                d = _coerce_date(v)
                if d is not None:
                    return d, None
        except Exception as exc:
            log.debug("yfinance.calendar dataframe parse failed for %s: %s", yf_sym, exc)
    return None, None


# ---------------------------------------------------------------------------
# Nasdaq HTML scrape fallback (best-effort)
# ---------------------------------------------------------------------------
def _nasdaq_next_earnings(ticker: str) -> date | None:
    """Best-effort scrape of nasdaq.com earnings-calendar page.

    Returns ``None`` on any failure — the goal is never to raise.
    """
    try:
        import httpx
    except ImportError:
        log.debug("httpx not installed; skipping Nasdaq fallback")
        return None
    url = f"https://www.nasdaq.com/market-activity/stocks/{ticker.lower()}/earnings"
    try:
        with httpx.Client(timeout=8.0, follow_redirects=True, headers={
            "User-Agent": "Mozilla/5.0 quant-terminal",
            "Accept": "text/html",
        }) as client:
            resp = client.get(url)
        if resp.status_code != 200:
            return None
        html = resp.text
    except Exception as exc:
        log.debug("nasdaq fetch failed for %s: %s", ticker, exc)
        return None

    # Heuristic: search for "Earnings Date" + first date pattern after it.
    import re
    pat = re.compile(
        r"(Earnings\s*Date|Next\s*Earnings)\D{0,40}?"
        r"(\d{1,2}/\d{1,2}/\d{2,4}|[A-Za-z]{3,9}\s+\d{1,2},?\s*\d{4})",
        re.IGNORECASE,
    )
    m = pat.search(html)
    if not m:
        return None
    raw = m.group(2)
    try:
        return pd.to_datetime(raw, errors="coerce").date()  # type: ignore[union-attr]
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def next_earnings_date(ticker: str) -> tuple[date | None, float | None]:
    """Return the next earnings date + EPS estimate for `ticker`."""
    d, est = _yfinance_calendar(ticker)
    if d is None:
        d = _nasdaq_next_earnings(ticker)
    return d, est


def fetch_earnings(tickers: list[str]) -> list[CalendarEvent]:
    """Return upcoming earnings events for `tickers` as `CalendarEvent` list.

    Uses the cache (6-hour TTL) keyed on the sorted ticker list so repeated
    UI invocations are cheap.  On cache miss, queries yfinance one-by-one
    with a Nasdaq HTML fallback when yfinance returns nothing.
    """
    if not tickers:
        return []
    tickers = sorted({t.strip().upper() for t in tickers if t and t.strip()})
    cache_key = "|".join(tickers)
    cached = cache_read(cache_key, namespace=_CACHE_NS, max_age_seconds=_CACHE_TTL_SECONDS)
    if cached is not None and not cached.empty:
        events: list[CalendarEvent] = []
        for rec in cached.to_dict(orient="records"):
            try:
                rec = dict(rec)
                rec["start"] = pd.to_datetime(rec["start"]).to_pydatetime()
                if rec.get("end") not in (None, "", float("nan")) and not pd.isna(rec.get("end")):
                    rec["end"] = pd.to_datetime(rec["end"]).to_pydatetime()
                else:
                    rec["end"] = None
                payload = rec.get("payload")
                if isinstance(payload, str):
                    import json
                    try:
                        rec["payload"] = json.loads(payload)
                    except Exception:
                        rec["payload"] = {}
                events.append(CalendarEvent(**rec))
            except Exception as exc:
                log.debug("earnings cache deserialise failed: %s", exc)
        if events:
            return events

    out: list[CalendarEvent] = []
    today = date.today()
    for tk in tickers:
        d, est = next_earnings_date(tk)
        if d is None or d < today - timedelta(days=2):
            continue
        start = datetime.combine(d, time(12, 0))  # mid-day placeholder
        title = f"{tk} earnings"
        if est is not None:
            title += f" (cons. EPS {est:.2f})"
        payload: dict[str, Any] = {"eps_estimate": est}
        out.append(CalendarEvent(
            event_id=_event_id(tk, d),
            ticker=tk,
            category="earnings",
            start=start,
            end=None,
            title=title,
            source="yfinance",
            payload=payload,
        ))

    # write cache
    if out:
        rows = []
        for ev in out:
            r = ev.model_dump()
            r["start"] = ev.start.isoformat()
            r["end"] = ev.end.isoformat() if ev.end else None
            import json
            r["payload"] = json.dumps(ev.payload)
            rows.append(r)
        try:
            cache_write(cache_key, pd.DataFrame(rows), namespace=_CACHE_NS)
        except Exception as exc:
            log.debug("earnings cache write failed: %s", exc)
    return out
