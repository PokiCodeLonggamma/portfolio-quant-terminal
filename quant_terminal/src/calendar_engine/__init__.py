"""Catalyst / calendar engine — Cluster 4 (modules A).

Aggregates structured catalyst events (earnings, FOMC, ECB, OPEC+, CPI, EIA,
NRC SMR docket milestones, space launches, contract awards) into a single
typed stream of `CalendarEvent` rows that downstream dashboards (this package
and the watchlist/trading clusters) consume.

The package is named **`calendar_engine`** rather than `calendar` to avoid
collision with Python's stdlib `calendar` module — `from calendar import
CalendarEvent` would otherwise shadow the wrong import in REPL sessions.
"""
from __future__ import annotations

from src.calendar_engine.earnings import fetch_earnings
from src.calendar_engine.implied_moves import implied_move
from src.calendar_engine.macro_events import load_2026, load_macro_events
from src.calendar_engine.space_launches import load_launches

__all__ = [
    "fetch_earnings",
    "implied_move",
    "load_2026",
    "load_launches",
    "load_macro_events",
]
