"""Couche LLM — Analyse qualitative des candidats short squeeze via Gemini.

Modèle : gemini-2.5-flash (configurable via LLM_MODEL)
SDK : google-genai avec Google Search grounding

5 missions du LLM (cf. prompt maître) :
1. Contextualisation du catalyst
2. Sanity check du signal (faux positif ?)
3. Risk assessment qualitatif
4. Score de conviction IA (0-10)
5. Synthèse pour l'alerte Telegram

Contraintes :
- 1 seul appel API par candidat (tout en une requête)
- Google Search grounding activé (le modèle décide quand chercher)
- Timeout 45s, retry x2 avec backoff exponentiel
- Mode dégradé si API indisponible (le pipeline ne crash jamais)
- Cache TTL 4h par ticker (évite les doublons intra-journée)
- Traitement séquentiel (pas de parallélisme → pas de rate limit)
"""

import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional

from config.settings import Config

logger = logging.getLogger(__name__)

# ─── Cache en mémoire (TTL 4h) ──────────────────────────────

_cache: dict[str, tuple[datetime, dict]] = {}
CACHE_TTL = timedelta(hours=float(Config.CACHE_TTL_HOURS) if hasattr(Config, "CACHE_TTL_HOURS") else 4)


def _cache_get(ticker: str) -> Optional[dict]:
    if ticker in _cache:
        ts, data = _cache[ticker]
        if datetime.now() - ts < CACHE_TTL:
            logger.info(f"LLM cache hit for {ticker}")
            return data
        del _cache[ticker]
    return None


def _cache_set(ticker: str, data: dict) -> None:
    _cache[ticker] = (datetime.now(), data)


# ─── Data Classes ────────────────────────────────────────────

@dataclass
class LLMAnalysis:
    """Résultat de l'analyse LLM pour un candidat."""
    ticker: str
    catalyst: str = ""
    catalyst_type: str = "none"          # earnings|regulatory|social|technical|none
    catalyst_strength: str = "none"      # strong|moderate|weak|none
    sanity_check: str = ""
    sanity_passed: bool = True
    key_risks: list[str] = field(default_factory=list)
    ai_conviction: float = 0.0          # 0-10
    reasoning: str = ""
    is_degraded: bool = False            # True si l'API a échoué
    error: str = ""
    timestamp: str = ""

    @property
    def conviction_emoji(self) -> str:
        if self.ai_conviction >= 7:
            return "🟢"
        elif self.ai_conviction >= 5:
            return "🟡"
        elif self.ai_conviction >= 3:
            return "🟠"
        return "🔴"

    def to_telegram_html(self) -> str:
        """Formate l'analyse LLM pour Telegram (HTML)."""
        if self.is_degraded:
            return (
                "🤖 <b>ANALYSE IA</b>\n"
                f"   ⚠️ Indisponible ({self.error})\n"
                "   <i>Score basé uniquement sur les métriques quantitatives.</i>"
            )

        lines = [
            f"🤖 <b>ANALYSE IA</b>  {self.conviction_emoji} {self.ai_conviction:.1f}/10",
        ]

        # Catalyst
        if self.catalyst and self.catalyst_type != "none":
            strength_emoji = {"strong": "🔥", "moderate": "⚡", "weak": "💨"}.get(
                self.catalyst_strength, "—"
            )
            lines.append(f"   {strength_emoji} Catalyst: {self.catalyst}")

        # Sanity check
        if self.sanity_passed:
            lines.append(f"   ✅ Sanity: {self.sanity_check}")
        else:
            lines.append(f"   ⚠️ Sanity: {self.sanity_check}")

        # Risks
        if self.key_risks:
            lines.append("   ⚠️ Risques:")
            for risk in self.key_risks[:3]:
                lines.append(f"      · {risk}")

        # Reasoning
        if self.reasoning:
            lines.append(f"   💭 {self.reasoning}")

        return "\n".join(lines)


# ─── System Prompt (conforme au prompt maître) ───────────────

