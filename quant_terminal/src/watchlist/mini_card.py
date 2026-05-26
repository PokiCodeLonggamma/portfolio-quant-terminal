"""Per-ticker mini-card payload assembly.

A "mini card" is a compact KPI tile shown in the Watchlists grid:

    - symbol, sub_theme, conviction, theme, region
    - last close EUR + 1D / 1W / 1M / 3M / YTD returns
    - sparkline series (last ~63 trading days, EUR-normalised)
    - peers, catalyst, list_name

The payload is a plain `dict` (JSON-friendly) so the dashboards layer can
pass it directly into `st.metric` / `plotly` / `st.json` without coupling
to internal models.
"""
from __future__ import annotations

from typing import Any

import pandas as pd

from src.data.fx import series_to_eur

SPARKLINE_DAYS = 63  # ~3 trading months


def mini_card_payload(
    ticker_row: pd.Series | dict,
    prices_eur: pd.Series | None = None,
) -> dict[str, Any]:
    """Assemble a self-contained payload for a single watchlist ticker.

    Parameters
    ----------
    ticker_row: a single row from `add_live_prices(load_watchlist(...))`.
        Either a pandas Series or a plain dict-like mapping.
    prices_eur: optional EUR-normalised price series for the sparkline.
        If `prices_eur` is in the listing currency, callers should pass it
        through `src.data.fx.series_to_eur` first — alternatively pass
        the listing-currency series and the helper will normalise it via
        the `currency` field on the row.
    """
    row = ticker_row.to_dict() if isinstance(ticker_row, pd.Series) else dict(ticker_row)

    spark_index: list[str] = []
    spark_values: list[float] = []
    if prices_eur is not None and isinstance(prices_eur, pd.Series) and not prices_eur.empty:
        s = prices_eur.dropna().tail(SPARKLINE_DAYS)
        # If the caller passed a listing-currency series, try to FX-normalise.
        # Heuristic: if the last value differs from `last_close_eur` by >5%,
        # we treat the input as listing-currency and convert.
        last_close_eur = row.get("last_close_eur")
        if (
            last_close_eur is not None
            and not s.empty
            and abs(float(s.iloc[-1]) - float(last_close_eur))
            > 0.05 * max(abs(float(last_close_eur)), 1e-9)
        ):
            currency = str(row.get("currency") or row.get("price_currency") or "EUR")
            try:
                s = series_to_eur(s, currency)
            except Exception:  # noqa: BLE001 — sparkline must never crash
                pass
        spark_index = [ts.isoformat() if hasattr(ts, "isoformat") else str(ts) for ts in s.index]
        spark_values = [float(v) for v in s.values]

    payload: dict[str, Any] = {
        "symbol": row.get("symbol"),
        "name": row.get("name") or row.get("symbol"),
        "list_name": row.get("list_name"),
        "sub_theme": row.get("sub_theme"),
        "conviction": row.get("conviction"),
        "theme": row.get("theme"),
        "region": row.get("region"),
        "currency": row.get("currency"),
        "catalyst": row.get("catalyst"),
        "peers": list(row.get("peers") or []),
        "isin": row.get("isin"),
        "private": bool(row.get("private", False)),
        # Live numbers
        "last_close_eur": row.get("last_close_eur"),
        "last_close_date": (
            row["last_close_date"].isoformat()
            if isinstance(row.get("last_close_date"), pd.Timestamp)
            else row.get("last_close_date")
        ),
        "ret_1d": row.get("ret_1d"),
        "ret_1w": row.get("ret_1w"),
        "ret_1m": row.get("ret_1m"),
        "ret_3m": row.get("ret_3m"),
        "ret_ytd": row.get("ret_ytd"),
        # Sparkline
        "sparkline": {"index": spark_index, "values": spark_values},
    }
    return payload
