"""Paper / Live mode resolution + safety check.

Default is **paper**. Switching to live requires BOTH:
  - `EXECUTION_ALLOW_LIVE=1` in `.env`
  - `APCA_API_BASE_URL` pointing to the live endpoint
(https://api.alpaca.markets, not …paper-api…).

Any single guard missing → mode falls back to paper.
"""
from __future__ import annotations

import os
from typing import Literal

from src.utils.config import get_config
from src.utils.logging import get_logger

log = get_logger(__name__)

Mode = Literal["paper", "live"]

LIVE_HOST = "api.alpaca.markets"
PAPER_HOST = "paper-api.alpaca.markets"


def resolve_mode() -> Mode:
    """Return the effective mode after applying all guards."""
    cfg = get_config()
    allow_live = os.getenv("EXECUTION_ALLOW_LIVE", "").strip() in {"1", "true", "yes", "on"}
    host = (cfg.secrets.alpaca_base_url or "").lower()

    if not allow_live:
        return "paper"
    if PAPER_HOST in host:
        log.warning("EXECUTION_ALLOW_LIVE=1 but APCA_API_BASE_URL still points to paper — staying paper.")
        return "paper"
    if LIVE_HOST in host:
        log.warning("LIVE MODE ACTIVE — orders will affect a real Alpaca account.")
        return "live"
    log.warning("Unrecognised APCA_API_BASE_URL=%r — defaulting to paper.", cfg.secrets.alpaca_base_url)
    return "paper"


def base_url_for(mode: Mode) -> str:
    if mode == "live":
        return f"https://{LIVE_HOST}"
    return f"https://{PAPER_HOST}"


def is_paper() -> bool:
    return resolve_mode() == "paper"
