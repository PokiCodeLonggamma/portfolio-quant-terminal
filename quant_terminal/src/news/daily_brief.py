"""Daily AI brief — Claude-powered morning summary.

Inputs (all already produced by other modules in the project):
  * Open positions snapshot (journal)
  * Current portfolio P&L summary
  * Today's & upcoming catalysts (calendar engine)
  * Last 24h news headlines + sentiment (rss_fetcher + sentiment)
  * Current HMM regime label + probabilities
  * Latest alerts fired (state.history)

Outputs:
  * A Markdown brief with sections: "Open positions watch", "Catalysts today",
    "News pulse", "Regime & macro", "Recommended actions".
  * Cached 1h (TTL) so opening the dashboard multiple times in the morning
    doesn't burn LLM quota.

Failure mode: when ``ANTHROPIC_API_KEY`` is missing we return a stripped
"data-only" brief (no LLM) so the user still sees a useful summary.
"""
from __future__ import annotations

import os
from datetime import datetime
from typing import Any

import pandas as pd

from src.utils.cache import read as cache_read, write as cache_write
from src.utils.logging import get_logger

log = get_logger(__name__)


_CACHE_NS = "daily_brief"
_CACHE_TTL = 60 * 60                # 1 hour
_DEFAULT_MODEL = "claude-sonnet-4-5"


def _model_id() -> str:
    return os.getenv("ANTHROPIC_MODEL", _DEFAULT_MODEL)


def _llm_available() -> bool:
    return bool(os.getenv("ANTHROPIC_API_KEY", "").strip())


# ---------------------------------------------------------------------------
# Context assembly — pure data shape, no API calls
# ---------------------------------------------------------------------------
def assemble_context(
    *,
    open_positions_df: pd.DataFrame | None = None,
    portfolio_pnl_eur: float | None = None,
    portfolio_nav_eur: float | None = None,
    catalysts_today: list[dict] | None = None,
    catalysts_week: list[dict] | None = None,
    news_24h_df: pd.DataFrame | None = None,
    regime_label: str | None = None,
    regime_probs: dict[str, float] | None = None,
    recent_alerts: list[dict] | None = None,
) -> dict[str, Any]:
    """Bundle the raw context the LLM will read."""
    ctx: dict[str, Any] = {
        "asof_utc": datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"),
        "portfolio_nav_eur": portfolio_nav_eur,
        "portfolio_pnl_eur": portfolio_pnl_eur,
        "regime_label": regime_label,
        "regime_probs": regime_probs or {},
    }

    # Open positions — keep the salient columns
    if open_positions_df is not None and not open_positions_df.empty:
        cols = [c for c in [
            "ticker", "direction", "strike", "expiry", "qty",
            "debit_eur", "live_mid_eur", "mtm_pnl_eur", "mtm_pct",
            "dte", "delta", "theta_eur_per_day",
        ] if c in open_positions_df.columns]
        ctx["open_positions"] = open_positions_df[cols].to_dict(orient="records")
    else:
        ctx["open_positions"] = []

    # Catalysts
    ctx["catalysts_today"] = catalysts_today or []
    ctx["catalysts_week"] = catalysts_week or []

    # News
    if news_24h_df is not None and not news_24h_df.empty:
        cols = [c for c in ["ts", "ticker", "title", "sentiment", "source"]
                if c in news_24h_df.columns]
        ctx["news_headlines"] = (
            news_24h_df[cols].head(40).to_dict(orient="records")
        )
    else:
        ctx["news_headlines"] = []

    ctx["recent_alerts"] = recent_alerts or []
    return ctx


