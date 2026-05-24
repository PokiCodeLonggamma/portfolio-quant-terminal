"""Pre-IPO / private companies watchlist loader.

Parses `config/private_watchlist.yaml` and returns a DataFrame with the
columns the UI expects:

    symbol, name, sub_theme, latest_valuation_usd_b, last_round_date,
    last_round_type, lead_investor, listed_proxies, notes, private

Valuations and rounds are manual — refresh by editing the YAML file.
"""
from __future__ import annotations

from datetime import date, datetime

import pandas as pd
import yaml

from src.utils.config import CONFIG_DIR
from src.utils.logging import get_logger

log = get_logger(__name__)

PRIVATE_YAML = CONFIG_DIR / "private_watchlist.yaml"

_PRIVATE_COLUMNS: tuple[str, ...] = (
    "symbol",
    "name",
    "sub_theme",
    "latest_valuation_usd_b",
    "last_round_date",
    "last_round_type",
    "lead_investor",
    "listed_proxies",
    "notes",
    "private",
)


def _coerce_date(v) -> date | None:
    if v is None:
        return None
    if isinstance(v, date) and not isinstance(v, datetime):
        return v
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, str):
        try:
            return datetime.fromisoformat(v).date()
        except ValueError:
            try:
                return datetime.strptime(v, "%Y-%m-%d").date()
            except ValueError:
                log.warning("Could not parse date %r in private_watchlist.yaml", v)
                return None
    return None


def load_private_watchlist() -> pd.DataFrame:
    """Return the private watchlist as a DataFrame.

    Always returns the canonical column set, even when the file is empty.
    """
    if not PRIVATE_YAML.exists():
        log.warning("Private watchlist YAML missing: %s", PRIVATE_YAML)
        return pd.DataFrame(columns=list(_PRIVATE_COLUMNS))

    with PRIVATE_YAML.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}

    raw = data.get("private", {}) if isinstance(data, dict) else {}
    if not isinstance(raw, dict):
        log.warning("private_watchlist.yaml::private is not a mapping; got %r", type(raw))
        return pd.DataFrame(columns=list(_PRIVATE_COLUMNS))

    rows: list[dict] = []
    for name, meta in raw.items():
        meta = dict(meta or {})
        rows.append(
            {
                "symbol": str(name),
                "name": str(name).replace("_", " "),
                "sub_theme": str(meta.get("sub_theme", "Unclassified")),
                "latest_valuation_usd_b": (
                    float(meta["latest_valuation_usd_b"])
                    if meta.get("latest_valuation_usd_b") is not None
                    else None
                ),
                "last_round_date": _coerce_date(meta.get("last_round_date")),
                "last_round_type": meta.get("last_round_type"),
                "lead_investor": meta.get("lead_investor"),
                "listed_proxies": list(meta.get("listed_proxies") or []),
                "notes": meta.get(
                    "notes", "valuations approximated, refresh manually"
                ),
                "private": True,
            }
        )

    if not rows:
        return pd.DataFrame(columns=list(_PRIVATE_COLUMNS))
    df = pd.DataFrame(rows)
    for col in _PRIVATE_COLUMNS:
        if col not in df.columns:
            df[col] = None
    return df[list(_PRIVATE_COLUMNS)]
