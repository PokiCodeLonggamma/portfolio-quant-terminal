"""Cluster 5 — Trading section tests.

Covers:
* Greeks vs known BS reference values + put-call parity + IV inverse recovery.
* delta_finder selects the contract closest to the target delta.
* compute_gex math on a synthetic 2-strike chain.
* Trade-ticket gating refuses IV-rank > 80, oversized debit, low OI.
* Journal add/close round-trip on tmp_path.
* squeeze_score components stay in [0, 100].
"""
from __future__ import annotations

import math
from datetime import date, datetime, timedelta

import pytest

from src.common.schemas import OptionContract, OptionRight, TradeTicket
from src.trading import greeks as G
from src.trading import journal as J
from src.trading.delta_finder import closest_delta
from src.trading.gex import compute_gex, gamma_flip_strike, negative_gamma_zone
from src.trading.squeeze_score import compute_squeeze_score
from src.trading.trade_ticket import build_ticket


# ---------------------------------------------------------------------------
# Greeks
# ---------------------------------------------------------------------------
class TestGreeks:
    def test_atm_call_delta_known_reference(self):
        # S=K=100, T=0.25, r=0.04, σ=0.20 → delta ≈ 0.54 (Hull).
        delta = G.bs_delta(100.0, 100.0, 0.25, 0.04, 0.20, OptionRight.CALL)
        assert 0.52 < delta < 0.56

    def test_put_call_parity(self):
        S, K, T, r, sigma = 100.0, 100.0, 0.25, 0.04, 0.20
        c = G.bs_price(S, K, T, r, sigma, OptionRight.CALL)
        p = G.bs_price(S, K, T, r, sigma, OptionRight.PUT)
        # C - P == S - K * exp(-rT)
        assert math.isclose(c - p, S - K * math.exp(-r * T), abs_tol=1e-6)

    def test_iv_solver_recovers_input_sigma(self):
        sigma = 0.35
        S, K, T, r = 100.0, 105.0, 0.5, 0.03
        price = G.bs_price(S, K, T, r, sigma, OptionRight.CALL)
        iv = G.bs_iv(price, S, K, T, r, OptionRight.CALL)
        assert iv is not None
        assert math.isclose(iv, sigma, abs_tol=1e-4)

    def test_iv_solver_returns_none_below_intrinsic(self):
        # A call cannot trade below intrinsic = max(0, S - K*exp(-rT))
        S, K, T, r = 100.0, 80.0, 0.5, 0.04
        intrinsic = S - K * math.exp(-r * T)
        assert G.bs_iv(intrinsic - 1.0, S, K, T, r, OptionRight.CALL) is None

    def test_gamma_is_positive_and_finite(self):
        g = G.bs_gamma(100.0, 100.0, 0.25, 0.04, 0.20)
        assert g > 0 and math.isfinite(g)

    def test_enrich_with_greeks_populates_missing_fields(self):
        c = OptionContract(
            underlying="ASTS",
            symbol="ASTS260620C00040000",
            expiry=date.today() + timedelta(days=30),
            strike=40.0,
            right=OptionRight.CALL,
            mid=2.0,
            snapshot_ts=datetime.utcnow(),
            source="yfinance",
        )
        out = G.enrich_with_greeks([c], spot=40.0)
        enriched = out[0]
        assert enriched.iv is not None and enriched.iv > 0
        assert enriched.delta is not None
        assert 0 <= enriched.delta <= 1


# ---------------------------------------------------------------------------
# delta_finder
# ---------------------------------------------------------------------------
class TestDeltaFinder:
    @staticmethod
    def _make_contract(strike: float, delta: float, *, right=OptionRight.CALL):
        return OptionContract(
            underlying="XLE",
            symbol=f"XLE260620C{int(strike * 1000):08d}",
            expiry=date.today() + timedelta(days=30),
            strike=strike,
            right=right,
            mid=1.0,
            bid=0.95, ask=1.05,
            delta=delta,
            gamma=0.02,
            iv=0.30,
            open_interest=500,
            snapshot_ts=datetime.utcnow(),
        )

    def test_picks_closest_delta(self):
        contracts = [
            self._make_contract(95, 0.10),
            self._make_contract(98, 0.20),
            self._make_contract(100, 0.27),     # ← closest to 0.25
            self._make_contract(105, 0.40),
        ]
        pick = closest_delta(contracts, target_delta=0.25)
        assert pick is not None
        assert pick.strike == 100

    def test_returns_none_when_outside_tolerance(self):
        contracts = [self._make_contract(95, 0.05), self._make_contract(120, 0.60)]
        assert closest_delta(contracts, target_delta=0.25, tolerance=0.05) is None


