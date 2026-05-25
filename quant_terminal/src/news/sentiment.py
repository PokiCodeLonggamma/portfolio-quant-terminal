"""Rule-based finance-news sentiment.

Pure-Python, zero NLP dependencies.  Computes a polarity score in
``[-1, +1]`` by counting hand-curated positive / negative lexemes in a
headline, scaled by the headline length and lightly boosted by intensity
modifiers (e.g. ``"surges"`` > ``"rises"``).

Negation handling
-----------------
A negation cue (``no``, ``not``, ``never``, ``without``) **within 3 tokens
before** a polarity word flips the sign of that word's contribution.

Why a hand-rolled scorer instead of VADER?
------------------------------------------
The brief explicitly forbids external NLP libraries and asks for a
finance-oriented lexicon — VADER is built for general social-media tone,
not the financial vernacular ("miss", "beat", "guide above", "cut").
"""
from __future__ import annotations

import re
from typing import Iterable

import pandas as pd


# ---------------------------------------------------------------------------
# Lexicons (lower-case stems).  Weights ∈ [0.4, 1.0] tune intensity.
# ---------------------------------------------------------------------------
POSITIVE_LEX: dict[str, float] = {
    # earnings beats
    "beat": 0.9, "beats": 0.9, "beating": 0.7,
    "exceed": 0.7, "exceeds": 0.7, "exceeded": 0.7,
    "outperform": 0.8, "outperforms": 0.8,
    # guidance
    "raise": 0.7, "raises": 0.7, "raised": 0.7,
    "guide": 0.5, "guides": 0.5,
    "above": 0.5, "ahead": 0.5,
    # price moves
    "surge": 1.0, "surges": 1.0, "surged": 1.0, "surging": 1.0,
    "soar": 1.0, "soars": 1.0, "soared": 1.0,
    "jump": 0.8, "jumps": 0.8, "jumped": 0.8,
    "rally": 0.8, "rallies": 0.8, "rallied": 0.8,
    "rise": 0.6, "rises": 0.6, "rose": 0.6,
    "gain": 0.5, "gains": 0.5, "gained": 0.5,
    "climb": 0.6, "climbs": 0.6, "climbed": 0.6,
    "advance": 0.5, "advances": 0.5,
    # ratings / sentiment
    "upgrade": 0.9, "upgrades": 0.9, "upgraded": 0.9,
    "bullish": 0.8, "buy": 0.6, "overweight": 0.7,
    "outperformer": 0.6, "outperformance": 0.6,
    "strong": 0.5, "robust": 0.5, "solid": 0.5,
    # business outcomes
    "record": 0.6, "expansion": 0.5, "growth": 0.4,
    "win": 0.6, "wins": 0.6, "won": 0.6, "winning": 0.5,
    "award": 0.5, "awarded": 0.6, "contract": 0.4,
    "approval": 0.7, "approved": 0.7, "approves": 0.7,
    "partnership": 0.5, "deal": 0.4, "acquisition": 0.4,
    "launch": 0.4, "launches": 0.4, "launched": 0.4,
    "successful": 0.7, "milestone": 0.6, "breakthrough": 0.9,
    "profit": 0.5, "profitable": 0.6,
    "boost": 0.6, "boosts": 0.6, "boosted": 0.6,
}

