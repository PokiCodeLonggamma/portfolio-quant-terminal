"""Cross-Asset Universe dashboard (CDC §1).

Renders the full institutional cross-asset matrix:
  - Indices US (SP/ES/MES, ND/NQ/MNQ, …)
  - Volatilité (VX/VXM)
  - Taux US (ZT/TU, ZF/FV, ZN/TY, ZB/US)
  - Énergie (CL/QM/MCL, B, NG/QG/MNG, HO, RB)
  - Métaux (GC/MGC, SI/SIL, HG/MHG, PL, PA, URA, URNM, …)
  - Crypto (BTC/MBT, ETH/MET)
  - Futures Européens (FESX, FDAX/FDXM/FDXS, FCE, Z, FSMI)
  - ETF Sectoriels (XLK, XLF, XLE, …)
  - ETF Thématiques (SMH, ARKX, URA, …)
  - Broad benchmarks (SPY, QQQ, IWM, DIA, SPX, NDX, RUT, DXY)

Each row has a "📈 Chart" expander that opens a TradingView candlestick
(CDC-preferred drilldown pattern).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import pandas as pd
import streamlit as st

from src.universe.cross_asset import (
    AssetClass,
    ContractSpec,
    CrossAssetUniverse,
    get_universe,
)
from src.viz.theme import (
    PALETTE,
    color_pct,
    empty_state_html,
    kpi_tile_html,
    section_header_html,
    stat_strip_html,
)
from src.viz.tv_chart import render_tv_chart, tv_symbol_for


# ---------------------------------------------------------------------------
# Live quote enrichment — uses yfinance fast_info (cheap, no rate-limit pain)
# ---------------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class _Quote:
    last: float | None
    chg_1d_pct: float | None
    chg_5d_pct: float | None
    asof: datetime | None


@st.cache_data(ttl=300, show_spinner=False)
def _quote_one(yf_symbol: str) -> _Quote:
    """Lightweight quote via yfinance — TTL 5 min."""
    if not yf_symbol:
        return _Quote(None, None, None, None)
    try:
        import yfinance as yf
        tk = yf.Ticker(yf_symbol)
        hist = tk.history(period="10d", auto_adjust=True)
        if hist is None or hist.empty or "Close" not in hist.columns:
            return _Quote(None, None, None, None)
        closes = hist["Close"].dropna()
        if closes.empty:
            return _Quote(None, None, None, None)
        last = float(closes.iloc[-1])
        chg_1d = None
        chg_5d = None
        if len(closes) >= 2:
            chg_1d = (last / float(closes.iloc[-2]) - 1.0) * 100.0
        if len(closes) >= 6:
            chg_5d = (last / float(closes.iloc[-6]) - 1.0) * 100.0
        return _Quote(
            last=last,
            chg_1d_pct=chg_1d,
            chg_5d_pct=chg_5d,
            asof=datetime.utcnow(),
        )
    except Exception:
        return _Quote(None, None, None, None)


def _quote_rows(specs: list[ContractSpec]) -> pd.DataFrame:
    rows = []
    for s in specs:
        q = _quote_one(s.yfinance) if s.yfinance else _Quote(None, None, None, None)
        rows.append({
            "tier": s.tier,
            "logical": s.logical,
            "name": s.name,
            "exchange": s.exchange,
            "currency": s.currency,
            "last": q.last,
            "1d %": q.chg_1d_pct,
            "5d %": q.chg_5d_pct,
            "mult": s.multiplier,
            "tick $": s.tick_value,
            "options": "✅" if s.option_market else "—",
            "yfinance": s.yfinance or "—",
            "tv": tv_symbol_for(s.logical) or "—",
            "notes": s.notes,
        })
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Asset-class section renderer
# ---------------------------------------------------------------------------
def _kpi_strip_for(specs: list[ContractSpec]) -> str:
    """Top KPIs for an asset class — # contracts, # with options, # tiers covered."""
    n = len(specs)
    n_opt = sum(1 for s in specs if s.option_market)
    tiers = {s.tier for s in specs}
    n_yf = sum(1 for s in specs if s.yfinance)
    items: list[dict] = [
        {"label": "Contracts",    "value": str(n)},
        {"label": "With options", "value": f"{n_opt}/{n}"},
        {"label": "Tiers",        "value": " / ".join(sorted(tiers))},
        {"label": "Yfinance map", "value": f"{n_yf}/{n}"},
    ]
    return stat_strip_html(items)