# ---------------------------------------------------------------------------
# Markdown fallback brief (no LLM)
# ---------------------------------------------------------------------------
def _data_only_brief(ctx: dict[str, Any]) -> str:
    """Plain-data brief when the LLM is unavailable."""
    out: list[str] = [f"# Daily Brief — {ctx['asof_utc']}\n"]

    out.append("## Portfolio snapshot")
    nav = ctx.get("portfolio_nav_eur")
    pnl = ctx.get("portfolio_pnl_eur")
    if nav is not None:
        out.append(f"- **NAV:** €{nav:,.0f}")
    if pnl is not None:
        out.append(f"- **Cumulative P&L:** €{pnl:+,.0f}")
    n_open = len(ctx.get("open_positions") or [])
    out.append(f"- **Open options positions:** {n_open}")
    if n_open > 0:
        out.append("\n### Open positions")
        for pos in ctx["open_positions"][:15]:
            out.append(
                f"- {pos.get('ticker', '?')} {pos.get('direction', '')} "
                f"{pos.get('strike', '?')} @ {pos.get('expiry', '')} "
                f"(DTE {pos.get('dte', '?')}) — "
                f"PnL €{(pos.get('mtm_pnl_eur') or 0):+,.0f}"
            )

    today = ctx.get("catalysts_today") or []
    if today:
        out.append("\n## Catalysts today")
        for ev in today[:10]:
            out.append(f"- {ev.get('ticker', '—')} · {ev.get('title', '')} "
                       f"({ev.get('event_type', '')})")

    if ctx.get("regime_label"):
        out.append(f"\n## Regime\n- Current state: **{ctx['regime_label']}**")
        for lbl, p in (ctx.get("regime_probs") or {}).items():
            out.append(f"  - {lbl}: {p:.0%}")

    news = ctx.get("news_headlines") or []
    if news:
        out.append("\n## News pulse (24h)")
        for h in news[:12]:
            sent = h.get("sentiment")
            sent_str = f"({sent:+.2f})" if sent is not None else ""
            out.append(f"- {h.get('ticker', '—')} · {h.get('title', '')} {sent_str}")

    alerts = ctx.get("recent_alerts") or []
    if alerts:
        out.append("\n## Recent alerts")
        for a in alerts[:8]:
            out.append(f"- {a.get('fired_at', '')} · {a.get('title', '')}")

    out.append("\n---\n_LLM not configured (set `ANTHROPIC_API_KEY` for a synthesised brief)._")
    return "\n".join(out)


# ---------------------------------------------------------------------------
# LLM-powered brief
# ---------------------------------------------------------------------------
_PROMPT = """\
You are a portfolio analyst writing a concise 5-minute morning briefing for a
quant trader who runs an event-driven long-options book (long calls/puts, Δ≈0.25,
focus on tech / space / uranium small-caps).

Use ONLY the JSON context below. Be concrete, no hedging. Output a Markdown
brief with EXACTLY these sections:

# Morning Brief — {asof}

## 1. Book status
- Open positions: P&L, time-decay, anything urgent (DTE < 14, large theta, etc.)

## 2. Today's catalysts
- Earnings, macro events, launches in next 24h that affect open positions or watchlist tickers

## 3. News pulse
- The 3-5 most actionable items from the past 24h

## 4. Regime & risk
- HMM regime label + what it means for sizing today

## 5. Recommended actions
- 3 bullet points, actionable, in priority order

Be terse. Use € for money, % for moves. No platitudes.

JSON context:
```json
{context_json}
```
"""


def generate_brief(ctx: dict[str, Any], *, max_tokens: int = 1200) -> str:
    """Run the LLM (or fall back to data-only). Cached 1h on context hash."""
    cache_key = f"brief|{hash(str(sorted(ctx.items()))) & 0xffffffff:x}"
    cached = cache_read(cache_key, namespace=_CACHE_NS, max_age_seconds=_CACHE_TTL)
    if cached is not None and not cached.empty:
        return str(cached.iloc[0, 0])

    if not _llm_available():
        out = _data_only_brief(ctx)
        try:
            cache_write(cache_key, pd.DataFrame({"text": [out]}), namespace=_CACHE_NS)
        except Exception:
            pass
        return out

    try:
        import anthropic
        import json as _json
        client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY", ""))
        ctx_clean = _json.loads(_json.dumps(ctx, default=str))
        prompt = _PROMPT.format(
            asof=ctx.get("asof_utc", "now"),
            context_json=_json.dumps(ctx_clean, indent=2)[:30000],
        )
        resp = client.messages.create(
            model=_model_id(),
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}],
        )
        body = "".join(getattr(b, "text", "") for b in resp.content) or _data_only_brief(ctx)
    except Exception as exc:
        log.warning("daily brief LLM call failed: %s", exc)
        body = _data_only_brief(ctx) + f"\n\n_⚠ LLM call failed: {exc}_"

    try:
        cache_write(cache_key, pd.DataFrame({"text": [body]}), namespace=_CACHE_NS)
    except Exception:
        pass
    return body


__all__ = ["assemble_context", "generate_brief"]
