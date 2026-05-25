"""Streamlit renderers for the Alerts tab."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from src.alerts.state import load_history
from src.alerts.triggers import Trigger
from src.viz.theme import PALETTE


_SEVERITY_BADGE = {
    "info":     ("#3B82F6", "ℹ️ info"),
    "warning":  ("#F59E0B", "⚠️ warning"),
    "critical": ("#EF4444", "🚨 critical"),
}


def render_alerts_status(triggers: list[Trigger], fired_now: list, dispatchers_status: dict) -> None:
    """Top strip — count of enabled triggers, just-fired, channels OK."""
    enabled = sum(1 for t in triggers if t.enabled)
    cols = st.columns(4)
    cols[0].metric("Triggers configurés", f"{len(triggers)}")
    cols[1].metric("Triggers actifs", f"{enabled}")
    cols[2].metric("Fired ce refresh", f"{len(fired_now)}")
    cols[3].metric(
        "Channels OK",
        f"{sum(1 for v in dispatchers_status.values() if v)}/{len(dispatchers_status)}",
    )


def render_dispatcher_status(status: dict[str, bool]) -> None:
    """Per-channel availability badges (from env-var check)."""
    if not status:
        return
    cols = st.columns(len(status))
    for col, (name, ok) in zip(cols, status.items()):
        color = "#22C55E" if ok else "#94A3B8"
        col.markdown(
            f"<div style='padding:8px 12px;border-radius:8px;background:{PALETTE.card};"
            f"border:1px solid {PALETTE.border}'>"
            f"<span style='color:{color};font-weight:600'>● {name}</span>"
            f"<br><span style='color:{PALETTE.fg_muted};font-size:0.75rem'>"
            f"{'configured' if ok else 'not configured'}</span></div>",
            unsafe_allow_html=True,
        )


def render_triggers_table(triggers: list[Trigger]) -> None:
    if not triggers:
        st.info("Aucun trigger défini. Édite `config/alerts.yaml`.")
        return
    rows = []
    for t in triggers:
        rows.append({
            "name": t.name,
            "type": t.type,
            "enabled": t.enabled,
            "cooldown_min": t.cooldown_minutes,
            "severity": t.severity,
            "channels": ",".join(t.channels),
            "params": str(t.params),
        })
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)


def render_alerts_history(limit: int = 50) -> None:
    history = load_history()
    if not history:
        st.info("Aucune alerte n'a encore été émise.")
        return
    df = pd.DataFrame(history[-limit:][::-1])  # newest first
    # Severity badges as a colored "sev" column
    if "severity" in df.columns:
        df["sev"] = df["severity"].map(lambda s: _SEVERITY_BADGE.get(s, ("#94A3B8", s))[1])
    keep = [c for c in ["sev", "fired_at", "trigger_name", "title", "body", "channels"]
             if c in df.columns]
    st.dataframe(df[keep], use_container_width=True, hide_index=True)


def render_just_fired_toasts(fired: list) -> None:
    """Show a Streamlit toast for each just-fired event (severity-coloured)."""
    for event in fired:
        sev = getattr(event, "severity", "info")
        title = getattr(event, "title", "")
        icon = {"info": "ℹ️", "warning": "⚠️", "critical": "🚨"}.get(sev, "🔔")
        try:
            st.toast(f"{icon} {title}", icon=icon)
        except Exception:
            st.info(f"{icon} {title}")
