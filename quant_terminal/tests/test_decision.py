"""Tests for Cluster 3 — Decision Support.

Covers:
  - conviction scoring (axis clamp + composite + grade)
  - suggested_weight (Kelly/4 cap)
  - var_contribution_sizing trims an over-weighted theme
  - risk_parity_weights sum-of-weights == 1.0
  - journal read/write round-trip on tmp_path
  - rerating score is bounded [0, 100]
  - compute_collar with monkeypatched fetch_chain
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

import numpy as np
import pandas as pd
import pytest

from src.common.schemas import (
    CollarQuote,
    ConvictionScore,
    DilutionAssessment,
    JournalEntry,
    JournalMilestone,
    OptionContract,
    OptionRight,
    RunwayAssessment,
)


# ---------------------------------------------------------------------------
# Conviction
# ---------------------------------------------------------------------------
def test_conviction_score_each_axis_in_1_5_and_composite():
    from src.decision.conviction import compute_position_score

    journal = JournalEntry(
        ticker="ASTS",
        thesis="MNO satcom direct-to-cell, scarce regulatory moat.",
        pre_mortem="If FCC denies AWS spectrum sharing -> thesis breaks.",
        price_target_eur=150.0,
        milestones=[
            JournalMilestone(date="2026-Q3", label="FCC approval", hit=False, weight=2.0),
            JournalMilestone(date="2026-Q4", label="first commercial revenue", hit=False, weight=1.5),
        ],
    )
    dilution = DilutionAssessment(
        ticker="ASTS", atm_active=False, dilution_score=2, rationale=["mild S-3"],
    )
    runway = RunwayAssessment(
        ticker="ASTS", cash_eur=500e6, quarterly_burn_eur=50e6,
        runway_quarters=10.0, period_end=date(2026, 3, 31), confidence="high",
    )
    liq = pd.Series({
        "ticker": "ASTS", "days_to_liq_10pct": 0.5,
        "slippage_bps_1pct_trade": 8.0, "weight_eur": 10_000.0,
    })

    score = compute_position_score(
        "ASTS",
        journal_entry=journal,
        liquidity_row=liq,
        dilution=dilution,
        runway=runway,
        next_catalyst_days=10,
    )
    assert isinstance(score, ConvictionScore)
    for axis in (score.thesis_quality, score.downside, score.liquidity, score.catalyst_proximity):
        assert 1 <= axis <= 5
    assert 1.0 <= score.composite <= 5.0
    assert score.grade in {"A", "B", "C", "D"}
    # Fully-populated thesis + good runway + tight liq + near catalyst -> at least a B
    assert score.composite >= 3.5


def test_conviction_score_degrades_without_inputs():
    from src.decision.conviction import compute_position_score
    s = compute_position_score("XYZ")
    assert 1.0 <= s.composite <= 5.0
    assert s.thesis_quality == 1     # no journal
    # downside falls to 3 with no dilution/runway data
    assert s.downside == 3
    # liquidity = 3 default
    assert s.liquidity == 3
    # no catalyst -> 1
    assert s.catalyst_proximity == 1


def test_suggested_weight_high_score_capped_at_max_single():
    from src.decision.conviction import suggested_weight

    high = ConvictionScore(
        ticker="X", thesis_quality=5, downside=5, liquidity=5,
        catalyst_proximity=5, composite=5.0, grade="A",
    )
    res = suggested_weight(high, current_weight=0.02, max_single_pct=0.12)
    assert 0.0 <= res["target_weight"] <= 0.12 + 1e-9
    # Kelly raw at 5/5: p = 0.7, kelly_full = 0.4, kelly/4 = 0.10 < 0.12 -> not capped
    assert res["target_weight"] > 0.05
    assert res["delta"] > 0


def test_suggested_weight_low_score_targets_zero():
    from src.decision.conviction import suggested_weight

    low = ConvictionScore(
        ticker="X", thesis_quality=1, downside=1, liquidity=1,
        catalyst_proximity=1, composite=1.0, grade="D",
    )
    res = suggested_weight(low, current_weight=0.05, max_single_pct=0.12)
    # composite 1 -> p = 0.3 -> kelly_full = -0.4 -> clamp 0
    assert res["target_weight"] == 0.0
    assert res["delta"] < 0


# ---------------------------------------------------------------------------
# VaR-contribution sizing
# ---------------------------------------------------------------------------
def _build_synthetic_returns(seed: int = 0) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Returns (returns_df, holdings_df). Theme 'Energy' is high-vol & heavy."""
    rng = np.random.default_rng(seed)
    n = 252
    idx = pd.date_range("2024-01-01", periods=n, freq="B")
    # Two assets in 'Energy' (high vol), two in 'Tech' (lower vol)
    rets = pd.DataFrame({
        "OIL1": rng.normal(0.0, 0.035, n),
        "OIL2": rng.normal(0.0, 0.030, n),
        "TECH1": rng.normal(0.0006, 0.012, n),
        "TECH2": rng.normal(0.0006, 0.010, n),
    }, index=idx)
    holdings = pd.DataFrame({
        "universe_key": ["OIL1", "OIL2", "TECH1", "TECH2"],
        "theme": ["Energy", "Energy", "Tech", "Tech"],
        "value_eur": [40_000.0, 30_000.0, 20_000.0, 10_000.0],
    })
    return rets, holdings