SYSTEM_PROMPT = """Tu es un analyste spécialisé dans les short squeezes et les situations spéciales sur les marchés actions US (NYSE/NASDAQ).

Tu analyses des candidats PRÉ-SÉLECTIONNÉS par un algorithme quantitatif multi-piliers. Les métriques quantitatives sont déjà calculées — ton rôle est d'apporter l'ANALYSE QUALITATIVE que les chiffres seuls ne capturent pas.

Tu as accès à Google Search pour tes recherches. Utilise-le de façon chirurgicale pour :
- Identifier le catalyst récent (earnings, FDA, short seller report, gamma squeeze, sentiment WSB)
- Vérifier les risques de dilution (historique d'émissions, ATM facility, convertibles)
- Évaluer le sentiment social si pertinent

Tes 5 missions EXACTES :

MISSION 1 — Contextualisation du catalyst
Identifier si un vrai déclencheur existe : earnings surprise, annonce FDA/réglementaire, short seller report (Hindenburg, Citron), gamma squeeze options, sentiment Reddit/WSB, momentum institutionnel.

MISSION 2 — Sanity check du signal
Challenger le score AVANT l'alerte pour réduire les faux positifs :
- Le squeeze est-il déjà amorcé (trop tard) ?
- La liquidité est-elle suffisante pour un trade réaliste ?
- La news est-elle déjà pricée ?
- Y a-t-il un biais de données probable (yfinance lag sur short interest) ?

MISSION 3 — Risk assessment qualitatif
Évaluer les risques que les métriques ne voient pas :
- Risque de dilution (historique d'émissions, ATM facility active)
- Qualité du management (insider selling, track record)
- Structure capitalistique (convertibles, warrants)
- Risque réglementaire ou sectoriel spécifique

MISSION 4 — Score de conviction IA (0-10)
Score DISTINCT du score quantitatif. Sois SCEPTIQUE par défaut — un bon score quant ne suffit pas.
0-3 = red flags majeurs, signal probablement faux positif
4-5 = signal douteux, manque de catalyst
6-7 = signal crédible avec catalyst identifié
8-10 = conviction forte, convergence quant/qualitative rare

MISSION 5 — Synthèse
Justifie ta conviction en 2-3 phrases maximum.

FORMAT DE RÉPONSE — Tu DOIS répondre UNIQUEMENT en JSON valide, sans markdown, sans backticks, sans preamble :
{
  "catalyst": "Description concise du catalyst principal (1 phrase)",
  "catalyst_type": "earnings|regulatory|social|technical|none",
  "catalyst_strength": "strong|moderate|weak|none",
  "sanity_check": "Le signal est-il fiable ? Résultat en 1-2 phrases",
  "sanity_passed": true,
  "key_risks": ["Risque 1", "Risque 2", "Risque 3"],
  "ai_conviction": 7.5,
  "reasoning": "Justification du score en 2-3 phrases"
}"""


# ─── Core Analysis ───────────────────────────────────────────

def analyze_candidate(score) -> LLMAnalysis:
    """Analyse LLM d'un candidat TickerScore.

    Retourne un LLMAnalysis. En cas d'échec API, retourne un résultat dégradé
    (is_degraded=True) — le pipeline ne crash jamais.
    """
    ticker = score.ticker
    result = LLMAnalysis(ticker=ticker, timestamp=datetime.now().isoformat())

    # Check cache
    cached = _cache_get(ticker)
    if cached:
        for k, v in cached.items():
            if hasattr(result, k):
                setattr(result, k, v)
        result.timestamp = datetime.now().isoformat()
        return result

    # Check si API configurée
    if not Config.llm_enabled():
        result.is_degraded = True
        result.error = "GEMINI_API_KEY non configurée"
        return result

    # Construire le user prompt
    user_prompt = _build_user_prompt(score)

    # Appel API avec retry
    raw = _call_gemini(user_prompt)
    if raw is None:
        result.is_degraded = True
        result.error = "API indisponible après 2 tentatives"
        return result

    # Parser la réponse
    parsed = _parse_response(raw)
    if parsed is None:
        result.is_degraded = True
        result.error = "Réponse LLM invalide (JSON parsing failed)"
        logger.error(f"Raw LLM response for {ticker}: {raw[:500]}")
        return result

    # Remplir le résultat
    result.catalyst = str(parsed.get("catalyst", ""))[:200]
    result.catalyst_type = parsed.get("catalyst_type", "none")
    result.catalyst_strength = parsed.get("catalyst_strength", "none")
    result.sanity_check = str(parsed.get("sanity_check", ""))[:200]
    result.sanity_passed = bool(parsed.get("sanity_passed", True))
    result.key_risks = [str(r)[:100] for r in parsed.get("key_risks", [])][:3]
    result.ai_conviction = min(max(float(parsed.get("ai_conviction", 0)), 0), 10)
    result.reasoning = str(parsed.get("reasoning", ""))[:300]

    # Cache
    _cache_set(ticker, parsed)

    return result


