"""Plotly template v3 — Wall Street Brutalist visual language.

Applied to every Plotly figure via ``fig.update_layout(template=PLOTLY_TEMPLATE)``.
Sharp grid lines (gold rule on axis), mono tick labels (JetBrains Mono),
no chartjunk, deep ink background that blends seamlessly with the page.

Imported by ``src.viz.theme`` (re-exported at module level) so all 25
dashboards consume it without code changes.
"""
from __future__ import annotations

from src.viz.theme import FONT_MONO, PALETTE

PLOTLY_TEMPLATE: dict = {
    "layout": {
        "paper_bgcolor": PALETTE.bg,
        "plot_bgcolor": PALETTE.bg,
        "font": {
            "family": FONT_MONO,
            "size": 12,
            "color": PALETTE.fg_muted,
        },
        "title": {
            "font": {
                "family": FONT_MONO,
                "size": 13,
                "color": PALETTE.fg,
            },
            "x": 0.0,
            "xanchor": "left",
            "y": 0.97,
            "pad": {"t": 6, "b": 6},
        },
        "colorway": list(PALETTE.plotly_colorway_v3),
        "xaxis": {
            "gridcolor": PALETTE.border,
            "linecolor": PALETTE.border_strong,
            "zerolinecolor": PALETTE.border_strong,
            "color": PALETTE.fg_muted,
            "tickfont": {"family": FONT_MONO, "size": 11, "color": PALETTE.fg_muted},
            "title": {
                "font": {"family": FONT_MONO, "size": 12, "color": PALETTE.fg_dim},
                "standoff": 10,
            },
            "ticks": "outside",
            "tickcolor": PALETTE.border_strong,
            "showspikes": False,
        },
        "yaxis": {
            "gridcolor": PALETTE.border,
            "linecolor": PALETTE.border_strong,
            "zerolinecolor": PALETTE.border_strong,
            "color": PALETTE.fg_muted,
            "tickfont": {"family": FONT_MONO, "size": 11, "color": PALETTE.fg_muted},
            "title": {
                "font": {"family": FONT_MONO, "size": 12, "color": PALETTE.fg_dim},
                "standoff": 10,
            },
            "ticks": "outside",
            "tickcolor": PALETTE.border_strong,
            "showspikes": False,
        },
        "legend": {
            "font": {
                "family": FONT_MONO,
                "size": 11,
                "color": PALETTE.fg_muted,
            },
            "bgcolor": "rgba(0,0,0,0)",
            "bordercolor": PALETTE.border,
            "borderwidth": 0,
            "orientation": "h",
            "y": -0.18,
            "x": 0,
            "xanchor": "left",
        },
        "margin": {"l": 50, "r": 30, "t": 40, "b": 50},
        "hoverlabel": {
            "bgcolor": PALETTE.card,
            "bordercolor": PALETTE.rule,
            "font": {"family": FONT_MONO, "color": PALETTE.fg, "size": 12},
        },
        # Subtle annotation defaults — keep editorial typography in chart text
        "annotationdefaults": {
            "font": {"family": FONT_MONO, "size": 11, "color": PALETTE.fg_muted},
            "showarrow": False,
        },
        # Brutalist polish: no rounded corners on shapes
        "shapedefaults": {
            "line": {"color": PALETTE.rule, "width": 1},
        },
    }
}