def test_var_contribution_sizing_reduces_overweight_theme():
    from src.decision.var_contribution_sizing import var_contribution_sizing

    class _PF:
        pass

    rets, holdings = _build_synthetic_returns(seed=42)
    pf = _PF()
    pf.holdings = holdings

    df = var_contribution_sizing(pf, rets, target_theme_pct=0.30, theme="Energy")
    assert not df.empty
    assert {"ticker", "in_theme", "suggested_trim_eur", "suggested_weight_eur"}.issubset(df.columns)
    energy_trims = df[df["in_theme"]]["suggested_trim_eur"]
    # Energy is the high-vol heavy theme -> should be trimmed (negative)
    assert (energy_trims <= 0).all()
    assert (energy_trims < 0).any()
    # Tech positions should never be trimmed (in_theme=False)
    tech_trims = df[~df["in_theme"]]["suggested_trim_eur"]
    assert (tech_trims == 0).all()


def test_var_contribution_sizing_noop_when_under_target():
    from src.decision.var_contribution_sizing import var_contribution_sizing

    class _PF:
        pass

    rets, holdings = _build_synthetic_returns(seed=42)
    pf = _PF()
    pf.holdings = holdings
    # 99% target -> nothing to trim
    df = var_contribution_sizing(pf, rets, target_theme_pct=0.99, theme="Energy")
    assert (df["suggested_trim_eur"] == 0).all()


# ---------------------------------------------------------------------------
# Risk-parity preview
# ---------------------------------------------------------------------------
def test_risk_parity_weights_sum_to_one_on_4_assets():
    from src.decision.risk_parity_preview import risk_parity_weights

    rng = np.random.default_rng(7)
    n = 252
    idx = pd.date_range("2024-01-01", periods=n, freq="B")
    rets = pd.DataFrame({
        f"A{i}": rng.normal(0.0, vol, n)
        for i, vol in enumerate([0.010, 0.020, 0.030, 0.040])
    }, index=idx)

    w = risk_parity_weights(rets, vol_target=0.01)
    assert len(w) == 4
    assert pytest.approx(w.sum(), abs=1e-9) == 1.0
    # Lowest-vol asset must get the highest weight
    assert w.idxmax() == "A0"
    assert w.idxmin() == "A3"


def test_risk_parity_weights_empty_returns_empty():
    from src.decision.risk_parity_preview import risk_parity_weights
    out = risk_parity_weights(pd.DataFrame())
    assert out.empty


