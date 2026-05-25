"""Trigger types — evaluated each refresh by the alerts engine.

Each `Trigger` has a name, a cooldown, target channels, severity, and a
`type` discriminator that the engine uses to route to the right evaluator.
The evaluator returns either an `AlertEvent` (fired) or `None` (no match).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Literal

import pandas as pd
from pydantic import BaseModel, Field

Severity = Literal["info", "warning", "critical"]
ChannelName = Literal["discord", "email", "telegram", "streamlit"]
TriggerKind = Literal[
    "price_breach",
    "iv_rank",
    "catalyst_proximity",
    "drawdown_threshold",
    "squeeze_score",
    "runway_low",
    "dilution_high",
    "journal_stop_breach",
]


class Trigger(BaseModel):
    """Declarative trigger definition (one entry in config/alerts.yaml)."""

    name: str
    type: TriggerKind
    enabled: bool = True
    cooldown_minutes: int = 60
    severity: Severity = "warning"
    channels: list[ChannelName] = Field(default_factory=lambda: ["streamlit"])
    # Trigger-specific params (typed loosely; each evaluator validates its own)
    params: dict[str, Any] = Field(default_factory=dict)


class AlertEvent(BaseModel):
    """One fired alert — persisted in history."""

    trigger_name: str
    fired_at: datetime
    severity: Severity
    title: str
    body: str
    payload: dict[str, Any] = Field(default_factory=dict)
    channels: list[ChannelName] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Concrete evaluators
# ---------------------------------------------------------------------------
def eval_price_breach(t: Trigger, prices_eur: pd.DataFrame) -> AlertEvent | None:
    """Params: ticker (str), direction ('above'|'below'), threshold_eur (float)."""
    ticker = t.params.get("ticker")
    direction = t.params.get("direction", "below")
    threshold = float(t.params.get("threshold_eur", 0.0))
    if not ticker or prices_eur is None or prices_eur.empty or ticker not in prices_eur.columns:
        return None
    series = prices_eur[ticker].dropna()
    if series.empty:
        return None
    last_price = float(series.iloc[-1])
    breached = (last_price <= threshold) if direction == "below" else (last_price >= threshold)
    if not breached:
        return None
    return AlertEvent(
        trigger_name=t.name,
        fired_at=datetime.utcnow(),
        severity=t.severity,
        title=f"[{ticker}] price {direction} {threshold:.2f} EUR",
        body=f"Last price {last_price:.2f} EUR (threshold {threshold:.2f}, direction {direction}).",
        payload={"ticker": ticker, "last_price": last_price, "threshold": threshold,
                 "direction": direction},
        channels=list(t.channels),
    )


def eval_drawdown_threshold(t: Trigger, drawdown_series: pd.Series | None) -> AlertEvent | None:
    """Params: threshold_pct (float, negative or positive — interpreted as absolute)."""
    threshold = abs(float(t.params.get("threshold_pct", 0.10)))
    if drawdown_series is None or drawdown_series.empty:
        return None
    current_dd = float(drawdown_series.iloc[-1])
    if current_dd > -threshold:  # drawdown is negative; -threshold is the line
        return None
    return AlertEvent(
        trigger_name=t.name,
        fired_at=datetime.utcnow(),
        severity=t.severity,
        title=f"Drawdown breach: {current_dd * 100:.1f}%",
        body=f"Portfolio drawdown reached {current_dd * 100:.1f}% (limit −{threshold * 100:.1f}%).",
        payload={"current_dd": current_dd, "threshold": threshold},
        channels=list(t.channels),
    )


def eval_squeeze_score(t: Trigger, squeeze_scores_df: pd.DataFrame | None) -> AlertEvent | None:
    """Params: threshold (float 0-100)."""
    threshold = float(t.params.get("threshold", 80.0))
    if squeeze_scores_df is None or squeeze_scores_df.empty:
        return None
    if "score" not in squeeze_scores_df.columns:
        return None
    hits = squeeze_scores_df[squeeze_scores_df["score"] >= threshold]
    if hits.empty:
        return None
    tickers = ",".join(str(x) for x in hits.get("ticker", hits.index).tolist())
    top = float(hits["score"].max())
    return AlertEvent(
        trigger_name=t.name,
        fired_at=datetime.utcnow(),
        severity=t.severity,
        title=f"Squeeze score breach: {tickers}",
        body=f"Squeeze score ≥ {threshold:.0f} on {tickers} (top {top:.0f}).",
        payload={"hits": hits.to_dict("records"), "threshold": threshold},
        channels=list(t.channels),
    )


def eval_catalyst_proximity(t: Trigger, events_list: list[Any] | None) -> AlertEvent | None:
    """Params: window_days (int), categories (list[str] optional filter)."""
    window = int(t.params.get("window_days", 3))
    cats = set(t.params.get("categories", []) or [])
    if not events_list:
        return None
    today = date.today()
    upcoming = []
    for ev in events_list:
        try:
            start = ev.start if hasattr(ev, "start") else ev["start"]
            cat = ev.category if hasattr(ev, "category") else ev.get("category")
            title = ev.title if hasattr(ev, "title") else ev.get("title", "")
        except Exception:
            continue
        sd = start.date() if hasattr(start, "date") else pd.Timestamp(start).date()
        delta_days = (sd - today).days
        if 0 <= delta_days <= window and (not cats or cat in cats):
            upcoming.append((sd, cat, title))
    if not upcoming:
        return None
    desc = "; ".join(f"{d} {c}: {t_}" for d, c, t_ in upcoming[:5])
    return AlertEvent(
        trigger_name=t.name,
        fired_at=datetime.utcnow(),
        severity=t.severity,
        title=f"{len(upcoming)} catalyst(s) within {window}d",
        body=desc,
        payload={"upcoming": [{"date": str(d), "category": c, "title": t_}
                              for d, c, t_ in upcoming]},
        channels=list(t.channels),
    )


def eval_runway_low(t: Trigger, runway_rows: list[dict] | None) -> AlertEvent | None:
    """Params: max_quarters (float). Fires if any portfolio name has runway < threshold."""
    threshold = float(t.params.get("max_quarters", 2.0))
    if not runway_rows:
        return None
    hits = [r for r in runway_rows
            if (r.get("runway_quarters") is not None
                and 0 < float(r["runway_quarters"]) < threshold)]
    if not hits:
        return None
    tickers = ",".join(str(r.get("ticker", "?")) for r in hits)
    return AlertEvent(
        trigger_name=t.name,
        fired_at=datetime.utcnow(),
        severity=t.severity,
        title=f"Runway low: {tickers}",
        body=f"{len(hits)} position(s) with cash runway < {threshold:.1f} quarters.",
        payload={"hits": hits},
        channels=list(t.channels),
    )


def eval_dilution_high(t: Trigger, dilution_rows: list[dict] | None) -> AlertEvent | None:
    """Params: min_score (int). Fires if any name has dilution_score >= min_score."""
    threshold = int(t.params.get("min_score", 4))
    if not dilution_rows:
        return None
    hits = [r for r in dilution_rows
            if int(r.get("dilution_score", 0)) >= threshold]
    if not hits:
        return None
    tickers = ",".join(str(r.get("ticker", "?")) for r in hits)
    return AlertEvent(
        trigger_name=t.name,
        fired_at=datetime.utcnow(),
        severity=t.severity,
        title=f"Dilution risk: {tickers}",
        body=f"{len(hits)} position(s) with dilution_score ≥ {threshold}.",
        payload={"hits": hits},
        channels=list(t.channels),
    )


def eval_journal_stop_breach(t: Trigger, journal_entries: list[Any] | None,
                              prices_eur: pd.DataFrame) -> AlertEvent | None:
    """Fires if any journal entry's current price ≤ stop_loss_thesis_eur (long bias)."""
    if not journal_entries or prices_eur is None or prices_eur.empty:
        return None
    hits = []
    for entry in journal_entries:
        ticker = getattr(entry, "ticker", None) or entry.get("ticker") if isinstance(entry, dict) else None
        stop = getattr(entry, "stop_loss_thesis_eur", None) if not isinstance(entry, dict) else entry.get("stop_loss_thesis_eur")
        if not ticker or stop is None:
            continue
        if ticker not in prices_eur.columns:
            continue
        series = prices_eur[ticker].dropna()
        if series.empty:
            continue
        last = float(series.iloc[-1])
        if last <= float(stop):
            hits.append({"ticker": ticker, "last_eur": last, "stop_eur": float(stop)})
    if not hits:
        return None
    tickers = ",".join(h["ticker"] for h in hits)
    return AlertEvent(
        trigger_name=t.name,
        fired_at=datetime.utcnow(),
        severity=t.severity,
        title=f"Thesis stop breached: {tickers}",
        body="; ".join(f"{h['ticker']} last {h['last_eur']:.2f} ≤ stop {h['stop_eur']:.2f}"
                       for h in hits),
        payload={"hits": hits},
        channels=list(t.channels),
    )


