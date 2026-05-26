"""Moteur de scoring — implémente les 4 piliers du short squeeze setup.

Pilier 1 : Structure VAD (4 pts max)
Pilier 2 : Positionnement institutionnel (4 pts max)
Pilier 3 : Divergence VAD vs Institutionnels (2 pts max)
Pilier 4 : Indicateurs techniques squeeze (3 pts BONUS)

Score fondamental : /10
Score technique bonus : /3
Total affiché : X/10 + bonus technique
"""

import logging
from dataclasses import dataclass, field
from typing import Optional

from config.settings import Config

logger = logging.getLogger(__name__)


@dataclass
class PillarScore:
    score: float = 0.0
    max_score: float = 0.0
    details: dict = field(default_factory=dict)


@dataclass
class TickerScore:
    ticker: str
    pillar1: PillarScore = field(default_factory=lambda: PillarScore(max_score=4.0))
    pillar2: PillarScore = field(default_factory=lambda: PillarScore(max_score=4.0))
    pillar3: PillarScore = field(default_factory=lambda: PillarScore(max_score=2.0))
    pillar4: PillarScore = field(default_factory=lambda: PillarScore(max_score=3.0))

    # Données de contexte pour le Telegram
    price: float = 0.0
    market_cap: float = 0.0
    sector: str = ""
    short_float_raw: float = 0.0
    dtc_raw: float = 0.0
    inst_trans_raw: float = 0.0
    squeeze_phase: str = ""

    @property
    def fundamental(self) -> float:
        """Score fondamental /10."""
        return self.pillar1.score + self.pillar2.score + self.pillar3.score

    @property
    def technical_bonus(self) -> float:
        """Score technique bonus /3."""
        return self.pillar4.score

    @property
    def total(self) -> float:
        """Score total = fondamental + bonus technique."""
        return self.fundamental + self.technical_bonus

    @property
    def signal(self) -> str:
        t = self.fundamental  # Le signal est basé sur le fondamental
        bonus = self.technical_bonus
        if t >= 7 or (t >= 6 and bonus >= 2):
            return "🔴 FORT"
        elif t >= 5:
            return "🟡 MODÉRÉ"
        return "⚪ FAIBLE"

    @property
    def passed_pillar1(self) -> bool:
        """Le titre passe le filtre Pilier 1 si score >= 3."""
        return self.pillar1.score >= 3.0


def score_pillar1(data: dict) -> PillarScore:
    """Pilier 1 — Structure des vendeurs à découvert (4 pts max).

    1.1 Short % of Float > 30%        → 1.5 pt
    1.2 Days to Cover > 7             → 1.5 pt
    1.3 Borrow Rate > 30% annualisé   → 0.5 pt (souvent N/D sans Ortex)
    1.4 Utilization > 80%             → 0.5 pt (souvent N/D sans Ortex)
    """
    p = PillarScore(max_score=4.0)

    short_float = data.get("short_float")
    dtc = data.get("days_to_cover")
    borrow_rate = data.get("borrow_rate")
    utilization = data.get("utilization")

    # 1.1 Short Float
    if short_float is not None and short_float > 0.30:
        p.score += 1.5
        p.details["short_float"] = f"✅ {short_float:.1%}"
    elif short_float is not None and short_float > 0.25:
        p.score += 0.75  # demi-point pour 25-30%
        p.details["short_float"] = f"⚠️ {short_float:.1%} (25-30%)"
    else:
        p.details["short_float"] = f"❌ {short_float:.1%}" if short_float else "❌ N/D"

    # 1.2 Days to Cover
    if dtc is not None and dtc > 7:
        p.score += 1.5
        p.details["days_to_cover"] = f"✅ {dtc:.1f}j"
    elif dtc is not None and dtc > 5:
        p.score += 0.75
        p.details["days_to_cover"] = f"⚠️ {dtc:.1f}j (5-7)"
    else:
        p.details["days_to_cover"] = f"❌ {dtc:.1f}j" if dtc else "❌ N/D"

    # 1.3 Borrow Rate (souvent indisponible gratuitement)
    if borrow_rate is not None and borrow_rate > 0.30:
        p.score += 0.5
        p.details["borrow_rate"] = f"✅ {borrow_rate:.1%}"
    else:
        p.details["borrow_rate"] = f"{borrow_rate:.1%}" if borrow_rate else "N/D"

    # 1.4 Utilization
    if utilization is not None and utilization > 0.80:
        p.score += 0.5
        p.details["utilization"] = f"✅ {utilization:.1%}"
    else:
        p.details["utilization"] = f"{utilization:.1%}" if utilization else "N/D"

    return p


