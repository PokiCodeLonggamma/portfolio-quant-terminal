"""Cluster 5 — Trading section (directional long options).

Public sub-modules:
  * `greeks`         — Black-Scholes pricer, inverse IV, delta/gamma/theta/vega.
  * `options_chain`  — Alpaca primary, yfinance fallback chain fetcher.
  * `iv_rank`        — 1-year IV rank percentile.
  * `gex`            — Net Gamma Exposure, gamma-flip strike, negative-gamma zone.
  * `delta_finder`   — Closest-delta strike picker (default delta=0.25).
  * `trade_ticket`   — Trade-ticket generator with hard gating rules.
  * `journal`        — Parquet-persisted open/closed trades + live MTM.
  * `squeeze_score`  — Composite gamma-squeeze score 0-100.
  * `dashboards`     — Streamlit render blocks for the new tab.
"""
from __future__ import annotations
