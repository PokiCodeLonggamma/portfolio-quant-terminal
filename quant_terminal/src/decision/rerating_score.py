"""Re-rating score — how far has the thesis materialised vs the price target?

Composite score in ``[0, 100]`` built from three sub-signals, each weighted:

  * **Price progress** (40%) — how close current price is to the target.
    ``min(1, max(0, (spot - entry) / (target - entry)))`` for longs.
    For short-thesis (target < entry) we mirror the math.
  * **Milestones hit** (40%) — weighted fraction of milestones flagged ``hit``.
  * **Time efficacy** (20%) — slow decay when too much time elapses without
    progress.  Score halves around 18 months.

Recommendation ladder:
  - ``add``      >= 70 and price below target           — thesis playing out, room left
  - ``trim``     >= 90 OR price > target                — most of the move banked
  - ``exit``     stop_loss_thesis breached (handled by caller pre-check)
  - ``review``   < 30 and > 180 days since entry        — call it
  - ``hold``     anything else
"""
from __future__ import annotations

from datetime import date
from typing import Literal

from src.common.schemas import JournalEntry, ReratingScore
from src.utils.cache import read as cache_read, write as cache_write
from src.utils.logging import get_logger

log = get_logger(__name__)

_NS = "decision_rerating"

_W_PRICE = 0.40
_W_MILESTONES = 0.40
_W_TIME = 0.20

_HALF_LIFE_DAYS = 540  # ~18 months — score halves due to time alone


def _price_progress_pct(entry: JournalEntry, current_price_eur: float) -> float | None:
    """Return progress to the price target as a percentage in [0, 100]."""
    target = entry.price_target_eur
    if target is None or current_price_eur is None or current_price_eur <= 0:
        return None
    base = entry.entry_price_eur if entry.entry_price_eur and entry.entry_price_eur > 0 else None
    if base is None or abs(target - base) < 1e-9:
        # Degenerate base — fall back to a simple ratio
        ratio = current_price_eur / target
        return float(max(0.0, min(100.0, ratio * 100.0)))
    if target >= base:
        # Long thesis: progress from entry up to target
        ratio = (current_price_eur - base) / (target - base)
    else:
        # Short thesis: progress is on the downside
        ratio = (base - current_price_eur) / (base - target)
    return float(max(0.0, min(100.0, ratio * 100.0)))


def _milestones_hit_pct(entry: JournalEntry) -> float:
    """Return weighted fraction of milestones marked as hit, in [0, 100]."""
    if not entry.milestones:
        return 0.0
    total_w = sum(max(0.0, m.weight) for m in entry.milestones)
    if total_w <= 0:
        return 0.0
    hit_w = sum(max(0.0, m.weight) for m in entry.milestones if m.hit)
    return float(max(0.0, min(100.0, (hit_w / total_w) * 100.0)))


def _days_since_entry(entry: JournalEntry, today: date) -> int | None:
    if entry.entry_date is None:
        return None
    delta = (today - entry.entry_date).days
    return int(delta) if delta >= 0 else 0


def _time_efficacy(days_since: int | None, milestones_pct: float, price_pct: float | None) -> float:
    """Score that erodes when too much time passes without thesis progress.

    Returns value in [0, 100]. When ``days_since`` is None (no entry date),
    return a neutral 50.
    """
    if days_since is None:
        return 50.0
    # Combined "progress" between 0 and 1
    progress = (milestones_pct + (price_pct if price_pct is not None else milestones_pct)) / 200.0
    progress = max(0.0, min(1.0, progress))
    # When progress = 1, time doesn't matter -> 100.
    # When progress = 0, score halves every _HALF_LIFE_DAYS.
    decay = 0.5 ** (days_since / max(1, _HALF_LIFE_DAYS))
    return float(100.0 * (progress + (1.0 - progress) * decay))


def _recommendation(
    score: float, price_pct: float | None, days_since: int | None,
) -> Literal["hold", "trim", "add", "exit", "review"]:
    # Stop-loss is the caller's job — we don't have spot vs stop_loss_thesis_eur
    # in the score-only signature.
    if price_pct is not None and price_pct >= 100.0:
        return "trim"
    if score >= 90.0:
        return "trim"
    if score >= 70.0:
        return "add"
    if days_since is not None and days_since > 180 and score < 30.0:
        return "review"
    return "hold"


def compute_rerating_score(
    entry: JournalEntry,
    current_price_eur: float,
    today: date | None = None,
) -> ReratingScore:
    """Compute the re-rating score for a thesis.

    Parameters
    ----------
    entry : JournalEntry
        Loaded from `read_journal(...)`.
    current_price_eur : float
        Latest spot in EUR (caller is responsible for FX conversion).
    today : date | None
        Defaults to `date.today()`; pinned for deterministic tests.
    """
    if today is None:
        today = date.today()

    cache_key = f"{entry.ticker}|{current_price_eur:.4f}|{today.isoformat()}|{entry.last_updated}"
    cached = cache_read(cache_key, namespace=_NS, max_age_seconds=60 * 30)
    if cached is not None and not cached.empty:
        try:
            row = cached.iloc[0].to_dict()
            return ReratingScore(
                ticker=row["ticker"],
                score=float(row["score"]),
                price_progress_pct=row.get("price_progress_pct"),
                milestones_hit_pct=float(row["milestones_hit_pct"]),
                days_since_entry=row.get("days_since_entry"),
                recommendation=row["recommendation"],
                rationale=list(row.get("rationale_csv", "").split("||")) if row.get("rationale_csv") else [],
            )
        except Exception:
            pass

    price_pct = _price_progress_pct(entry, current_price_eur)
    milestones_pct = _milestones_hit_pct(entry)
    days_since = _days_since_entry(entry, today)
    time_pct = _time_efficacy(days_since, milestones_pct, price_pct)

    # Weight components; missing price progress -> redistribute its weight onto milestones+time
    if price_pct is None:
        w_milestones = _W_MILESTONES + _W_PRICE * 0.5
        w_time = _W_TIME + _W_PRICE * 0.5
        composite = w_milestones * milestones_pct + w_time * time_pct
    else:
        composite = _W_PRICE * price_pct + _W_MILESTONES * milestones_pct + _W_TIME * time_pct
    composite = float(max(0.0, min(100.0, composite)))

    rec = _recommendation(composite, price_pct, days_since)

    rationale: list[str] = []
    if price_pct is not None:
        rationale.append(f"price progress {price_pct:.0f}%")
    else:
        rationale.append("no price target set")
    rationale.append(f"milestones hit {milestones_pct:.0f}%")
    if days_since is not None:
        rationale.append(f"{days_since}d since entry")
    rationale.append(f"composite {composite:.1f} -> {rec}")

    out = ReratingScore(
        ticker=entry.ticker,
        score=composite,
        price_progress_pct=price_pct,
        milestones_hit_pct=milestones_pct,
        days_since_entry=days_since,
        recommendation=rec,
        rationale=rationale,
    )

    try:
        import pandas as pd
        cache_df = pd.DataFrame([{
            "ticker": out.ticker,
            "score": out.score,
            "price_progress_pct": out.price_progress_pct,
            "milestones_hit_pct": out.milestones_hit_pct,
            "days_since_entry": out.days_since_entry,
            "recommendation": out.recommendation,
            "rationale_csv": "||".join(out.rationale),
        }])
        cache_write(cache_key, cache_df, namespace=_NS)
    except Exception as exc:
        log.debug("rerating cache write failed for %s: %s", entry.ticker, exc)

    return out
