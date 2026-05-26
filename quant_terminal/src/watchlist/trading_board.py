"""Trading watchlist — futures + sector ETFs cross-asset board.

Reads ``config/trading_watchlist.yaml`` and produces a flat DataFrame with
level, daily change and a couple of light technicals (RSI-14, 20d range
position). yfinance is the only data source — falls back gracefully when
quotes are unavailable.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import yaml

from src.utils.logging import get_logger

log = get_logger(__name__)

_CFG_FILE = Path(__file__).resolve().parents[2] / "config" / "trading_watchlist.yaml"


def load_trading_groups(path: Path | None = None) -> dict[str, dict]:
    """Return the YAML-as-dict: ``{group_id: {label, tickers: [{symbol,name}]}}``."""
    p = Path(path) if path else _CFG_FILE
    if not p.exists():
        return {}
    try:
        with p.open("r", encoding="utf-8") as fp:
            data = yaml.safe_load(fp) or {}
    except Exception as exc:
        log.warning("trading_watchlist.yaml read failed: %s", exc)
        return {}
    return dict(data.get("groups") or {})


def _rsi14(close: pd.Series) -> float | None:
    if close is None or len(close) < 20:
        return None
    delta = close.diff().dropna()
    up = delta.clip(lower=0.0)
    dn = -delta.clip(upper=0.0)
    # Wilder's smoothing approximation via EMA
    avg_up = up.ewm(alpha=1 / 14, adjust=False).mean()
    avg_dn = dn.ewm(alpha=1 / 14, adjust=False).mean()
    rs = avg_up.iloc[-1] / (avg_dn.iloc[-1] + 1e-12)
    return float(100 - (100 / (1 + rs)))


def _range_pos20(close: pd.Series) -> float | None:
    if close is None or len(close) < 25:
        return None
    sub = close.tail(20)
    lo = float(sub.min())
    hi = float(sub.max())
    last = float(close.iloc[-1])
    if hi - lo <= 0:
        return None
    return (last - lo) / (hi - lo)


def _one_symbol(sym: str, name: str, group_label: str) -> dict | None:
    try:
        import yfinance as yf
    except ImportError:
        return None
    try:
        hist = yf.download(sym, period="60d", progress=False, auto_adjust=True,
                            threads=False)
    except Exception as exc:
        log.debug("yfinance download %s failed: %s", sym, exc)
        return None
    if hist is None or hist.empty:
        return None
    if isinstance(hist.columns, pd.MultiIndex):
        hist.columns = hist.columns.get_level_values(0)
    if "Close" not in hist.columns:
        return None
    close = hist["Close"].astype(float).dropna()
    if close.empty:
        return None
    last = float(close.iloc[-1])
    prev = float(close.iloc[-2]) if len(close) >= 2 else last
    chg_pct = (last - prev) / prev if prev > 0 else 0.0
    return {
        "group": group_label,
        "symbol": sym,
        "name": name,
        "level": round(last, 4),
        "prev_close": round(prev, 4),
        "chg_pct": chg_pct,
        "rsi14": _rsi14(close),
        "range_pos_20d": _range_pos20(close),
        "asof": str(close.index[-1].date()),
    }


def trading_board() -> pd.DataFrame:
    """Build the full cross-asset board from the YAML watchlist."""
    groups = load_trading_groups()
    if not groups:
        return pd.DataFrame()
    rows: list[dict] = []
    for _gid, gdef in groups.items():
        label = gdef.get("label", "")
        for entry in gdef.get("tickers") or []:
            sym = str(entry.get("symbol", "")).strip()
            name = str(entry.get("name", "")).strip()
            if not sym:
                continue
            r = _one_symbol(sym, name, label)
            if r is not None:
                rows.append(r)
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows)