def eval_iv_rank(t: Trigger, iv_ranks: dict[str, float] | None) -> AlertEvent | None:
    """Params: ticker (str), threshold (float 0-100), direction ('above'|'below')."""
    ticker = t.params.get("ticker")
    threshold = float(t.params.get("threshold", 80.0))
    direction = t.params.get("direction", "above")
    if not ticker or not iv_ranks or ticker not in iv_ranks:
        return None
    rank = float(iv_ranks[ticker])
    breached = (rank >= threshold) if direction == "above" else (rank <= threshold)
    if not breached:
        return None
    return AlertEvent(
        trigger_name=t.name,
        fired_at=datetime.utcnow(),
        severity=t.severity,
        title=f"[{ticker}] IV rank {direction} {threshold:.0f}",
        body=f"Current IV rank {rank:.0f} (threshold {threshold:.0f}, {direction}).",
        payload={"ticker": ticker, "iv_rank": rank, "threshold": threshold,
                 "direction": direction},
        channels=list(t.channels),
    )


EVALUATORS: dict[str, str] = {
    "price_breach": "eval_price_breach",
    "iv_rank": "eval_iv_rank",
    "catalyst_proximity": "eval_catalyst_proximity",
    "drawdown_threshold": "eval_drawdown_threshold",
    "squeeze_score": "eval_squeeze_score",
    "runway_low": "eval_runway_low",
    "dilution_high": "eval_dilution_high",
    "journal_stop_breach": "eval_journal_stop_breach",
}