def score_pillar2(data: dict) -> PillarScore:
    """Pilier 2 — Positionnement institutionnel (4 pts max).

    2.1 Hausse achats institutionnels (inst_trans > 0 ou holders_delta > 0) → 1.5 pt
    2.2 OI Call en hausse > 20% sur 30j                                     → 1.0 pt
    2.3 Put/Call ratio en baisse (< 0.7)                                     → 1.0 pt
    2.4 Unusual options activity détectée                                     → 0.5 pt
    """
    p = PillarScore(max_score=4.0)

    # 2.1 Institutional accumulation
    inst_trans = data.get("inst_trans_pct")
    holders_delta = data.get("holders_delta")
    inst_accumulating = data.get("accumulating", False)

    if inst_trans is not None and inst_trans > 0:
        p.score += 1.5
        p.details["inst_accumulation"] = f"✅ Inst Trans +{inst_trans:.1%}"
    elif inst_accumulating and holders_delta and holders_delta > 0:
        p.score += 1.5
        p.details["inst_accumulation"] = f"✅ +{holders_delta} holders (EDGAR)"
    elif inst_trans is not None and inst_trans > -0.02:
        p.score += 0.5  # neutre/légèrement négatif
        p.details["inst_accumulation"] = f"⚠️ Inst Trans {inst_trans:+.1%}"
    else:
        p.details["inst_accumulation"] = f"❌ {inst_trans:+.1%}" if inst_trans else "N/D"

    # 2.2 Call OI en hausse
    call_oi_change = data.get("call_oi_change_pct")
    if call_oi_change is not None and call_oi_change > 0.20:
        p.score += 1.0
        p.details["call_oi_change"] = f"✅ +{call_oi_change:.0%}"
    elif call_oi_change is not None and call_oi_change > 0:
        p.score += 0.5
        p.details["call_oi_change"] = f"⚠️ +{call_oi_change:.0%}"
    else:
        p.details["call_oi_change"] = f"{call_oi_change:+.0%}" if call_oi_change else "N/D (1er scan)"

    # 2.3 Put/Call Ratio
    pc_ratio = data.get("put_call_ratio")
    if pc_ratio is not None and pc_ratio < 0.7:
        p.score += 1.0
        p.details["put_call_ratio"] = f"✅ {pc_ratio:.2f} (< 0.7 = bullish)"
    elif pc_ratio is not None and pc_ratio < 1.0:
        p.score += 0.5
        p.details["put_call_ratio"] = f"⚠️ {pc_ratio:.2f}"
    else:
        p.details["put_call_ratio"] = f"❌ {pc_ratio:.2f}" if pc_ratio else "N/D"

    # 2.4 Unusual activity
    if data.get("unusual_activity"):
        p.score += 0.5
        details = data.get("unusual_details", {})
        p.details["unusual_activity"] = (
            f"✅ {details.get('type')} ${details.get('strike')} "
            f"exp {details.get('expiration')} vol/OI={details.get('ratio')}x"
        )
    else:
        p.details["unusual_activity"] = "❌ Aucune"

    return p


