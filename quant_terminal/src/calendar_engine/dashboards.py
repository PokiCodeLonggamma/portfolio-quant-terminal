"""Streamlit render functions for the "Catalyst Board" tab.

Render functions are **pure UI** — they accept already-fetched data and
never trigger network I/O.  Fetches happen in ``app.py`` and the data
flows in as arguments.

Widget keys are namespaced ``calendar_*`` to avoid DuplicateWidgetID
collisions with the other clusters.
"""
from __future__ import annotations

from datetime import date

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from src.common.schemas import CalendarEvent
from src.viz.theme import PALETTE, PLOTLY_TEMPLATE


# ---------------------------------------------------------------------------
# colour mapping per category
# ---------------------------------------------------------------------------
_CATEGORY_COLOUR: dict[str, str] = {
    "earnings": PALETTE.accent,
    "fomc": "#8B5CF6",
    "ecb": "#06B6D4",
    "cpi": PALETTE.warning,
    "eia": "#F97316",
    "opec": "#EC4899",
    "nrc": "#10B981",
    "launch": PALETTE.bull_body,
    "contract_award": "#FACC15",
    "dividend": PALETTE.fg_muted,
    "macro_other": PALETTE.fg_muted,
}

_CATEGORY_BADGE: dict[str, str] = {
    "earnings": "EARN",
    "fomc": "FOMC",
    "ecb": "ECB",
    "cpi": "CPI",
    "eia": "EIA",
    "opec": "OPEC",
    "nrc": "NRC",
    "launch": "LAUNCH",
    "contract_award": "AWARD",
    "dividend": "DIV",
    "macro_other": "MACRO",
}


def _apply_template(fig: go.Figure) -> go.Figure:
    fig.update_layout(**PLOTLY_TEMPLATE["layout"])
    return fig


def _events_within(events: list[CalendarEvent], window_days: int) -> list[CalendarEvent]:
    today = date.today()
    return [
        e for e in events
        if 0 <= (e.start.date() - today).days <= window_days
    ]


def _link_for(event: CalendarEvent) -> str | None:
    """Best-effort canonical link per category."""
    payload = event.payload or {}
    if isinstance(payload, dict) and isinstance(payload.get("url"), str):
        return payload["url"]
    cat = event.category
    if cat == "earnings" and event.ticker:
        return f"https://finance.yahoo.com/quote/{event.ticker}/analysis"
    if cat == "fomc":
        return "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm"
    if cat == "ecb":
        return "https://www.ecb.europa.eu/press/calendars/mgcgc/html/index.en.html"
    if cat == "cpi":
        return "https://www.bls.gov/schedule/news_release/cpi.htm"
    if cat == "eia":
        return "https://www.eia.gov/petroleum/supply/weekly/"
    if cat == "opec":
        return "https://www.opec.org/opec_web/en/press_room/2079.htm"
    if cat == "launch":
        return "https://nextspaceflight.com/launches/"
    if cat == "nrc":
        return "https://www.nrc.gov/reactors/new-reactors/smr.html"
    return None


# ---------------------------------------------------------------------------
# 1. Full catalyst calendar (chronological)
# ---------------------------------------------------------------------------
def render_catalyst_calendar(
    events: list[CalendarEvent] | None, window_days: int = 30,
) -> None:
    """Chronological catalyst list colour-coded by category."""
    st.markdown(f"#### Catalyst calendar — next {window_days} days")
    if not events:
        st.info("No catalysts loaded.")
        return
    sliced = sorted(_events_within(events, window_days), key=lambda e: e.start)
    if not sliced:
        st.info("No catalysts inside the selected window.")
        return
    today = date.today()
    rows: list[dict] = []
    for ev in sliced:
        days = (ev.start.date() - today).days
        rows.append({
            "Date": ev.start.date().isoformat(),
            "In days": days,
            "Type": _CATEGORY_BADGE.get(ev.category, ev.category.upper()),
            "Ticker": ev.ticker or "—",
            "Title": ev.title,
            "Source": ev.source,
            "Link": _link_for(ev) or "",
        })
    df = pd.DataFrame(rows)
    st.dataframe(
        df,
        hide_index=True,
        use_container_width=True,
        column_config={
            "Link": st.column_config.LinkColumn("Link", display_text="open"),
        },
        key=f"calendar_full_{window_days}",
    )

    # mini Plotly timeline (one dot per event coloured by category)
    fig = go.Figure()
    for ev in sliced:
        col = _CATEGORY_COLOUR.get(ev.category, PALETTE.fg_muted)
        fig.add_trace(go.Scatter(
            x=[ev.start.date()],
            y=[ev.category],
            mode="markers",
            marker=dict(size=14, color=col, line=dict(color=PALETTE.border, width=1)),
            text=[f"{ev.title}<br>{ev.ticker or 'MACRO'}"],
            hovertemplate="%{text}<br>%{x}<extra></extra>",
            showlegend=False,
        ))
    _apply_template(fig)
    fig.update_layout(
        title="Catalyst timeline",
        height=320,
        yaxis=dict(categoryorder="category ascending"),
    )
    st.plotly_chart(fig, use_container_width=True, key=f"calendar_timeline_{window_days}")