# ---------------------------------------------------------------------------
# Journal store
# ---------------------------------------------------------------------------
def test_journal_round_trip(tmp_path, monkeypatch):
    monkeypatch.setenv("DECISION_JOURNAL_DIR", str(tmp_path))
    from src.decision import journal_store

    entry = JournalEntry(
        ticker="ASTS",
        thesis="MNO satcom direct-to-cell.",
        entry_rationale="FCC alignment + scarce moat",
        entry_price_eur=89.5,
        entry_date=date(2026, 1, 10),
        position_target_pct=0.08,
        price_target_eur=150.0,
        stop_loss_thesis_eur=50.0,
        stop_loss_technical_eur=65.0,
        milestones=[
            JournalMilestone(date="2026-Q3", label="FCC approval", hit=False, weight=2.0),
            JournalMilestone(date="2026-Q4", label="first revenue", hit=True, weight=1.5),
        ],
        pre_mortem="Regulatory denial -> thesis breaks.",
        catalyst_event_ids=["evt-001"],
        last_updated=date(2026, 5, 24),
    )
    path = journal_store.write_journal(entry)
    assert path.exists()

    read_back = journal_store.read_journal("ASTS")
    assert read_back is not None
    assert read_back.ticker == "ASTS"
    assert read_back.thesis == entry.thesis
    assert read_back.entry_price_eur == pytest.approx(89.5)
    assert read_back.price_target_eur == pytest.approx(150.0)
    assert read_back.stop_loss_thesis_eur == pytest.approx(50.0)
    assert len(read_back.milestones) == 2
    assert read_back.milestones[1].hit is True
    assert read_back.milestones[1].weight == pytest.approx(1.5)
    assert read_back.entry_date == date(2026, 1, 10)
    assert read_back.last_updated == date(2026, 5, 24)
    assert read_back.catalyst_event_ids == ["evt-001"]


def test_journal_list_summary(tmp_path, monkeypatch):
    monkeypatch.setenv("DECISION_JOURNAL_DIR", str(tmp_path))
    from src.decision import journal_store

    journal_store.write_journal(JournalEntry(
        ticker="ABC", thesis="Short test thesis.",
        pre_mortem="If x then bust.",
        milestones=[JournalMilestone(date="2026-Q1", label="m1", hit=True, weight=1.0)],
    ))
    journal_store.write_journal(JournalEntry(ticker="DEF", thesis=""))

    df = journal_store.list_journals()
    assert len(df) == 2
    assert set(df["ticker"]) == {"ABC", "DEF"}
    abc = df[df["ticker"] == "ABC"].iloc[0]
    assert abc["n_milestones"] == 1
    assert abc["n_milestones_hit"] == 1
    assert bool(abc["has_pre_mortem"])  # accept both numpy bool and python bool


def test_journal_read_missing_returns_none(tmp_path, monkeypatch):
    monkeypatch.setenv("DECISION_JOURNAL_DIR", str(tmp_path))
    from src.decision import journal_store
    assert journal_store.read_journal("DOES_NOT_EXIST") is None


# ---------------------------------------------------------------------------
# Rerating score
# ---------------------------------------------------------------------------
def test_compute_rerating_score_bounds():
    from src.decision.rerating_score import compute_rerating_score

    entry = JournalEntry(
        ticker="ASTS",
        entry_price_eur=90.0,
        price_target_eur=150.0,
        entry_date=date(2026, 1, 1),
        milestones=[
            JournalMilestone(date="2026-Q3", label="FCC", hit=True, weight=2.0),
            JournalMilestone(date="2026-Q4", label="rev", hit=False, weight=1.0),
        ],
    )
    today = date(2026, 5, 24)

    out = compute_rerating_score(entry, current_price_eur=120.0, today=today)
    assert 0.0 <= out.score <= 100.0
    assert out.ticker == "ASTS"
    assert out.recommendation in {"hold", "trim", "add", "exit", "review"}
    # 120/90 -> 30/60 = 50% price progress
    assert out.price_progress_pct is not None
    assert 49.0 <= out.price_progress_pct <= 51.0
    # 2/3 weight hit -> ~67%
    assert 65.0 <= out.milestones_hit_pct <= 68.0
    assert out.days_since_entry is not None
    assert out.days_since_entry > 0


def test_rerating_recommendation_trim_when_target_reached():
    from src.decision.rerating_score import compute_rerating_score

    entry = JournalEntry(
        ticker="X", entry_price_eur=100.0, price_target_eur=120.0,
        entry_date=date(2026, 1, 1),
        milestones=[
            JournalMilestone(date="2026-Q1", label="m1", hit=True, weight=1.0),
        ],
    )
    out = compute_rerating_score(entry, current_price_eur=120.0, today=date(2026, 6, 1))
    assert out.recommendation == "trim"


