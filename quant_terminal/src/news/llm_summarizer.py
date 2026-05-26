"""LLM summariser for earnings transcripts (Anthropic Claude API).

Public API
----------
* `summarise_transcript(text, ticker, *, max_tokens=1024)`
  Returns a structured dict {summary, beats, misses, guidance, sentiment, key_quotes}.

* `summarise_news_burst(headlines, ticker)`
  Compresses N headlines to a 4-bullet narrative used in alerts/email body.

The model name + API key live in environment variables so we never hardcode:
  ANTHROPIC_API_KEY        — required
  ANTHROPIC_MODEL          — default "claude-sonnet-4-5"
"""
from __future__ import annotations

import json
import os
from typing import Any

from src.utils.cache import read as cache_read, write as cache_write
from src.utils.logging import get_logger

log = get_logger(__name__)

_DEFAULT_MODEL = "claude-sonnet-4-5"
_CACHE_NS = "llm_summary"
_CACHE_TTL = 60 * 60 * 24                # transcripts don't change post-publication


def _client():  # noqa: ANN202
    try:
        import anthropic
    except ImportError as exc:
        raise RuntimeError("anthropic SDK missing — `pip install anthropic`") from exc
    key = os.getenv("ANTHROPIC_API_KEY", "")
    if not key:
        raise RuntimeError("ANTHROPIC_API_KEY missing in .env")
    return anthropic.Anthropic(api_key=key)


def _model_id() -> str:
    return os.getenv("ANTHROPIC_MODEL", _DEFAULT_MODEL)


# ---------------------------------------------------------------------------
# Earnings transcript
# ---------------------------------------------------------------------------
_TRANSCRIPT_PROMPT = """\
You are an institutional equity analyst. Summarise the earnings transcript below
for {ticker}. Return STRICT JSON only with these keys:

{{
  "summary":        "1 short paragraph (max 70 words) — the bottom line",
  "beats":          ["…", "…"],     // metrics that beat consensus
  "misses":         ["…", "…"],
  "guidance":       "raised / maintained / lowered / withdrawn — one short sentence",
  "sentiment":      -1.0 to +1.0,    // analyst-style sentiment
  "key_quotes":     ["mgmt direct quote 1", "quote 2"]   // max 3
}}

Transcript:
\"\"\"{text}\"\"\"
"""


def summarise_transcript(
    text: str, ticker: str, *, max_tokens: int = 1024,
) -> dict[str, Any]:
    """Send the transcript to Claude and parse a strict-JSON summary."""
    if not text or len(text.strip()) < 100:
        raise ValueError("transcript too short to summarise meaningfully")
    cache_key = f"transcript|{ticker.upper()}|{hash(text) & 0xffffffff:x}"
    cached = cache_read(cache_key, namespace=_CACHE_NS, max_age_seconds=_CACHE_TTL)
    if cached is not None and not cached.empty:
        try:
            return cached.iloc[0].to_dict()
        except Exception:
            pass

    client = _client()
    prompt = _TRANSCRIPT_PROMPT.format(ticker=ticker.upper(), text=text[:18000])
    resp = client.messages.create(
        model=_model_id(),
        max_tokens=max_tokens,
        messages=[{"role": "user", "content": prompt}],
    )
    body = "".join(getattr(b, "text", "") for b in resp.content) or "{}"
    try:
        data = json.loads(body[body.find("{"): body.rfind("}") + 1])
    except json.JSONDecodeError as exc:
        log.warning("LLM JSON parse failed for %s: %s", ticker, exc)
        return {"summary": body, "beats": [], "misses": [], "guidance": "",
                 "sentiment": 0.0, "key_quotes": []}

    try:
        import pandas as pd
        cache_write(cache_key, pd.DataFrame([data]), namespace=_CACHE_NS)
    except Exception:
        pass
    return data


# ---------------------------------------------------------------------------
# News-burst summariser (for alerts body)
# ---------------------------------------------------------------------------
_BURST_PROMPT = """\
Compress these {n} headlines about {ticker} into 4 bullet points capturing the
narrative shift. Return JSON: {{"bullets": ["…","…","…","…"],
"net_sentiment": -1.0 to +1.0}}

Headlines (oldest → newest):
{lines}
"""


def summarise_news_burst(headlines: list[str], ticker: str) -> dict[str, Any]:
    if not headlines:
        return {"bullets": [], "net_sentiment": 0.0}
    client = _client()
    text = "\n".join(f"- {h}" for h in headlines[-20:])  # cap input
    prompt = _BURST_PROMPT.format(n=len(headlines), ticker=ticker.upper(), lines=text)
    try:
        resp = client.messages.create(
            model=_model_id(),
            max_tokens=600,
            messages=[{"role": "user", "content": prompt}],
        )
        body = "".join(getattr(b, "text", "") for b in resp.content) or "{}"
        return json.loads(body[body.find("{"): body.rfind("}") + 1])
    except Exception as exc:
        log.warning("news burst LLM failed for %s: %s", ticker, exc)
        return {"bullets": [], "net_sentiment": 0.0}