def analyze_batch(qualifying_scores: list) -> dict[str, LLMAnalysis]:
    """Analyse séquentielle d'un batch de candidats qualifiés.

    Retourne un dict ticker -> LLMAnalysis.
    Séquentiel pour respecter les rate limits Gemini.
    """
    results = {}
    for i, score in enumerate(qualifying_scores):
        logger.info(f"LLM analyzing [{i+1}/{len(qualifying_scores)}] {score.ticker}")
        results[score.ticker] = analyze_candidate(score)
        # Pause entre les appels
        if i < len(qualifying_scores) - 1:
            time.sleep(1.5)
    return results


# ─── Prompt Builder ──────────────────────────────────────────

def _build_user_prompt(score) -> str:
    """Construit le prompt utilisateur à partir du TickerScore."""
    p1 = score.pillar1.details
    p2 = score.pillar2.details
    p3 = score.pillar3.details
    p4 = score.pillar4.details

    mcap_str = f"${score.market_cap/1e9:.1f}B" if score.market_cap >= 1e9 else f"${score.market_cap/1e6:.0f}M"

    prompt = f"""Analyse ce candidat short squeeze. Utilise Google Search pour identifier le catalyst et les risques.

═══ TICKER ═══
{score.ticker}
Prix: ${score.price:.2f} | Market Cap: {mcap_str} | Secteur: {score.sector}

═══ SCORING QUANTITATIF ═══
Score fondamental: {score.fundamental:.1f}/10
Bonus technique: {score.technical_bonus:.1f}/3
Signal: {score.signal}
Phase technique: {score.squeeze_phase}

═══ PILIER 1 — Structure VAD ({score.pillar1.score:.1f}/4) ═══
{chr(10).join(f'  {k}: {v}' for k, v in p1.items())}

═══ PILIER 2 — Positionnement Institutionnel ({score.pillar2.score:.1f}/4) ═══
{chr(10).join(f'  {k}: {v}' for k, v in p2.items())}

═══ PILIER 3 — Divergence ({score.pillar3.score:.1f}/2) ═══
{chr(10).join(f'  {k}: {v}' for k, v in p3.items())}

═══ PILIER 4 — Technique ({score.pillar4.score:.1f}/3) ═══
{chr(10).join(f'  {k}: {v}' for k, v in p4.items())}

═══ INSTRUCTIONS ═══
1. Recherche le catalyst récent pour {score.ticker} (news, earnings, FDA, short seller report, WSB)
2. Évalue si ce signal est actionnable ou faux positif
3. Identifie les risques hors métriques (dilution, management, structure cap, réglementaire)
4. Donne un score de conviction 0-10 (sois sceptique par défaut)

Réponds UNIQUEMENT en JSON valide, sans backticks ni preamble."""

    return prompt


# ─── Gemini API Call ─────────────────────────────────────────