def test_rerating_no_target_uses_milestones_only():
    from src.decision.rerating_score import compute_rerating_score

    entry = JournalEntry(
        ticker="X",
        milestones=[JournalMilestone(date="2026-Q1", label="m1", hit=True, weight=1.0)],
        entry_date=date(2026, 1, 1),
    )
    out = compute_rerating_score(entry, current_price_eur=50.0, today=date(2026, 3, 1))
    assert out.price_progress_pct is None
    assert 0.0 <= out.score <= 100.0


# ---------------------------------------------------------------------------
# Collar cost
# ---------------------------------------------------------------------------
def _make_chain(spot: float, expiry: date) -> list[OptionContract]:
    """Build a synthetic chain centred on `spot` with sane mid prices."""
    contracts: list[OptionContract] = []
    snap = datetime(2026, 5, 24, 16, 0, 0)
    for strike in [80, 85, 90, 95, 100, 105, 110, 115, 120]:
        for right in (OptionRight.CALL, OptionRight.PUT):
            # crude payoff-style mid: max(intrinsic, 0) + small time value
            if right == OptionRight.CALL:
                mid = max(spot - strike, 0.0) + 2.0
            else:
                mid = max(strike - spot, 0.0) + 2.0
            contracts.append(OptionContract(
                underlying="X",
                symbol=f"X260620{right.value}{int(strike*1000):08d}",
                expiry=expiry,
                strike=float(strike),
                right=right,
                bid=mid * 0.95,
                ask=mid * 1.05,
                mid=mid,
                snapshot_ts=snap,
                source="yfinance",
            ))
    return contracts


def test_compute_collar_with_monkeypatched_chain(monkeypatch):
    from src.decision import hedge_cost

    expiry = date.today() + timedelta(days=90)
    chain = _make_chain(spot=100.0, expiry=expiry)

    def fake_fetch_chain(underlying: str, *, target_dte_window=(60, 120), **kw):
        return chain

    # Pass in the chain directly to avoid spot lookup as well
    quote = hedge_cost.compute_collar(
        "X", position_eur=10_000.0,
        dte_days=90, call_otm_pct=0.15, put_otm_pct=0.10,
        spot_eur=100.0, chain=chain,
    )
    assert isinstance(quote, CollarQuote)
    assert quote.ticker == "X"
    assert quote.expiry == expiry
    # Closest put strike to 100*(1-0.10)=90; closest call to 100*1.15=115
    assert quote.long_put_strike == pytest.approx(90.0)
    assert quote.short_call_strike == pytest.approx(115.0)
    # Should have computed sensible breakevens around spot
    assert quote.breakeven_low < quote.breakeven_high
    # Max loss is negative, max gain positive
    assert quote.max_loss_eur <= 0
    assert quote.max_gain_eur >= 0


def test_compute_collar_via_fetch_seam(monkeypatch):
    from src.decision import hedge_cost

    expiry = date.today() + timedelta(days=85)
    chain = _make_chain(spot=100.0, expiry=expiry)

    def fake_fetch(underlying, target_dte_window=(60, 120), **kw):
        assert underlying == "X"
        return chain

    quote = hedge_cost.compute_collar(
        "X", position_eur=10_000.0,
        spot_eur=100.0,
        fetch_chain=fake_fetch,
    )
    assert quote is not None
    assert quote.expiry == expiry


def test_compute_collar_no_chain_returns_none(monkeypatch):
    from src.decision import hedge_cost

    quote = hedge_cost.compute_collar(
        "X", position_eur=10_000.0, spot_eur=100.0,
        fetch_chain=lambda *a, **kw: [],
    )
    assert quote is None


def test_linear_alternatives_known_etp():
    from src.decision.hedge_cost import linear_futures_alternatives

    alts = linear_futures_alternatives("3OIL.L")
    assert isinstance(alts, list)
    assert any(a.get("hedge") == "USO" for a in alts)

    alts_unknown = linear_futures_alternatives("NOPE")
    assert alts_unknown == []