# ---------------------------------------------------------------------------
# GEX
# ---------------------------------------------------------------------------
class TestGex:
    @staticmethod
    def _two_strike_chain(spot: float = 100.0):
        # Call-heavy at K=95 (positive GEX), put-heavy at K=105 (negative GEX).
        snap = datetime.utcnow()
        exp = date.today() + timedelta(days=30)
        return [
            OptionContract(
                underlying="QQQ", symbol="QQQ_K95_C",
                expiry=exp, strike=95.0, right=OptionRight.CALL,
                gamma=0.03, open_interest=1000, snapshot_ts=snap,
            ),
            OptionContract(
                underlying="QQQ", symbol="QQQ_K95_P",
                expiry=exp, strike=95.0, right=OptionRight.PUT,
                gamma=0.01, open_interest=100, snapshot_ts=snap,
            ),
            OptionContract(
                underlying="QQQ", symbol="QQQ_K105_C",
                expiry=exp, strike=105.0, right=OptionRight.CALL,
                gamma=0.01, open_interest=100, snapshot_ts=snap,
            ),
            OptionContract(
                underlying="QQQ", symbol="QQQ_K105_P",
                expiry=exp, strike=105.0, right=OptionRight.PUT,
                gamma=0.03, open_interest=1000, snapshot_ts=snap,
            ),
        ]

    def test_compute_gex_math_on_synthetic_chain(self):
        spot = 100.0
        df = compute_gex(self._two_strike_chain(spot), spot=spot)
        assert {"strike", "net_gex_usd", "call_gex_usd", "put_gex_usd"} <= set(df.columns)
        assert len(df) == 2
        # K=95 should be positive net (calls dominate), K=105 should be negative.
        row95 = df.loc[df["strike"] == 95.0].iloc[0]
        row105 = df.loc[df["strike"] == 105.0].iloc[0]
        assert row95["net_gex_usd"] > 0
        assert row105["net_gex_usd"] < 0

    def test_gamma_flip_strike_zero_crossing_detected(self):
        spot = 100.0
        df = compute_gex(self._two_strike_chain(spot), spot=spot)
        flip = gamma_flip_strike(df)
        # Cumulative crosses zero between 95 and 105, so flip ∈ (95, 105].
        assert flip is not None
        assert 95.0 < flip <= 105.0

    def test_negative_gamma_zone(self):
        spot = 100.0
        df = compute_gex(self._two_strike_chain(spot), spot=spot)
        lo, hi = negative_gamma_zone(df, spot=spot, pct=0.10)
        assert lo == 105.0 and hi == 105.0


# ---------------------------------------------------------------------------
# Trade ticket gating
# ---------------------------------------------------------------------------
class _StubChain:
    """Fake chain factory delivering a single ATM-ish 0.25-delta call."""
    def __init__(self, *, oi: int = 500, mid: float = 0.50, delta: float = 0.26):
        self.oi = oi
        self.mid = mid
        self.delta = delta

    def __call__(self, ticker, *, target_dte_window=(14, 45)):
        return [OptionContract(
            underlying=ticker,
            symbol=f"{ticker}260620C00050000",
            expiry=date.today() + timedelta(days=30),
            strike=50.0,
            right=OptionRight.CALL,
            mid=self.mid, bid=self.mid - 0.05, ask=self.mid + 0.05,
            delta=self.delta, gamma=0.04, iv=0.35,
            open_interest=self.oi,
            snapshot_ts=datetime.utcnow(),
        )]


class TestTradeTicketGating:
    def test_refuses_high_iv_rank(self):
        t = build_ticket(
            ticker="ASTS", direction="LONG_CALL", target_delta=0.25,
            max_debit_eur=None, net_ev_eur=10_000.0,
            fetch_chain_fn=_StubChain(), iv_rank_fn=lambda _: 90.0,
        )
        assert any("IV rank" in r for r in t.refused_reasons)

    def test_refuses_oversized_debit(self):
        # mid 5.0 USD * 100 = 500 USD debit; if net EV is 100 EUR -> > 2% cap.
        t = build_ticket(
            ticker="ASTS", direction="LONG_CALL", target_delta=0.25,
            max_debit_eur=None, net_ev_eur=100.0,
            fetch_chain_fn=_StubChain(mid=5.0), iv_rank_fn=lambda _: 40.0,
        )
        assert any("Debit" in r for r in t.refused_reasons)

    def test_refuses_low_open_interest(self):
        t = build_ticket(
            ticker="ASTS", direction="LONG_CALL", target_delta=0.25,
            max_debit_eur=None, net_ev_eur=10_000.0,
            fetch_chain_fn=_StubChain(oi=10), iv_rank_fn=lambda _: 40.0,
        )
        assert any("Open interest" in r for r in t.refused_reasons)

    def test_clean_ticket_has_no_refused_reasons(self):
        t = build_ticket(
            ticker="ASTS", direction="LONG_CALL", target_delta=0.25,
            max_debit_eur=None, net_ev_eur=100_000.0,
            fetch_chain_fn=_StubChain(oi=500, mid=0.50, delta=0.26),
            iv_rank_fn=lambda _: 40.0,
        )
        assert t.refused_reasons == []
        assert t.actual_delta > 0
        assert t.contract_symbol.startswith("ASTS")