def score_pillar3(data: dict) -> PillarScore:
    """Pilier 3 — Divergence VAD vs Institutionnels (2 pts max).

    Signal central : les shorts augmentent PENDANT que les institutionnels accumulent.
    """
    p = PillarScore(max_score=2.0)

    short_float = data.get("short_float", 0) or 0
    inst_trans = data.get("inst_trans_pct")
    inst_accumulating = data.get("accumulating", False)

    # Condition short : SI élevé (proxy pour "shorts actifs")
    shorts_elevated = short_float > 0.20

    # Condition institutional : accumulation détectée
    inst_buying = (inst_trans is not None and inst_trans > 0) or inst_accumulating

    if shorts_elevated and inst_buying:
        p.score = 2.0
        p.details["divergence"] = "✅ DIVERGENCE FORTE — SI élevé + accumulation institutionnelle"
    elif shorts_elevated and inst_trans is not None and inst_trans > -0.02:
        p.score = 1.0
        p.details["divergence"] = "⚠️ Partielle — SI élevé, inst. neutre"
    elif inst_buying and short_float > 0.15:
        p.score = 1.0
        p.details["divergence"] = "⚠️ Partielle — inst. accumulant, SI modéré"
    else:
        p.score = 0.0
        p.details["divergence"] = "❌ Pas de divergence claire"

    return p


def score_pillar4(tech_signals) -> PillarScore:
    """Pilier 4 — Indicateurs techniques squeeze (3 pts BONUS).

    1. TTM Squeeze (compression ou fired)        → 0.75 pt
    2. OBV Divergence haussière                   → 0.5 pt
    3. Keltner Breakout                           → 0.5 pt
    4. Volume Spike (>2.5x SMA)                   → 0.5 pt
    5. RSI Momentum Shift                         → 0.25 pt
    6. VWAP Reclaim                               → 0.5 pt
    """
    p = PillarScore(max_score=3.0)

    if tech_signals is None or not tech_signals.data_available:
        p.details = tech_signals.to_details() if tech_signals else {"technical": "N/D"}
        return p

    # 1. Squeeze (0.75 pt)
    if tech_signals.squeeze_just_fired:
        p.score += 0.75
    elif tech_signals.squeeze_on:
        p.score += 0.5  # compression active = pas encore déclenché

    # 2. OBV Divergence (0.5 pt)
    if tech_signals.obv_divergence:
        p.score += 0.5

    # 3. Keltner Breakout (0.5 pt)
    if tech_signals.keltner_breakout:
        p.score += 0.5

    # 4. Volume Spike (0.5 pt)
    if tech_signals.volume_spike:
        p.score += 0.5

    # 5. RSI Momentum Shift (0.25 pt)
    if tech_signals.rsi_shift:
        p.score += 0.25

    # 6. VWAP Reclaim (0.5 pt — capped to not exceed max)
    if tech_signals.vwap_reclaim:
        p.score += 0.5

    # Cap at max
    p.score = min(p.score, p.max_score)

    # Details
    p.details = tech_signals.to_details()

    return p


def score_ticker(data: dict, tech_signals=None) -> TickerScore:
    """Calcule le score complet pour un ticker."""
    ts = TickerScore(ticker=data.get("ticker", "???"))
    ts.pillar1 = score_pillar1(data)
    ts.pillar2 = score_pillar2(data)
    ts.pillar3 = score_pillar3(data)
    ts.pillar4 = score_pillar4(tech_signals)

    # Context data for Telegram formatting
    ts.price = data.get("price", 0) or 0
    ts.market_cap = data.get("market_cap", 0) or 0
    ts.sector = data.get("sector", "") or ""
    ts.short_float_raw = data.get("short_float", 0) or 0
    ts.dtc_raw = data.get("days_to_cover", 0) or 0
    ts.inst_trans_raw = data.get("inst_trans_pct", 0) or 0
    if tech_signals and tech_signals.data_available:
        ts.squeeze_phase = tech_signals.squeeze_phase

    return ts
