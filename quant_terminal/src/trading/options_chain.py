"""Options chain fetcher — Alpaca primary, yfinance silent fallback.

Resolution order
----------------
1. **Alpaca** `OptionHistoricalDataClient.get_option_chain()` — ships greeks &
   IV inline (when the user's data subscription supports it). Only used when
   credentials are set AND a universe-mapped `alpaca` ticker exists.
2. **yfinance** `Ticker(sym).option_chain(expiry)` — free, but no greeks;
   we then call `greeks.enrich_with_greeks(...)` to populate them via BS-inverse.

Cache
-----
`namespace="options_chain"`, **30-minute TTL** as per the brief. Per-expiry
caching keeps the granularity small (one chain per (ticker, expiry, source)).

Public API
----------
* `fetch_chain(underlying, expiry=None, *, target_dte_window=(14,45))`
* `expiries_available(ticker)`
* `chain_dataframe(contracts)`
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

import math

import pandas as pd

from src.common.schemas import OptionContract, OptionRight
from src.data.loaders import load_one
from src.trading.greeks import enrich_with_greeks
from src.utils.cache import read as cache_read, write as cache_write
from src.utils.config import get_config
from src.utils.logging import get_logger

log = get_logger(__name__)

_CACHE_TTL_SECONDS = 30 * 60          # 30 minutes
_CACHE_NS = "options_chain"
_RISK_FREE = 0.04                     # used by BS inverse on yfinance fallback

# Data-quality threshold: if Alpaca returns a chain but more than this share
# of contracts lack BOTH a usable mid AND a delta, we treat the chain as
# corrupted and fall back to yfinance.
_ALPACA_QUALITY_THRESHOLD = 0.7


def _nan_to_none(v: Any) -> Any:
    """Coerce float NaN/inf to None so pydantic + parquet round-trips stay clean."""
    if v is None:
        return None
    if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
        return None
    try:
        if pd.isna(v):
            return None
    except (TypeError, ValueError):
        pass
    return v


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _safe_spot(underlying: str) -> float | None:
    """Best-effort spot fetch via existing loader (Alpaca + yf fallback)."""
    try:
        end = datetime.utcnow()
        start = end - timedelta(days=10)
        series = load_one(underlying, start, end)
        if series is not None and not series.empty:
            return float(series.dropna().iloc[-1])
    except Exception as exc:
        log.debug("spot lookup via loader failed for %s: %s", underlying, exc)
    # yfinance fast_info fallback — works for almost any US-listed symbol.
    try:
        import yfinance as yf
        cfg = get_config()
        yf_sym = cfg.yfinance_symbol(underlying) or underlying
        tk = yf.Ticker(yf_sym)
        fi = getattr(tk, "fast_info", None)
        candidates = []
        if fi is not None:
            for attr in ("last_price", "lastPrice", "regular_market_price"):
                try:
                    candidates.append(getattr(fi, attr, None))
                except Exception:
                    pass
            if hasattr(fi, "get"):
                for k in ("last_price", "lastPrice", "regularMarketPrice"):
                    try:
                        candidates.append(fi.get(k))
                    except Exception:
                        pass
        for c in candidates:
            if c is None:
                continue
            try:
                px = float(c)
            except (TypeError, ValueError):
                continue
            if px > 0:
                return px
    except Exception as exc:
        log.debug("yfinance fast_info spot fallback failed for %s: %s", underlying, exc)
    return None


def _to_record(c: OptionContract) -> dict[str, Any]:
    """Pydantic -> flat dict suitable for parquet serialisation."""
    d = c.model_dump()
    d["expiry"] = c.expiry.isoformat()
    d["snapshot_ts"] = c.snapshot_ts.isoformat()
    d["right"] = c.right.value
    return d


def _from_record(rec: dict[str, Any]) -> OptionContract:
    rec = {k: _nan_to_none(v) for k, v in rec.items()}
    rec["expiry"] = date.fromisoformat(str(rec["expiry"]))
    rec["snapshot_ts"] = datetime.fromisoformat(str(rec["snapshot_ts"]))
    if isinstance(rec.get("right"), str):
        rec["right"] = OptionRight(rec["right"])
    # Optional integer-ish fields: pydantic refuses None-> int but we want None
    for opt_int in ("open_interest", "volume"):
        if rec.get(opt_int) is not None:
            try:
                rec[opt_int] = int(rec[opt_int])
            except (TypeError, ValueError):
                rec[opt_int] = None
    return OptionContract(**rec)


def _quality_ok(contracts: list[OptionContract]) -> bool:
    """Heuristic: at least 30% of contracts must have a usable price+greek,
    AND the chain as a whole must have at least *some* open interest — without
    OI, downstream GEX/max-pain/PC-ratio are degenerate so we'd rather pay
    the yfinance round-trip for a chain that actually has the data.
    """
    if not contracts:
        return False
    usable = sum(
        1 for c in contracts
        if (c.mid is not None or c.last is not None or c.bid is not None)
        and c.delta is not None
    )
    ratio = usable / len(contracts)
    if ratio < (1.0 - _ALPACA_QUALITY_THRESHOLD):
        return False
    # Need at least 5 contracts with non-zero OI for GEX to produce anything.
    oi_count = sum(1 for c in contracts if c.open_interest and c.open_interest > 0)
    return oi_count >= 5


def _in_dte_window(expiry: date, window: tuple[int, int]) -> bool:
    dte = (expiry - date.today()).days
    return window[0] <= dte <= window[1]


# ---------------------------------------------------------------------------
# Alpaca path
# ---------------------------------------------------------------------------
def _fetch_alpaca(
    underlying: str, expiry: date | None, target_dte_window: tuple[int, int],
) -> list[OptionContract]:
    cfg = get_config()
    if not cfg.secrets.has_alpaca:
        return []
    alpaca_sym = cfg.alpaca_symbol(underlying) or underlying
    try:
        from alpaca.data.historical.option import OptionHistoricalDataClient
        from alpaca.data.requests import OptionChainRequest
    except ImportError:
        log.debug("alpaca-py options module unavailable")
        return []
    try:
        client = OptionHistoricalDataClient(cfg.secrets.alpaca_key_id, cfg.secrets.alpaca_secret_key)
        kwargs: dict[str, Any] = {"underlying_symbol": alpaca_sym}
        if expiry is not None:
            kwargs["expiration_date"] = expiry
        req = OptionChainRequest(**kwargs)
        snap = client.get_option_chain(req)
    except Exception as exc:
        log.info("Alpaca options chain failed for %s: %s -- falling back to yfinance", underlying, exc)
        return []

    # The SDK returns dict[str, OptionsSnapshot]
    contracts: list[OptionContract] = []
    now = datetime.utcnow()
    items = snap.items() if hasattr(snap, "items") else []
    for occ_symbol, s in items:
        try:
            # OCC parse: AAPL250620C00040000 -> expiry 25-06-20, C, strike 40
            exp_str, right_char, strike_str = occ_symbol[-15:-9], occ_symbol[-9], occ_symbol[-8:]
            yy, mm, dd = int("20" + exp_str[:2]), int(exp_str[2:4]), int(exp_str[4:6])
            exp_d = date(yy, mm, dd)
            strike = int(strike_str) / 1000.0
            right = OptionRight.CALL if right_char.upper() == "C" else OptionRight.PUT
        except Exception:
            continue
        if expiry is None and not _in_dte_window(exp_d, target_dte_window):
            continue

        quote = getattr(s, "latest_quote", None)
        trade = getattr(s, "latest_trade", None)
        greeks = getattr(s, "greeks", None)
        iv = getattr(s, "implied_volatility", None)
        bid = getattr(quote, "bid_price", None) if quote else None
        ask = getattr(quote, "ask_price", None) if quote else None
        last = getattr(trade, "price", None) if trade else None
        mid = 0.5 * (bid + ask) if (bid is not None and ask is not None and bid > 0 and ask > 0) else None

        contracts.append(OptionContract(
            underlying=underlying,
            symbol=occ_symbol,
            expiry=exp_d,
            strike=strike,
            right=right,
            bid=bid, ask=ask, last=last, mid=mid,
            iv=iv,
            delta=getattr(greeks, "delta", None) if greeks else None,
            gamma=getattr(greeks, "gamma", None) if greeks else None,
            theta=getattr(greeks, "theta", None) if greeks else None,
            vega=getattr(greeks, "vega", None) if greeks else None,
            open_interest=getattr(s, "open_interest", None),
            volume=getattr(trade, "size", None) if trade else None,
            snapshot_ts=now,
            source="alpaca",
        ))
    return contracts


# ---------------------------------------------------------------------------
# yfinance path
# ---------------------------------------------------------------------------
def _build_occ_symbol(underlying: str, expiry: date, right: OptionRight, strike: float) -> str:
    """OCC 21-char symbol e.g. ASTS250620C00040000."""
    root = underlying.upper().ljust(6)[:6].rstrip()
    yymmdd = expiry.strftime("%y%m%d")
    r = "C" if right == OptionRight.CALL else "P"
    strike_int = int(round(strike * 1000))
    return f"{root}{yymmdd}{r}{strike_int:08d}"


def _fetch_yfinance(
    underlying: str, expiry: date | None, target_dte_window: tuple[int, int], spot: float | None,
) -> list[OptionContract]:
    cfg = get_config()
    yf_sym = cfg.yfinance_symbol(underlying) or underlying
    try:
        import yfinance as yf
    except ImportError:
        log.error("yfinance not installed; cannot resolve %s", underlying)
        return []

    try:
        tk = yf.Ticker(yf_sym)
        all_expiries = [date.fromisoformat(e) for e in (tk.options or [])]
    except Exception as exc:
        log.warning("yfinance expiries lookup failed for %s: %s", yf_sym, exc)
        return []

    if expiry is not None:
        targets = [expiry] if expiry in all_expiries else []
    else:
        targets = [e for e in all_expiries if _in_dte_window(e, target_dte_window)]
        # If the window matches nothing, pick the soonest expiry that lies after
        # the window's lower bound — better degraded behaviour than empty chain.
        if not targets and all_expiries:
            future = [e for e in all_expiries if (e - date.today()).days >= target_dte_window[0]]
            if future:
                targets = [min(future)]

    contracts: list[OptionContract] = []
    now = datetime.utcnow()
    for exp in targets:
        try:
            chain = tk.option_chain(exp.isoformat())
        except Exception as exc:
            log.warning("yfinance chain for %s @ %s failed: %s", yf_sym, exp, exc)
            continue
        for side, frame in (("C", chain.calls), ("P", chain.puts)):
            if frame is None or frame.empty:
                continue
            right = OptionRight.CALL if side == "C" else OptionRight.PUT
            for _, row in frame.iterrows():
                strike = float(row.get("strike", 0.0))
                if strike <= 0:
                    continue
                bid = float(row["bid"]) if pd.notna(row.get("bid")) else None
                ask = float(row["ask"]) if pd.notna(row.get("ask")) else None
                last = float(row["lastPrice"]) if pd.notna(row.get("lastPrice")) else None
                iv = float(row["impliedVolatility"]) if pd.notna(row.get("impliedVolatility")) else None
                oi = int(row["openInterest"]) if pd.notna(row.get("openInterest")) else None
                vol = int(row["volume"]) if pd.notna(row.get("volume")) else None
                mid = (
                    0.5 * (bid + ask) if (bid is not None and ask is not None and bid > 0 and ask > 0)
                    else None
                )
                occ = str(row.get("contractSymbol") or _build_occ_symbol(underlying, exp, right, strike))
                contracts.append(OptionContract(
                    underlying=underlying,
                    symbol=occ, expiry=exp, strike=strike, right=right,
                    bid=bid, ask=ask, last=last, mid=mid,
                    iv=iv,
                    open_interest=oi, volume=vol,
                    snapshot_ts=now, source="yfinance",
                ))

    # Populate greeks (yfinance ships only IV, not delta/gamma/...)
    if contracts and spot is not None and spot > 0:
        contracts = enrich_with_greeks(contracts, spot=spot, r=_RISK_FREE)
    return contracts


# ---------------------------------------------------------------------------
# OI merger
# ===========
# Alpaca's Data-API `OptionsSnapshot` does NOT expose `open_interest` (only
# greeks + IV + quote/trade). When Alpaca powers our chain we end up with 0 OI
# for every contract, which silently kills GEX / max-pain / P/C-ratio.
#
# Resolution order, Alpaca-first per user preference:
#   1. **Alpaca Trading-API** `GET /v2/options/contracts` — the trading-side
#      `OptionContract` model carries `open_interest`. One call per expiry
#      yields OI for the entire expiry strip.
#   2. **yfinance** — last-resort fallback when no Alpaca creds / Trading API
#      errors out. Same merge-by-symbol pattern.
#
# Both mergers preserve all existing fields and ONLY patch contracts whose
# `open_interest` is None or 0.
# ---------------------------------------------------------------------------
def _missing_oi_ratio(contracts: list[OptionContract]) -> float:
    if not contracts:
        return 0.0
    missing = sum(1 for c in contracts if not c.open_interest)
    return missing / len(contracts)


def _merge_oi_from_alpaca_trading(
    underlying: str, contracts: list[OptionContract],
) -> list[OptionContract]:
    """Pull OI from the Alpaca Trading API and merge by symbol."""
    if not contracts:
        return contracts
    cfg = get_config()
    if not cfg.secrets.has_alpaca:
        return contracts
    try:
        from alpaca.trading.client import TradingClient
        from alpaca.trading.requests import GetOptionContractsRequest
    except ImportError:
        return contracts
    try:
        # paper=True because options OI metadata is identical on paper/live and
        # the user runs paper by default; the endpoint accepts either.
        client = TradingClient(
            cfg.secrets.alpaca_key_id, cfg.secrets.alpaca_secret_key, paper=True,
        )
    except Exception as exc:
        log.debug("alpaca trading client init failed: %s", exc)
        return contracts

    alpaca_sym = cfg.alpaca_symbol(underlying) or underlying
    needed_expiries = sorted({c.expiry for c in contracts if c.expiry is not None})

    oi_map: dict[str, int] = {}
    for exp in needed_expiries:
        try:
            req = GetOptionContractsRequest(
                underlying_symbols=[alpaca_sym],
                expiration_date=exp,
                limit=1000,
            )
            resp = client.get_option_contracts(req)
            # alpaca-py returns OptionContractsResponse with .option_contracts list
            rows = getattr(resp, "option_contracts", None) or []
            for row in rows:
                sym = getattr(row, "symbol", None)
                oi = getattr(row, "open_interest", None)
                if sym and oi is not None:
                    try:
                        oi_map[str(sym)] = int(float(oi))
                    except (TypeError, ValueError):
                        pass
        except Exception as exc:
            log.debug("alpaca trading OI fetch for %s @ %s failed: %s",
                      alpaca_sym, exp, exc)
            continue

    if not oi_map:
        return contracts

    patched = 0
    out: list[OptionContract] = []
    for c in contracts:
        if (c.open_interest is None or c.open_interest == 0) and c.symbol in oi_map:
            patched += 1
            out.append(c.model_copy(update={"open_interest": oi_map[c.symbol]}))
        else:
            out.append(c)
    if patched:
        log.info("alpaca trading OI merge: patched %d/%d contracts on %s",
                 patched, len(contracts), underlying)
    return out


def _merge_oi_from_yfinance(
    underlying: str, contracts: list[OptionContract],
) -> list[OptionContract]:
    if not contracts:
        return contracts
    needed_expiries = sorted({c.expiry for c in contracts if c.expiry is not None})
    if not needed_expiries:
        return contracts
    cfg = get_config()
    yf_sym = cfg.yfinance_symbol(underlying) or underlying
    try:
        import yfinance as yf
        tk = yf.Ticker(yf_sym)
    except Exception as exc:
        log.debug("yfinance OI merge: ticker init failed for %s: %s", yf_sym, exc)
        return contracts

    # Build {OCC_symbol: open_interest} index from yfinance.
    oi_map: dict[str, int] = {}
    vol_map: dict[str, int] = {}
    for exp in needed_expiries:
        try:
            chain = tk.option_chain(exp.isoformat())
        except Exception as exc:
            log.debug("yfinance OI merge: chain @ %s failed: %s", exp, exc)
            continue
        for frame in (chain.calls, chain.puts):
            if frame is None or frame.empty or "contractSymbol" not in frame.columns:
                continue
            for _, row in frame.iterrows():
                sym = str(row.get("contractSymbol", "")).strip()
                if not sym:
                    continue
                oi_raw = row.get("openInterest")
                if pd.notna(oi_raw):
                    try:
                        oi_map[sym] = int(oi_raw)
                    except (TypeError, ValueError):
                        pass
                vol_raw = row.get("volume")
                if pd.notna(vol_raw):
                    try:
                        vol_map[sym] = int(vol_raw)
                    except (TypeError, ValueError):
                        pass

    if not oi_map:
        log.debug("yfinance OI merge: no OI rows recovered for %s", underlying)
        return contracts

    # Patch contracts that lack OI; also fill volume opportunistically.
    patched = 0
    out: list[OptionContract] = []
    for c in contracts:
        upd: dict[str, Any] = {}
        if (c.open_interest is None or c.open_interest == 0) and c.symbol in oi_map:
            upd["open_interest"] = oi_map[c.symbol]
        if (c.volume is None or c.volume == 0) and c.symbol in vol_map:
            upd["volume"] = vol_map[c.symbol]
        if upd:
            patched += 1
            out.append(c.model_copy(update=upd))
        else:
            out.append(c)
    if patched:
        log.info("yfinance OI merge: patched %d/%d contracts on %s",
                 patched, len(contracts), underlying)
    return out


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def fetch_chain(
    underlying: str,
    expiry: date | None = None,
    *,
    target_dte_window: tuple[int, int] = (14, 45),
) -> list[OptionContract]:
    """Return option contracts for `underlying`, Alpaca first then yfinance.

    Parameters
    ----------
    underlying           : universe_key (e.g. "ASTS").
    expiry               : specific expiration date or None for the DTE window.
    target_dte_window    : inclusive (min, max) days-to-expiry filter (default
                           14-45 days as per user's trading style).
    """
    cache_key = f"{underlying}|{expiry.isoformat() if expiry else 'window'}|{target_dte_window}"
    cached = cache_read(cache_key, namespace=_CACHE_NS, max_age_seconds=_CACHE_TTL_SECONDS)
    if cached is not None and not cached.empty:
        try:
            return [_from_record(rec) for rec in cached.to_dict(orient="records")]
        except Exception as exc:
            log.warning("cache deserialize failed for %s: %s", cache_key, exc)

    contracts = _fetch_alpaca(underlying, expiry, target_dte_window)
    # If Alpaca returned junk (no greeks, no prices for most contracts — common
    # on illiquid small-caps like ASTS / IONQ paper data), retry via yfinance
    # and merge greeks via BS-inverse.
    spot = _safe_spot(underlying)
    if not contracts or not _quality_ok(contracts):
        if contracts:
            log.info("Alpaca chain for %s low-quality (%d contracts) → yfinance fallback",
                     underlying, len(contracts))
        yf_contracts = _fetch_yfinance(underlying, expiry, target_dte_window, spot)
        if yf_contracts:
            contracts = yf_contracts

    # Final greek-completion pass: even when Alpaca passed quality (delta+mid OK)
    # it commonly ships chains without `gamma`. compute_gex would then silently
    # skip every contract. Run BS-inverse to fill the gaps when a spot is known.
    if contracts and spot is not None and spot > 0:
        missing_gamma = any(c.gamma is None and c.iv is not None for c in contracts)
        if missing_gamma:
            contracts = enrich_with_greeks(contracts, spot=spot, r=_RISK_FREE)

    # OI merger: Alpaca's Data-API snapshot drops `open_interest`, killing GEX.
    # Try Alpaca's Trading-API first (native, no extra dependency), then fall
    # back to yfinance if Alpaca trading is unavailable. Triggers only when
    # the existing OI coverage is poor (>50% of contracts missing OI).
    if contracts and _missing_oi_ratio(contracts) > 0.5:
        before = sum(1 for c in contracts if c.open_interest)
        contracts = _merge_oi_from_alpaca_trading(underlying, contracts)
        after_alpaca = sum(1 for c in contracts if c.open_interest)
        if _missing_oi_ratio(contracts) > 0.5:
            contracts = _merge_oi_from_yfinance(underlying, contracts)
        after_yf = sum(1 for c in contracts if c.open_interest)
        log.info(
            "OI coverage for %s: %d → %d (Alpaca) → %d (yfinance) of %d contracts",
            underlying, before, after_alpaca, after_yf, len(contracts),
        )

    if contracts:
        try:
            df = pd.DataFrame([_to_record(c) for c in contracts])
            cache_write(cache_key, df, namespace=_CACHE_NS)
        except Exception as exc:
            log.debug("cache write failed for %s: %s", cache_key, exc)
    return contracts


def expiries_available(ticker: str) -> list[date]:
    """All expiries quoted by yfinance — Alpaca's chain dict does not expose
    a clean expirations listing, so we always read yfinance for this metadata.
    Result is cached implicitly by yfinance itself (in-process)."""
    cfg = get_config()
    yf_sym = cfg.yfinance_symbol(ticker) or ticker
    try:
        import yfinance as yf
        tk = yf.Ticker(yf_sym)
        return [date.fromisoformat(e) for e in (tk.options or [])]
    except Exception as exc:
        log.debug("expiries_available failed for %s: %s", ticker, exc)
        return []


def chain_dataframe(
    contracts: list[OptionContract], *, sort: str = "strike",
) -> pd.DataFrame:
    """Flatten a list of OptionContracts to a wide pandas DataFrame."""
    if not contracts:
        return pd.DataFrame(columns=[
            "underlying", "symbol", "expiry", "right", "strike", "bid", "ask",
            "mid", "last", "iv", "delta", "gamma", "theta", "vega",
            "open_interest", "volume", "source",
        ])
    df = pd.DataFrame([_to_record(c) for c in contracts])
    if sort in df.columns:
        df = df.sort_values(["expiry", "right", sort]).reset_index(drop=True)
    return df