def _call_gemini(user_prompt: str, max_retries: int = 2) -> Optional[str]:
    """Appel Gemini API avec Google Search grounding, retry et backoff."""
    try:
        from google import genai
        from google.genai import types
    except ImportError:
        logger.error("google-genai SDK not installed — pip install google-genai")
        return None

    client = genai.Client(api_key=Config.GEMINI_API_KEY)

    # Google Search grounding tool
    search_tool = types.Tool(google_search=types.GoogleSearch())

    config = types.GenerateContentConfig(
        system_instruction=SYSTEM_PROMPT,
        tools=[search_tool],
        temperature=0.3,   # Bas pour des réponses factuelles et cohérentes
        max_output_tokens=4096,
    )

    for attempt in range(max_retries):
        try:
            response = client.models.generate_content(
                model=Config.LLM_MODEL,
                contents=user_prompt,
                config=config,
            )

            # Extraire le texte — Gemini peut retourner plusieurs parts
            all_text = []

            if response.candidates:
                for candidate in response.candidates:
                    if candidate.content and candidate.content.parts:
                        for part in candidate.content.parts:
                            if hasattr(part, "text") and part.text:
                                all_text.append(part.text)

            # Fallback via .text property
            if not all_text and response.text:
                all_text.append(response.text)

            if all_text:
                full_text = "\n".join(all_text)
                logger.debug(f"Gemini response length: {len(full_text)} chars")
                return full_text

            logger.warning(f"Gemini returned empty response (attempt {attempt+1})")

        except Exception as e:
            error_msg = str(e)
            # Extraire le code HTTP si disponible
            http_code = ""
            if "429" in error_msg:
                http_code = " [RATE LIMIT 429]"
            elif "500" in error_msg:
                http_code = " [SERVER ERROR 500]"
            elif "403" in error_msg:
                http_code = " [FORBIDDEN 403 — vérifier API key]"
            elif "400" in error_msg:
                http_code = " [BAD REQUEST 400]"

            logger.warning(
                f"Gemini API error{http_code} (attempt {attempt+1}/{max_retries}): {error_msg[:300]}"
            )
            if attempt < max_retries - 1:
                wait = (attempt + 1) * 5  # 5s, 10s
                logger.info(f"Retrying in {wait}s...")
                time.sleep(wait)

    return None


# ─── Response Parser ─────────────────────────────────────────

def _parse_response(raw_text: str) -> Optional[dict]:
    """Parse la réponse JSON du LLM. Tolère backticks, preamble, thinking, truncation."""
    text = raw_text.strip()

    # Nettoyer backticks markdown
    if "```" in text:
        # Extraire le contenu entre ```json et ```
        import re
        json_block = re.search(r'```(?:json)?\s*\n?(.*?)```', text, re.DOTALL)
        if json_block:
            text = json_block.group(1).strip()
        else:
            # Retirer les backticks isolés
            lines = text.split("\n")
            lines = [l for l in lines if not l.strip().startswith("```")]
            text = "\n".join(lines).strip()

    # Chercher le JSON entre { et }
    try:
        start = text.index("{")
        end = text.rindex("}") + 1
        json_str = text[start:end]
        data = json.loads(json_str)

        # Validation minimale
        if not isinstance(data, dict):
            return None
        if "ai_conviction" not in data:
            logger.warning("LLM response missing ai_conviction field")
            data["ai_conviction"] = 0

        return data

    except (ValueError, json.JSONDecodeError) as e:
        # Tentative de réparation : JSON tronqué
        try:
            start = text.index("{")
            json_str = text[start:].rstrip()

            # Compter les accolades/crochets non fermés
            open_braces = json_str.count("{") - json_str.count("}")
            open_brackets = json_str.count("[") - json_str.count("]")

            if open_braces > 0 or open_brackets > 0:
                # Retirer le dernier champ incomplet si la dernière ligne est tronquée
                lines = json_str.rstrip().split("\n")
                # Essayer de fermer en retirant les lignes depuis la fin
                for trim in range(min(3, len(lines))):
                    attempt = "\n".join(lines[:len(lines) - trim]).rstrip().rstrip(",")
                    ob = attempt.count("{") - attempt.count("}")
                    olb = attempt.count("[") - attempt.count("]")
                    attempt += "]" * max(0, olb) + "}" * max(0, ob)
                    try:
                        data = json.loads(attempt)
                        if isinstance(data, dict):
                            logger.info(f"Repaired truncated JSON (trimmed {trim} lines)")
                            if "ai_conviction" not in data:
                                data["ai_conviction"] = 0
                            return data
                    except json.JSONDecodeError:
                        continue

        except Exception:
            pass

        logger.error(f"JSON parse failed: {e}\nRaw text: {text[:500]}")
        return None