# ---------------------------------------------------------------------------
# 2. Earnings board
# ---------------------------------------------------------------------------
def render_earnings_board(
    events: list[CalendarEvent] | None,
    implied_moves: dict[str, float] | None = None,
    historical_avg: dict[str, float] | None = None,
    window_days: int = 14,
) -> None:
    """Table per ticker: date / implied move / historical avg next-day move."""
    st.markdown(f"#### Earnings — next {window_days} days")
    earnings = [e for e in (events or []) if e.category == "earnings"]
    sliced = _events_within(earnings, window_days)
    if not sliced:
        st.info(f"No earnings in the next {window_days} days.")
        return
    moves = implied_moves or {}
    hist = historical_avg or {}
    today = date.today()
    rows: list[dict] = []
    for ev in sorted(sliced, key=lambda e: e.start):
        tkr = ev.ticker or "—"
        days = (ev.start.date() - today).days
        im = moves.get(tkr)
        ha = hist.get(tkr)
        rows.append({
            "Ticker": tkr,
            "Date": ev.start.date().isoformat(),
            "In days": days,
            "Implied move %": f"{im * 100:.1f}%" if im is not None else "n/a",
            "Hist. avg |move| %": f"{ha * 100:.1f}%" if ha is not None else "n/a",
            "Title": ev.title,
        })
    st.dataframe(
        pd.DataFrame(rows), hide_index=True, use_container_width=True,
        key="calendar_earnings_board",
    )


# ---------------------------------------------------------------------------
# 3. Macro board (FOMC/ECB/OPEC/CPI)
# ---------------------------------------------------------------------------
def render_macro_board(events: list[CalendarEvent] | None) -> None:
    st.markdown("#### Macro & monetary calendar")
    if not events:
        st.info("No macro events loaded.")
        return
    keep = {"fomc", "ecb", "cpi", "opec", "eia", "nrc"}
    sub = [e for e in events if e.category in keep]
    if not sub:
        st.info("No macro events in the current dataset.")
        return
    sub = sorted(sub, key=lambda e: e.start)

    today = date.today()
    rows = []
    for ev in sub:
        days = (ev.start.date() - today).days
        if days < -3:
            continue  # hide events more than 3 days in the past
        rows.append({
            "Date": ev.start.date().isoformat(),
            "In days": days,
            "Type": _CATEGORY_BADGE.get(ev.category, ev.category.upper()),
            "Title": ev.title,
            "Ticker": ev.ticker or "—",
        })
    if not rows:
        st.info("All macro events already in the past.")
        return
    df = pd.DataFrame(rows)
    st.dataframe(df, hide_index=True, use_container_width=True, key="calendar_macro_board")

    # bar chart: count per category in the next 90 days
    future = df[df["In days"].between(0, 90)]
    if not future.empty:
        agg = future.groupby("Type").size().reset_index(name="count")
        fig = go.Figure(go.Bar(
            x=agg["Type"], y=agg["count"],
            marker_color=[_CATEGORY_COLOUR.get(t.lower(), PALETTE.accent) for t in agg["Type"]],
        ))
        fig.update_layout(title="Macro events in next 90 days", height=300)
        st.plotly_chart(_apply_template(fig), use_container_width=True, key="calendar_macro_bar")


# ---------------------------------------------------------------------------
# 4. Launch board
# ---------------------------------------------------------------------------
def render_launch_board(events: list[CalendarEvent] | None) -> None:
    st.markdown("#### Space launch manifest")
    if not events:
        st.info("No launch manifest loaded.")
        return
    launches = sorted(
        [e for e in events if e.category == "launch"], key=lambda e: e.start,
    )
    if not launches:
        st.info("No upcoming launches.")
        return
    today = date.today()
    rows = []
    for ev in launches:
        days = (ev.start.date() - today).days
        if days < -7:
            continue
        payload = ev.payload or {}
        rows.append({
            "NET Date": ev.start.date().isoformat(),
            "In days": days,
            "Operator": str(payload.get("operator", "")).upper(),
            "Vehicle": payload.get("vehicle", ""),
            "Mission": payload.get("mission", ev.title),
            "Customer": payload.get("customer", ""),
            "Ticker": ev.ticker or "—",
        })
    if not rows:
        st.info("Launches are all >7 days in the past.")
        return
    st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True, key="calendar_launch_board")
