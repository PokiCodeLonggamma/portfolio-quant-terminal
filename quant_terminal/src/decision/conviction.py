"""Conviction scoring engine — module E.

A composite 1-5 score per position over four axes:

* **thesis_quality**   — quality of the user's documented thesis. We don't
  pretend to grade prose; instead we measure "is there a fact-anchored
  thesis on file?" — non-empty thesis + pre-mortem + ≥1 milestone +
  price_target -> 5; nothing -> 1.
* **downside**         — *inverse* of dilution risk (Cluster 1's
  `DilutionAssessment.dilution_score`) **and** cash-runway risk
  (`RunwayAssessment.runway_quarters`). Both 5 = great; both 1 = scary.
* **liquidity**        — derived from `days_to_liq_10pct` and
  `slippage_bps_1pct_trade`.  ≤1 day & <10 bps -> 5; >20d or >100bps -> 1.
* **catalyst_proximity** — inverse of days-to-next-catalyst. ≤21d -> 5;
  unknown / > 180d -> 1.

A weighted mean produces the composite (default weights in
``config/conviction_weights.yaml`` if present, otherwise 0.30/0.25/0.20/0.25).

`suggested_weight` maps the composite to a target portfolio weight, capped
at the risk-limit and Kelly/4-haircut against current weight.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

import pandas as pd
import yaml

from src.common.schemas import (
    ConvictionScore,
    DilutionAssessment,
    JournalEntry,
    RunwayAssessment,
)
from src.utils.cache import read as cache_read, write as cache_write
from src.utils.config import get_config
from src.utils.logging import get_logger

log = get_logger(__name__)

_NS = "decision_conviction"

# Default axis weights; can be overridden via config/conviction_weights.yaml
_DEFAULT_WEIGHTS: dict[str, float] = {
    "thesis_quality": 0.30,
    "downside": 0.25,
    "liquidity": 0.20,
    "catalyst_proximity": 0.25,
}


def _load_weights() -> dict[str, float]:
    cfg = get_config()
    path: Path = cfg.data_dir.parent / "config" / "conviction_weights.yaml"
    if not path.exists():
        return dict(_DEFAULT_WEIGHTS)
    try:
        with path.open("r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        if not isinstance(data, dict):
            raise ValueError("not a mapping")
        merged = dict(_DEFAULT_WEIGHTS)
        for k, v in data.items():
            if k in merged:
                merged[k] = float(v)
        # Re-normalise so the weights sum to 1
        s = sum(merged.values())
        if s <= 0:
            return dict(_DEFAULT_WEIGHTS)
        return {k: v / s for k, v in merged.items()}
    except Exception as exc:
        log.warning("conviction_weights.yaml unreadable, using defaults: %s", exc)
        return dict(_DEFAULT_WEIGHTS)


# ---------------------------------------------------------------------------
# Per-axis scorers
# ---------------------------------------------------------------------------
def _clamp_15(x: float | int) -> int:
    return int(max(1, min(5, int(round(x)))))


def score_thesis_quality(entry: JournalEntry | None) -> tuple[int, str]:
    """Score the journal completeness, not the prose itself."""
    if entry is None:
        return 1, "no journal entry"
    pts = 1
    bits: list[str] = []
    if (entry.thesis or "").strip():
        pts += 1
        bits.append("thesis")
    if entry.price_target_eur is not None and entry.price_target_eur > 0:
        pts += 1
        bits.append("price target")
    if (entry.pre_mortem or "").strip():
        pts += 1
        bits.append("pre-mortem")
    if entry.milestones:
        pts += 1
        bits.append(f"{len(entry.milestones)} milestones")
    pts = _clamp_15(pts)
    rationale = "journal: " + (", ".join(bits) if bits else "empty")
    return pts, rationale


def score_downside(
    dilution: DilutionAssessment | None,
    runway: RunwayAssessment | None,
) -> tuple[int, str]:
    """Downside risk -> 1 (scary) to 5 (rock-solid)."""
    pts = 5
    bits: list[str] = []
    if dilution is not None:
        ds = max(1, min(5, dilution.dilution_score))
        # Dilution 1 (low) -> +0; dilution 5 (severe) -> -3 (cap to 1)
        pts -= (ds - 1) * 3 // 4  # int rounding
        bits.append(f"dilution {ds}/5")
        if dilution.atm_active:
            pts -= 1
            bits.append("ATM live")
    if runway is not None:
        rq = runway.runway_quarters
        if rq == float("inf") or rq > 16:
            bits.append("runway: self-funding / >4y")
        elif rq < 2:
            pts -= 3
            bits.append(f"runway {rq:.1f}q")
        elif rq < 4:
            pts -= 2
            bits.append(f"runway {rq:.1f}q")
        elif rq < 8:
            pts -= 1
            bits.append(f"runway {rq:.1f}q")
        else:
            bits.append(f"runway {rq:.1f}q")
    if dilution is None and runway is None:
        return 3, "no SEC dilution / runway data"
    return _clamp_15(pts), "downside: " + "; ".join(bits)


def score_liquidity(liquidity_row: pd.Series | None) -> tuple[int, str]:
    """Liquidity score from days-to-liquidate + slippage."""
    if liquidity_row is None:
        return 3, "no liquidity data"
    try:
        days = float(liquidity_row.get("days_to_liq_10pct", float("nan")))
        bps = float(liquidity_row.get("slippage_bps_1pct_trade", float("nan")))
    except Exception:
        return 3, "malformed liquidity row"

    pts = 5
    bits: list[str] = []
    import math
    if not math.isfinite(days) or days > 20:
        pts -= 3
        bits.append(f"days-to-liq {'inf' if not math.isfinite(days) else f'{days:.1f}'}")
    elif days > 5:
        pts -= 2
        bits.append(f"days-to-liq {days:.1f}")
    elif days > 1:
        pts -= 1
        bits.append(f"days-to-liq {days:.1f}")
    else:
        bits.append(f"days-to-liq {days:.1f}")

    if not math.isfinite(bps) or bps > 100:
        pts -= 2
        bits.append(f"slip {'inf' if not math.isfinite(bps) else f'{bps:.0f}'}bps")
    elif bps > 50:
        pts -= 1
        bits.append(f"slip {bps:.0f}bps")
    else:
        bits.append(f"slip {bps:.0f}bps")
    return _clamp_15(pts), "liquidity: " + "; ".join(bits)


def score_catalyst_proximity(next_catalyst_days: int | None) -> tuple[int, str]:
    """Closer catalysts = higher score."""
    if next_catalyst_days is None:
        return 1, "no catalyst on calendar"
    d = int(next_catalyst_days)
    if d < 0:
        return 1, f"catalyst {abs(d)}d in past"
    if d <= 7:
        return 5, f"catalyst in {d}d"
    if d <= 21:
        return 4, f"catalyst in {d}d"
    if d <= 45:
        return 3, f"catalyst in {d}d"
    if d <= 90:
        return 2, f"catalyst in {d}d"
    return 1, f"catalyst {d}d out"


def _grade(composite: float) -> Literal["A", "B", "C", "D"]:
    if composite >= 4.25:
        return "A"
    if composite >= 3.25:
        return "B"
    if composite >= 2.25:
        return "C"
    return "D"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def compute_position_score(
    ticker: str,
    portfolio: Any | None = None,
    journal_entry: JournalEntry | None = None,
    liquidity_row: pd.Series | None = None,
    dilution: DilutionAssessment | None = None,
    runway: RunwayAssessment | None = None,
    next_catalyst_days: int | None = None,
) -> ConvictionScore:
    """Aggregate a 4-axis conviction score for ``ticker``.

    Every input is optional; the score degrades gracefully (defaults to a
    centred 3/5 when a signal is missing).
    """
    t = (ticker or "").upper().strip()
    if not t:
        raise ValueError("ticker is required")
    # portfolio is accepted for future enrichment (e.g. theme cap awareness)
    _ = portfolio

    cache_key = (
        f"{t}|"
        f"j={journal_entry.last_updated if journal_entry else 'na'}|"
        f"d={dilution.dilution_score if dilution else 'na'}|"
        f"r={runway.runway_quarters if runway else 'na'}|"
        f"l={float(liquidity_row.get('days_to_liq_10pct', 'nan')) if liquidity_row is not None else 'na'}|"
        f"c={next_catalyst_days}"
    )
    cached = cache_read(cache_key, namespace=_NS, max_age_seconds=60 * 60)
    if cached is not None and not cached.empty:
        try:
            row = cached.iloc[0].to_dict()
            return ConvictionScore(
                ticker=row["ticker"],
                thesis_quality=int(row["thesis_quality"]),
                downside=int(row["downside"]),
                liquidity=int(row["liquidity"]),
                catalyst_proximity=int(row["catalyst_proximity"]),
                composite=float(row["composite"]),
                grade=row["grade"],
                rationale=list(row.get("rationale_csv", "").split("||")) if row.get("rationale_csv") else [],
            )
        except Exception:
            pass

    tq, r_tq = score_thesis_quality(journal_entry)
    dn, r_dn = score_downside(dilution, runway)
    lq, r_lq = score_liquidity(liquidity_row)
    cp, r_cp = score_catalyst_proximity(next_catalyst_days)

    w = _load_weights()
    composite = (
        w["thesis_quality"] * tq
        + w["downside"] * dn
        + w["liquidity"] * lq
        + w["catalyst_proximity"] * cp
    )
    composite = float(max(1.0, min(5.0, composite)))

    out = ConvictionScore(
        ticker=t,
        thesis_quality=tq,
        downside=dn,
        liquidity=lq,
        catalyst_proximity=cp,
        composite=composite,
        grade=_grade(composite),
        rationale=[r_tq, r_dn, r_lq, r_cp],
    )

    try:
        cache_df = pd.DataFrame([{
            "ticker": out.ticker,
            "thesis_quality": out.thesis_quality,
            "downside": out.downside,
            "liquidity": out.liquidity,
            "catalyst_proximity": out.catalyst_proximity,
            "composite": out.composite,
            "grade": out.grade,
            "rationale_csv": "||".join(out.rationale),
        }])
        cache_write(cache_key, cache_df, namespace=_NS)
    except Exception as exc:
        log.debug("conviction cache write failed for %s: %s", t, exc)

    return out


def score_portfolio(
    portfolio: Any,
    *,
    dilutions: dict[str, DilutionAssessment] | None = None,
    runways: dict[str, RunwayAssessment] | None = None,
    liquidity_df: pd.DataFrame | None = None,
    journals: dict[str, JournalEntry] | None = None,
    next_catalysts: dict[str, int] | None = None,
) -> pd.DataFrame:
    """Score every position in the portfolio. Returns one row per ticker.

    Columns: ticker, thesis_quality, downside, liquidity,
    catalyst_proximity, composite, grade, rationale.
    """
    if portfolio is None or not hasattr(portfolio, "universe_keys"):
        return pd.DataFrame(columns=[
            "ticker", "thesis_quality", "downside", "liquidity",
            "catalyst_proximity", "composite", "grade", "rationale",
        ])
    rows: list[dict[str, Any]] = []
    liq_indexed: pd.DataFrame | None = None
    if liquidity_df is not None and not liquidity_df.empty and "ticker" in liquidity_df.columns:
        liq_indexed = liquidity_df.set_index("ticker")
    for t in portfolio.universe_keys:
        liq_row = liq_indexed.loc[t] if (liq_indexed is not None and t in liq_indexed.index) else None
        score = compute_position_score(
            t,
            portfolio=portfolio,
            journal_entry=(journals or {}).get(t),
            liquidity_row=liq_row,
            dilution=(dilutions or {}).get(t),
            runway=(runways or {}).get(t),
            next_catalyst_days=(next_catalysts or {}).get(t),
        )
        rows.append({
            "ticker": score.ticker,
            "thesis_quality": score.thesis_quality,
            "downside": score.downside,
            "liquidity": score.liquidity,
            "catalyst_proximity": score.catalyst_proximity,
            "composite": score.composite,
            "grade": score.grade,
            "rationale": " ; ".join(score.rationale),
        })
    if not rows:
        return pd.DataFrame(columns=[
            "ticker", "thesis_quality", "downside", "liquidity",
            "catalyst_proximity", "composite", "grade", "rationale",
        ])
    return pd.DataFrame(rows).sort_values("composite", ascending=False).reset_index(drop=True)


# ---------------------------------------------------------------------------
# Sizing — Kelly/4 haircut driven by conviction composite
# ---------------------------------------------------------------------------
def suggested_weight(
    score: ConvictionScore,
    current_weight: float,
    max_single_pct: float | None = None,
    *,
    kelly_haircut: float = 0.25,
) -> dict[str, Any]:
    """Map a ConvictionScore to a target portfolio weight (0..1).

    The composite is interpreted as an "edge" on a 1..5 scale; we transform
    to a probability-of-win ``p = 0.5 + 0.1 * (composite - 3)`` in [0.3, 0.7],
    apply Kelly at 1:1 odds, then a 1/4 haircut. The result is clamped to
    ``[0, max_single_pct]``.

    Returns a dict ``{target_weight, kelly_raw, current_weight, delta,
    rationale, capped}``.
    """
    if max_single_pct is None:
        try:
            max_single_pct = float(get_config().risk_limits.get("position", {}).get(
                "max_single_position_pct", 0.12,
            ))
        except Exception:
            max_single_pct = 0.12

    # p in [0.3, 0.7] as score moves 1->5
    p = 0.5 + 0.1 * (float(score.composite) - 3.0)
    p = max(0.05, min(0.95, p))
    # Kelly at odds 1:1 -> f* = 2p - 1
    kelly_full = max(0.0, 2.0 * p - 1.0)
    kelly_quarter = kelly_full * float(kelly_haircut)
    target = min(float(max_single_pct), kelly_quarter)
    target = max(0.0, target)

    delta = target - float(current_weight or 0.0)
    capped = kelly_quarter > max_single_pct + 1e-9

    rationale = [
        f"composite {score.composite:.2f} ({score.grade})",
        f"p_win={p:.2f}, kelly_full={kelly_full:.2%}, kelly/4={kelly_quarter:.2%}",
        f"max_single={max_single_pct:.2%}{' (capped)' if capped else ''}",
        f"current {float(current_weight or 0.0):.2%} -> target {target:.2%} (Δ {delta:+.2%})",
    ]
    return {
        "target_weight": float(target),
        "kelly_raw": float(kelly_quarter),
        "current_weight": float(current_weight or 0.0),
        "delta": float(delta),
        "capped": bool(capped),
        "rationale": rationale,
    }