NEGATIVE_LEX: dict[str, float] = {
    # earnings misses
    "miss": 0.9, "misses": 0.9, "missed": 0.9, "missing": 0.7,
    "disappoint": 0.8, "disappoints": 0.8, "disappointing": 0.9,
    "underperform": 0.8, "underperforms": 0.8,
    "below": 0.5, "weak": 0.6, "weaker": 0.6, "weakness": 0.6,
    # guidance
    "cut": 0.8, "cuts": 0.8, "cutting": 0.7,
    "lower": 0.5, "lowers": 0.5, "lowered": 0.5,
    "reduce": 0.5, "reduces": 0.5, "reduced": 0.5,
    # price moves
    "plunge": 1.0, "plunges": 1.0, "plunged": 1.0, "plunging": 1.0,
    "tumble": 1.0, "tumbles": 1.0, "tumbled": 1.0,
    "crash": 1.0, "crashes": 1.0, "crashed": 1.0, "crashing": 1.0,
    "sink": 0.9, "sinks": 0.9, "sank": 0.9,
    "fall": 0.6, "falls": 0.6, "fell": 0.6, "falling": 0.6,
    "drop": 0.6, "drops": 0.6, "dropped": 0.6, "dropping": 0.6,
    "decline": 0.6, "declines": 0.6, "declined": 0.6,
    "slip": 0.5, "slips": 0.5, "slipped": 0.5,
    "slump": 0.8, "slumps": 0.8, "slumped": 0.8,
    "loss": 0.6, "losses": 0.6,
    # ratings / sentiment
    "downgrade": 0.9, "downgrades": 0.9, "downgraded": 0.9,
    "bearish": 0.8, "sell": 0.5, "underweight": 0.7,
    "warning": 0.7, "warns": 0.7, "warned": 0.7,
    # business outcomes
    "lawsuit": 0.7, "investigation": 0.6, "probe": 0.6,
    "recall": 0.7, "delay": 0.5, "delays": 0.5, "delayed": 0.6,
    "fraud": 1.0, "bankruptcy": 1.0, "default": 0.9, "halt": 0.6,
    "fire": 0.5, "fired": 0.6, "layoff": 0.6, "layoffs": 0.7,
    "scrap": 0.6, "scraps": 0.6, "scrapped": 0.7,
    "explode": 0.9, "explodes": 0.9, "exploded": 0.9, "explosion": 0.9,
    "scandal": 0.9, "breach": 0.8, "hack": 0.7,
    "failure": 0.8, "fails": 0.7, "failed": 0.7,
    "shrink": 0.5, "shrinks": 0.5,
}

NEGATION_TOKENS: frozenset[str] = frozenset({
    "no", "not", "never", "without", "n't", "neither", "nor",
})

_TOKEN_RE = re.compile(r"[A-Za-z']+")


def _tokenise(text: str) -> list[str]:
    return [t.lower() for t in _TOKEN_RE.findall(text or "")]


def score_headline(text: str) -> float:
    """Return a sentiment score in ``[-1, +1]`` for `text`.

    Implementation
    --------------
    1. Tokenise on word characters.
    2. For each token, look up positive/negative weight.
    3. If any of the previous 3 tokens is a negation cue, flip the sign.
    4. Sum signed weights, normalise by ``max(positive_word_count + negative_word_count, 1)``.
    5. Clip into ``[-1, +1]``.
    """
    if not text:
        return 0.0
    tokens = _tokenise(text)
    if not tokens:
        return 0.0
    score = 0.0
    hits = 0
    n = len(tokens)
    for i, tok in enumerate(tokens):
        weight: float | None = None
        sign = 0
        if tok in POSITIVE_LEX:
            weight = POSITIVE_LEX[tok]
            sign = 1
        elif tok in NEGATIVE_LEX:
            weight = NEGATIVE_LEX[tok]
            sign = -1
        if weight is None:
            continue
        # negation check: any negation cue within the previous 3 tokens
        window = tokens[max(0, i - 3): i]
        if any(w in NEGATION_TOKENS for w in window):
            sign *= -1
        score += sign * weight
        hits += 1
    if hits == 0:
        return 0.0
    norm = score / max(hits, 1)
    if norm > 1.0:
        norm = 1.0
    if norm < -1.0:
        norm = -1.0
    return float(norm)


def score_headlines(texts: Iterable[str]) -> list[float]:
    """Vector form of :func:`score_headline`."""
    return [score_headline(t) for t in texts]


def add_sentiment_column(df: pd.DataFrame, *, text_col: str = "title", out_col: str = "sentiment") -> pd.DataFrame:
    """Convenience: return `df` with a new sentiment column."""
    if df is None or df.empty or text_col not in df.columns:
        if df is None:
            return pd.DataFrame()
        out = df.copy()
        out[out_col] = []
        return out
    out = df.copy()
    out[out_col] = out[text_col].astype(str).map(score_headline)
    return out
