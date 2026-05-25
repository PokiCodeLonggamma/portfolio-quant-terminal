"""Cluster 4 — Calendar / News tests.

Covers:
* `calendar_engine.earnings.fetch_earnings` builds CalendarEvents from a
  monkey-patched yfinance.Ticker.calendar.
* `calendar_engine.macro_events.load_2026` returns >= 30 events covering all
  six declared categories.
* `calendar_engine.implied_moves.implied_move` computes
  ``straddle_mid / spot`` when given a synthetic chain via the
  ``fetch_chain_fn`` injection point.
* `calendar_engine.historical_postearnings.post_earnings_history` returns
  a DataFrame with the required columns when yfinance is monkey-patched.
* `news.sentiment.score_headline` is positive on a clear-positive headline
  and negative on a clear-negative one.
* `news.aggregator.aggregate_news` produces a long-format DataFrame with
  ticker / day / count / sentiment when given a mock RSS feed.
* `news.rss_fetcher.fetch_news` parses a stub feedparser feed and respects
  the lookback window.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from src.calendar_engine import earnings as cal_earnings
from src.calendar_engine import macro_events
from src.calendar_engine import implied_moves
from src.calendar_engine import historical_postearnings
from src.calendar_engine import space_launches
from src.common.schemas import OptionContract, OptionRight
from src.news import aggregator as news_agg
from src.news import rss_fetcher
from src.news import sentiment


# ---------------------------------------------------------------------------
# earnings
# ---------------------------------------------------------------------------
class _FakeYFTicker:
    def __init__(self, calendar):
        self.calendar = calendar
        self.options = []


class _FakeYFModule:
    def __init__(self, calendars: dict[str, object]):
        self._calendars = calendars

    def Ticker(self, sym):
        return _FakeYFTicker(self._calendars.get(sym))


def test_fetch_earnings_builds_events_from_yfinance(monkeypatch):
    next_d = date.today() + timedelta(days=7)
    fake = _FakeYFModule({
        "ASTS": {"Earnings Date": next_d, "Earnings Average": 0.42},
        "IONQ": {"Earnings Date": next_d + timedelta(days=14), "Earnings Average": -0.31},
    })
    # patch the import inside earnings._yfinance_calendar
    import sys
    monkeypatch.setitem(sys.modules, "yfinance", fake)
    # also make sure the cache miss path runs deterministically
    monkeypatch.setattr(cal_earnings, "cache_read", lambda *a, **kw: None)
    written = {}
    monkeypatch.setattr(
        cal_earnings, "cache_write",
        lambda key, df, namespace=None: written.setdefault(key, df),
    )
    # block the Nasdaq scrape fallback so the test stays offline
    monkeypatch.setattr(cal_earnings, "_nasdaq_next_earnings", lambda t: None)
    events = cal_earnings.fetch_earnings(["ASTS", "IONQ", "UNKNOWN"])
    assert len(events) == 2
    tickers = {e.ticker for e in events}
    assert tickers == {"ASTS", "IONQ"}
    asts = next(e for e in events if e.ticker == "ASTS")
    assert asts.category == "earnings"
    assert asts.payload.get("eps_estimate") == pytest.approx(0.42)
    assert asts.source == "yfinance"


# ---------------------------------------------------------------------------
# macro_events
# ---------------------------------------------------------------------------
def test_macro_load_2026_returns_many_events():
    events = macro_events.load_2026()
    assert len(events) >= 30, f"expected >=30 macro events, got {len(events)}"
    categories = {e.category for e in events}
    # at minimum FOMC, ECB, CPI, EIA must be present
    assert {"fomc", "ecb", "cpi", "eia"} <= categories
    # required fields populated
    for ev in events[:10]:
        assert ev.event_id
        assert ev.start is not None
        assert ev.title
        assert ev.source == "manual"


def test_macro_categories_whitelist_filter():
    events = macro_events.load_macro_events(categories=["fomc"])
    assert events, "expected at least one FOMC event"
    assert {e.category for e in events} == {"fomc"}


# ---------------------------------------------------------------------------
# space launches
# ---------------------------------------------------------------------------
def test_load_launches_returns_events_with_payload():
    events = space_launches.load_launches()
    assert events, "launches yaml should yield ≥1 event"
    sample = events[0]
    assert sample.category == "launch"
    assert "operator" in sample.payload
    assert "vehicle" in sample.payload
    # at least one rocket-lab tagged via operator
    rkl = [e for e in events if e.ticker == "RKLB"]
    assert rkl, "expected at least one Rocket Lab launch (ticker=RKLB)"


# ---------------------------------------------------------------------------
# implied_moves
# ---------------------------------------------------------------------------
def _make_atm_chain(ticker: str, spot: float, expiry: date) -> list[OptionContract]:
    """Tiny 3-strike chain centred on `spot` with deterministic mids."""
    strikes = [spot - 5, spot, spot + 5]
    now = datetime.utcnow()
    chain: list[OptionContract] = []
    for k in strikes:
        # call/put mids configured so ATM straddle ≈ 5 (i.e. 5% implied move @ spot=100)
        if k == spot:
            cmid, pmid = 2.5, 2.5
        elif k < spot:
            cmid, pmid = 6.0, 1.0
        else:
            cmid, pmid = 1.0, 6.0
        chain.append(OptionContract(
            underlying=ticker, symbol=f"{ticker}-{int(k)}-C",
            expiry=expiry, strike=k, right=OptionRight.CALL,
            bid=cmid - 0.1, ask=cmid + 0.1, mid=cmid,
            snapshot_ts=now, source="yfinance",
        ))
        chain.append(OptionContract(
            underlying=ticker, symbol=f"{ticker}-{int(k)}-P",
            expiry=expiry, strike=k, right=OptionRight.PUT,
            bid=pmid - 0.1, ask=pmid + 0.1, mid=pmid,
            snapshot_ts=now, source="yfinance",
        ))
    return chain


def test_implied_move_computes_straddle_over_spot():
    spot = 100.0
    expiry = date.today() + timedelta(days=30)
    chain = _make_atm_chain("FAKE", spot, expiry)

    def _stub_fetch(ticker, **kwargs):
        return chain

    move = implied_moves.implied_move(
        "FAKE", dte_days=30, fetch_chain_fn=_stub_fetch, spot=spot,
    )
    assert move == pytest.approx(0.05, abs=1e-4)


def test_implied_move_empty_chain_returns_none():
    move = implied_moves.implied_move(
        "EMPTY", dte_days=30, fetch_chain_fn=lambda *a, **kw: [], spot=100.0,
    )
    assert move is None


# ---------------------------------------------------------------------------
# historical post-earnings
# ---------------------------------------------------------------------------
class _FakeYFTickerHist:
    def __init__(self, eps_df: pd.DataFrame, price_df: pd.DataFrame):
        self.earnings_dates = eps_df
        self._price_df = price_df

    def history(self, **kwargs):
        return self._price_df.copy()


class _FakeYFModuleHist:
    def __init__(self, tick):
        self._tick = tick

    def Ticker(self, sym):
        return self._tick


def test_post_earnings_history_returns_dataframe(monkeypatch):
    # Two earnings dates in the past — one beat, one miss.
    idx = pd.to_datetime([
        (date.today() - timedelta(days=120)).isoformat(),
        (date.today() - timedelta(days=30)).isoformat(),
    ])
    eps = pd.DataFrame({
        "EPS Estimate": [0.10, 0.20],
        "Reported EPS": [0.15, 0.05],
        "Surprise(%)": [50.0, -75.0],
    }, index=idx)

    # synthetic price history covering both dates +/-
    price_idx = pd.date_range(date.today() - timedelta(days=150), date.today(), freq="B")
    rng = np.random.default_rng(42)
    closes = 100 * (1 + rng.normal(0.0, 0.01, size=len(price_idx))).cumprod()
    price_df = pd.DataFrame({"Close": closes}, index=price_idx)

    tick = _FakeYFTickerHist(eps, price_df)
    yf_module = _FakeYFModuleHist(tick)

    df = historical_postearnings.post_earnings_history("ASTS", n_quarters=8, yf_module=yf_module)
    assert isinstance(df, pd.DataFrame)
    assert not df.empty
    assert {"quarter", "eps_estimate", "eps_actual", "eps_surprise_pct", "next_day_move_pct"} <= set(df.columns)


# ---------------------------------------------------------------------------
# sentiment
# ---------------------------------------------------------------------------
class TestSentiment:
    def test_positive_headline(self):
        score = sentiment.score_headline("ASTS stock beats estimates, raises guidance for FY26")
        assert score > 0.2, f"expected positive score, got {score}"

    def test_negative_headline(self):
        score = sentiment.score_headline("IONQ plunges 20% after earnings miss")
        assert score < -0.2, f"expected negative score, got {score}"

    def test_neutral_headline(self):
        score = sentiment.score_headline("Company holds annual shareholder meeting in Wilmington")
        assert -0.15 <= score <= 0.15

    def test_negation_flips_sign(self):
        pos = sentiment.score_headline("ASTS beats estimates")
        neg = sentiment.score_headline("ASTS did not beat estimates")
        assert pos > 0
        assert neg < 0, f"negated 'beat' should be negative, got {neg}"


# ---------------------------------------------------------------------------
# rss_fetcher
# ---------------------------------------------------------------------------
def _make_stub_feedparser(entries: list[dict]) -> object:
    """Return a minimal stand-in for the feedparser module."""
    feed_obj = SimpleNamespace(entries=entries)

    class StubFP:
        @staticmethod
        def parse(_url):
            return feed_obj

    return StubFP


def test_fetch_news_parses_stub_feed(monkeypatch, tmp_path):
    now = datetime.utcnow()
    entries = [
        {
            "title": "ASTS surges after analyst upgrade",
            "link": "http://example.com/1",
            "published_parsed": (now - timedelta(hours=2)).timetuple()[:9],
            "source": {"title": "MarketWatch"},
        },
        {
            "title": "ASTS plunges after earnings miss",
            "link": "http://example.com/2",
            "published_parsed": (now - timedelta(days=2)).timetuple()[:9],
            "source": {"title": "Reuters"},
        },
        {
            "title": "Ancient news outside lookback",
            "link": "http://example.com/old",
            "published_parsed": (now - timedelta(days=30)).timetuple()[:9],
            "source": {"title": "Forbes"},
        },
    ]
    # bypass cache
    monkeypatch.setattr(rss_fetcher, "cache_read", lambda *a, **kw: None)
    monkeypatch.setattr(rss_fetcher, "cache_write", lambda *a, **kw: None)

    df = rss_fetcher.fetch_news(
        "ASTS", lookback_days=7,
        feedparser_module=_make_stub_feedparser(entries),
    )
    assert isinstance(df, pd.DataFrame)
    assert len(df) == 2
    assert set(df["title"]) == {
        "ASTS surges after analyst upgrade",
        "ASTS plunges after earnings miss",
    }


# ---------------------------------------------------------------------------
# aggregator
# ---------------------------------------------------------------------------
def test_aggregate_news_returns_long_dataframe():
    def _fake_rss(ticker, lookback_days=7):
        now = datetime.utcnow()
        if ticker == "ASTS":
            return pd.DataFrame([
                {"ticker": "ASTS", "ts": now, "title": "ASTS surges after upgrade",
                 "link": "http://x/1", "source": "MW"},
                {"ticker": "ASTS", "ts": now - timedelta(hours=10),
                 "title": "ASTS beats estimates", "link": "http://x/2", "source": "Reuters"},
                {"ticker": "ASTS", "ts": now - timedelta(days=2),
                 "title": "ASTS plunges 10%", "link": "http://x/3", "source": "FT"},
            ])
        if ticker == "IONQ":
            return pd.DataFrame([
                {"ticker": "IONQ", "ts": now - timedelta(hours=1),
                 "title": "IONQ downgraded", "link": "http://x/i1", "source": "Forbes"},
            ])
        return pd.DataFrame()

    df = news_agg.aggregate_news(["ASTS", "IONQ"], lookback_days=7, rss_fetcher_fn=_fake_rss)
    assert isinstance(df, pd.DataFrame)
    assert not df.empty
    assert {"ticker", "day", "article_count", "mean_sentiment"} <= set(df.columns)
    # ASTS today should have 2 articles
    today = date.today()
    today_row = df[(df["ticker"] == "ASTS") & (df["day"] == today)]
    assert not today_row.empty
    assert int(today_row["article_count"].iloc[0]) == 2
