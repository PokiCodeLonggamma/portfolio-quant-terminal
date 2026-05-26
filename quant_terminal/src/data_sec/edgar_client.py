"""Thin SEC EDGAR HTTP wrapper.

The single responsibility of this module is to make sure every outbound call
to SEC carries:

  * A `User-Agent` header containing the operator's email (per SEC fair-use
    policy https://www.sec.gov/os/accessing-edgar-data).
  * `Accept-Encoding: gzip, deflate`.
  * A global throttle of <= 10 requests / second / process.

All higher-level modules (`forms_index`, `form4`, `form13f`, `xbrl_facts`,
`dilution`, ...) must funnel their HTTP through `edgar_get` / `edgar_json`.
If `SEC_EMAIL` is missing we still allow the request but tag the UA as
`anonymous` and emit a warning — degraded mode rather than hard-fail keeps
the Streamlit UI usable for offline demos.
"""
from __future__ import annotations

import threading
import time
from collections import deque
from typing import Any

import httpx

from src.utils.config import get_config
from src.utils.logging import get_logger

log = get_logger(__name__)


SEC_BASE: str = "https://data.sec.gov"
WWW_BASE: str = "https://www.sec.gov"
EFTS_BASE: str = "https://efts.sec.gov"

# SEC fair-use ceiling is 10 req/s. Stay one under to leave headroom for
# concurrent dev tools (browser, MCP probes, ...).
_MAX_REQ_PER_SECOND = 9
_WINDOW_SECONDS = 1.0

_call_times: deque[float] = deque()
_throttle_lock = threading.Lock()


def _throttle() -> None:
    """Block until issuing one more request keeps us under the rate cap."""
    with _throttle_lock:
        now = time.monotonic()
        while _call_times and (now - _call_times[0]) > _WINDOW_SECONDS:
            _call_times.popleft()
        if len(_call_times) >= _MAX_REQ_PER_SECOND:
            sleep_for = _WINDOW_SECONDS - (now - _call_times[0]) + 0.005
            if sleep_for > 0:
                time.sleep(sleep_for)
            now = time.monotonic()
            while _call_times and (now - _call_times[0]) > _WINDOW_SECONDS:
                _call_times.popleft()
        _call_times.append(now)


def _user_agent() -> str:
    cfg = get_config()
    email = (cfg.secrets.sec_email or "").strip()
    if not email:
        log.warning("SEC_EMAIL not configured — using anonymous UA; SEC may block requests")
        email = "anonymous@example.com"
    return f"quant-terminal/0.1 ({email})"


def _headers() -> dict[str, str]:
    return {
        "User-Agent": _user_agent(),
        "Accept-Encoding": "gzip, deflate",
        "Accept": "application/json, text/html;q=0.9, */*;q=0.5",
        "Host-Override": "",
    }


def _resolve_url(path: str) -> str:
    if path.startswith("http://") or path.startswith("https://"):
        return path
    if path.startswith("/"):
        return SEC_BASE + path
    return f"{SEC_BASE}/{path}"


def edgar_get(
    path: str,
    *,
    params: dict[str, Any] | None = None,
    timeout: float = 20.0,
) -> httpx.Response:
    """GET wrapper. Returns the raw httpx.Response. Raises on transport error.

    Status codes are NOT raised automatically; callers decide whether 404 is
    a real failure (filing missing) or expected (search miss).
    """
    url = _resolve_url(path)
    _throttle()
    headers = _headers()
    headers.pop("Host-Override", None)
    try:
        resp = httpx.get(url, params=params, headers=headers, timeout=timeout, follow_redirects=True)
    except httpx.HTTPError as exc:
        log.warning("SEC GET %s failed: %s", url, exc)
        raise
    if resp.status_code >= 500:
        log.warning("SEC GET %s -> HTTP %s", url, resp.status_code)
    return resp


def edgar_json(
    path: str,
    *,
    params: dict[str, Any] | None = None,
    timeout: float = 20.0,
) -> dict[str, Any]:
    """GET + parse JSON. Returns `{}` on any failure so the caller can degrade."""
    try:
        resp = edgar_get(path, params=params, timeout=timeout)
    except Exception:
        return {}
    if resp.status_code != 200:
        log.info("SEC JSON %s returned %s", path, resp.status_code)
        return {}
    try:
        data = resp.json()
        if isinstance(data, dict):
            return data
        # SEC sometimes returns an array (e.g. EFTS hits) — wrap.
        return {"_root": data}
    except Exception as exc:
        log.warning("SEC JSON parse failed for %s: %s", path, exc)
        return {}


def pad_cik(cik: str | int) -> str:
    """SEC submissions API requires 10-digit zero-padded CIKs."""
    return str(cik).strip().lstrip("CIK").zfill(10)