# ---------------------------------------------------------------------------
# Journal round-trip
# ---------------------------------------------------------------------------
class TestJournalRoundtrip:
    def test_add_then_close_persists(self, tmp_path, monkeypatch):
        J.set_journal_dir(tmp_path)
        # Patch FX so debit_eur math is deterministic
        monkeypatch.setattr("src.trading.journal.to_eur", lambda v, ccy: float(v))
        ticket = TradeTicket(
            ticker="ASTS", direction="LONG_CALL",
            expiry=date.today() + timedelta(days=30),
            strike=50.0, mid_eur=0.50, debit_eur=50.0,
            target_delta=0.25, actual_delta=0.26,
            breakeven=50.5, rr_1_to_1=1.0, pct_of_net_ev=0.005,
            refused_reasons=[],
            contract_symbol="ASTS260620C00050000",
            snapshot_ts=datetime.utcnow(),
        )
        trade_id = J.add_trade(ticket, qty=2)
        opens = J.list_open()
        assert len(opens) == 1
        assert opens["trade_id"].iloc[0] == trade_id
        assert opens["qty"].iloc[0] == 2

        closed = J.close_trade(trade_id, exit_credit_eur=80.0)
        assert closed.pnl_eur is not None
        # (80 - 50) * 2 = 60
        assert math.isclose(closed.pnl_eur, 60.0, abs_tol=1e-6)
        opens_after = J.list_open()
        assert len(opens_after) == 0

        all_rows = J.list_all()
        assert len(all_rows) == 1
        # Cleanup test override
        J.set_journal_dir(None)

    def test_refuses_to_journal_a_rejected_ticket(self, tmp_path):
        J.set_journal_dir(tmp_path)
        bad = TradeTicket(
            ticker="X", direction="LONG_CALL",
            expiry=date.today() + timedelta(days=30),
            strike=10.0, mid_eur=0.0, debit_eur=0.0,
            target_delta=0.25, actual_delta=0.0,
            breakeven=0.0, rr_1_to_1=0.0, pct_of_net_ev=0.0,
            refused_reasons=["IV rank too high"],
            contract_symbol="X260620C00010000",
            snapshot_ts=datetime.utcnow(),
        )
        with pytest.raises(ValueError):
            J.add_trade(bad)
        J.set_journal_dir(None)


# ---------------------------------------------------------------------------
# squeeze_score
# ---------------------------------------------------------------------------
def test_squeeze_score_components_in_range():
    snap = datetime.utcnow()
    exp = date.today() + timedelta(days=30)
    chain = [
        OptionContract(underlying="ASTS", symbol="ASTS_K48_C",
                       expiry=exp, strike=48.0, right=OptionRight.CALL,
                       gamma=0.02, open_interest=200, snapshot_ts=snap),
        OptionContract(underlying="ASTS", symbol="ASTS_K48_P",
                       expiry=exp, strike=48.0, right=OptionRight.PUT,
                       gamma=0.05, open_interest=2000, snapshot_ts=snap),
        OptionContract(underlying="ASTS", symbol="ASTS_K55_C",
                       expiry=exp, strike=55.0, right=OptionRight.CALL,
                       gamma=0.01, open_interest=8000, snapshot_ts=snap),
    ]
    payload = compute_squeeze_score(
        chain, spot=50.0,
        today_call_volume=10_000, mean_20d_call_volume=2_500,
        oi_5d_ago_total=4_000,
    )
    for k in ("score", "negative_gex_score", "call_volume_score", "otm_oi_score"):
        assert 0 <= payload[k] <= 100
    # Strong setup → score should not be trivially small
    assert payload["score"] > 10