def render_asset_class_section(
    ac: AssetClass,
    *,
    show_charts: bool = True,
    interval: str = "D",
    chart_height: int = 420,
) -> None:
    """Render one asset class block: header + KPIs + matrix + drilldown selector."""
    specs = list(ac.contracts)
    st.markdown(
        section_header_html(
            f"{ac.icon}  {ac.label}",
            icon=None,
            subtitle=f"{len(specs)} contrats · classe `{ac.key}` · "
                     "cliquez sur un ticker pour ouvrir le graphique candlestick.",
        ),
        unsafe_allow_html=True,
    )
    st.markdown(_kpi_strip_for(specs), unsafe_allow_html=True)

    df = _quote_rows(specs)

    # Pretty formatting
    df_display = df.copy()
    df_display["last"] = df_display["last"].apply(
        lambda v: "—" if v is None or pd.isna(v) else f"{v:,.2f}".replace(",", " ")
    )
    df_display["1d %"] = df_display["1d %"].apply(
        lambda v: "—" if v is None or pd.isna(v) else f"{v:+.2f}%"
    )
    df_display["5d %"] = df_display["5d %"].apply(
        lambda v: "—" if v is None or pd.isna(v) else f"{v:+.2f}%"
    )

    st.dataframe(
        df_display[[
            "tier", "logical", "name", "exchange", "currency",
            "last", "1d %", "5d %", "mult", "tick $", "options",
            "yfinance", "tv", "notes",
        ]],
        use_container_width=True,
        hide_index=True,
        column_config={
            "tier": st.column_config.TextColumn("Tier", width="small"),
            "logical": st.column_config.TextColumn("Logical", width="small"),
            "exchange": st.column_config.TextColumn("Exchange", width="small"),
            "currency": st.column_config.TextColumn("Ccy", width="small"),
            "last": st.column_config.TextColumn("Last", width="small"),
            "1d %": st.column_config.TextColumn("1d %", width="small"),
            "5d %": st.column_config.TextColumn("5d %", width="small"),
            "mult": st.column_config.NumberColumn("Mult", width="small"),
            "tick $": st.column_config.NumberColumn("Tick $", width="small"),
            "options": st.column_config.TextColumn("Opt", width="small"),
            "yfinance": st.column_config.TextColumn("yfinance", width="small"),
            "tv": st.column_config.TextColumn("TradingView", width="medium"),
            "notes": st.column_config.TextColumn("Notes", width="large"),
        },
    )

    if not show_charts:
        return

    pool = [s.logical for s in specs]
    pick = st.selectbox(
        "🔍 Open candlestick chart for…",
        options=["—"] + pool,
        key=f"xa_pick_{ac.key}",
    )
    if pick and pick != "—":
        spec = ac.find(pick)
        if spec is None:
            st.warning(f"{pick}: not found in {ac.key}")
            return
        with st.expander(
            f"📈 {spec.icon if False else ''}{spec.logical} — {spec.name} "
            f"({spec.exchange}, {spec.currency})",
            expanded=True,
        ):
            render_tv_chart(spec.logical, interval=interval, height=chart_height)


# ---------------------------------------------------------------------------
# Heatmap overview — all asset classes condensed
# ---------------------------------------------------------------------------
def render_overview_heatmap(universe: CrossAssetUniverse) -> None:
    """A compact daily-perf heatmap across the whole universe."""
    rows = []
    for ac in universe.asset_classes:
        for s in ac.contracts:
            if not s.yfinance:
                continue
            q = _quote_one(s.yfinance)
            rows.append({
                "asset_class": ac.label,
                "logical": s.logical,
                "name": s.name,
                "1d %": q.chg_1d_pct,
                "5d %": q.chg_5d_pct,
            })
    df = pd.DataFrame(rows)
    if df.empty:
        st.markdown(
            empty_state_html(
                title="No quotes",
                text="yfinance returned no data for any cross-asset symbol. "
                     "Check network connectivity or retry in a few minutes.",
                icon="📡",
            ),
            unsafe_allow_html=True,
        )
        return
    df = df.dropna(subset=["1d %"])
    df = df.sort_values("1d %", ascending=False)

    # Compact table with conditional coloring on perf
    def _pct_html(v):
        if v is None or pd.isna(v):
            return "—"
        col = color_pct(float(v) / 100.0)
        return f'<span style="color:{col};font-family:JetBrains Mono,monospace;">{v:+.2f}%</span>'

    df_html = df.copy()
    df_html["1d %"] = df_html["1d %"].apply(_pct_html)
    df_html["5d %"] = df_html["5d %"].apply(_pct_html)
    st.markdown(
        df_html.to_html(escape=False, index=False, classes="xa-overview"),
        unsafe_allow_html=True,
    )
    st.markdown(
        f"<style>"
        f".xa-overview {{width:100%; border-collapse: collapse; font-size:0.85rem;}}"
        f".xa-overview th {{background:{PALETTE.muted_bg}; color:{PALETTE.fg};"
        f"text-align:left; padding:8px 10px; border-bottom:1px solid {PALETTE.border};}}"
        f".xa-overview td {{padding:6px 10px; border-bottom:1px solid {PALETTE.border};"
        f"color:{PALETTE.fg_muted};}}"
        f".xa-overview tr:hover td {{background:{PALETTE.card_hover};}}"
        f"</style>",
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------------------
# Main entry point — used by app.py
# ---------------------------------------------------------------------------
def render_cross_asset_tab() -> None:
    """Top-level entry: header, summary KPIs, per-class accordions, overview heatmap."""
    u = get_universe()
    if not u.asset_classes:
        st.error(
            "Cross-asset universe could not be loaded. "
            "Check `config/universe_cross_asset.yaml` exists and parses."
        )
        return

    total_contracts = len(u.all_contracts())
    n_classes = len(u.asset_classes)
    n_opt = sum(1 for c in u.all_contracts() if c.option_market)
    n_futures = sum(1 for c in u.all_contracts() if c.is_future)
    n_etf = sum(1 for c in u.all_contracts() if c.is_etf)

    st.markdown(
        section_header_html(
            "Cross-Asset Universe",
            icon="🌍",
            subtitle=f"CDC §1 · {n_classes} asset classes · {total_contracts} contrats · "
                     "indices, vol, taux, énergie, métaux, crypto, futures EU, ETF.",
            meta="TradingView drilldown au clic",
        ),
        unsafe_allow_html=True,
    )

    # Header KPIs
    c1, c2, c3, c4 = st.columns(4)
    c1.markdown(kpi_tile_html("Asset classes", str(n_classes), hint="indices / vol / taux / …"), unsafe_allow_html=True)
    c2.markdown(kpi_tile_html("Contracts", str(total_contracts), hint="standard + mini + micro"), unsafe_allow_html=True)
    c3.markdown(kpi_tile_html("Options-traded", f"{n_opt}/{total_contracts}", hint="chaînes listées et liquides"), unsafe_allow_html=True)
    c4.markdown(kpi_tile_html("Futures / ETF", f"{n_futures} / {n_etf}", hint="livrables / cash"), unsafe_allow_html=True)

    st.divider()

    # Choose default view
    view = st.radio(
        "View",
        options=["📊 Per asset class", "🔥 Daily heatmap (all)", "📈 Chart only"],
        horizontal=True,
        key="xa_view",
    )

    if view == "🔥 Daily heatmap (all)":
        render_overview_heatmap(u)
        return

    if view == "📈 Chart only":
        all_logicals = u.all_logicals()
        col_a, col_b, col_c = st.columns([3, 1, 1])
        pick = col_a.selectbox(
            "Ticker",
            options=all_logicals,
            index=all_logicals.index("ES") if "ES" in all_logicals else 0,
            key="xa_chart_only_pick",
        )
        interval = col_b.selectbox(
            "Interval",
            options=["1", "5", "15", "60", "240", "D", "W", "M"],
            index=5,
            key="xa_chart_only_interval",
        )
        height = col_c.number_input(
            "Height",
            min_value=300, max_value=900, value=600, step=20,
            key="xa_chart_only_height",
        )
        render_tv_chart(pick, interval=interval, height=int(height))
        return

    # Per-asset-class accordion (default)
    class_filter = st.multiselect(
        "Filter asset classes",
        options=[ac.key for ac in u.asset_classes],
        default=[ac.key for ac in u.asset_classes],
        format_func=lambda k: next(
            (f"{ac.icon} {ac.label}" for ac in u.asset_classes if ac.key == k),
            k,
        ),
        key="xa_class_filter",
    )
    interval = st.select_slider(
        "Default chart interval",
        options=["5", "15", "60", "240", "D", "W"],
        value="D",
        key="xa_default_interval",
    )

    for ac in u.asset_classes:
        if ac.key not in class_filter:
            continue
        with st.expander(f"{ac.icon} {ac.label}  ({len(ac.contracts)})", expanded=False):
            render_asset_class_section(
                ac,
                show_charts=True,
                interval=interval,
                chart_height=420,
            )
