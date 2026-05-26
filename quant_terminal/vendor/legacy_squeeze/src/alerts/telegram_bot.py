"""Module d'alertes Telegram v4 — Channel Edition.

Conçu pour un channel Telegram public/privé avec bot administrateur.
Format HTML lisible, beau, avec barres de progression et émojis.
Inclut les 4 piliers (fondamentaux + technique).

Envoi :
- 1 message HEADER (résumé du scan)
- 1 message DÉTAILLÉ par ticker qualifié
"""

import logging
from datetime import datetime

import requests

from config.settings import Config

logger = logging.getLogger(__name__)

MAX_MSG_LENGTH = 4000


# ═══════════════════════════════════════════════════════════════
#  CORE SEND
# ═══════════════════════════════════════════════════════════════

def send_telegram(message: str) -> bool:
    """Envoie un message au channel Telegram. Chunke auto si trop long."""
    if not Config.telegram_enabled():
        logger.warning(
            "⚠️  Telegram désactivé — TOKEN='%s' CHAT_ID='%s'",
            "SET" if Config.TELEGRAM_BOT_TOKEN else "EMPTY",
            "SET" if Config.TELEGRAM_CHAT_ID else "EMPTY",
        )
        return False

    url = f"https://api.telegram.org/bot{Config.TELEGRAM_BOT_TOKEN}/sendMessage"
    chunks = _chunk_message(message, MAX_MSG_LENGTH)
    all_ok = True

    for i, chunk in enumerate(chunks):
        payload = {
            "chat_id": Config.TELEGRAM_CHAT_ID,
            "text": chunk,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }
        try:
            resp = requests.post(url, json=payload, timeout=15)
            if resp.status_code == 200:
                logger.info(f"✅ Telegram [{i+1}/{len(chunks)}] sent")
                continue

            # Fallback plaintext
            logger.warning("Telegram HTML failed (%d): %s", resp.status_code, resp.text[:300])
            payload["text"] = _strip_html(chunk)
            payload.pop("parse_mode", None)
            resp2 = requests.post(url, json=payload, timeout=15)
            if resp2.status_code != 200:
                logger.error("❌ Telegram FAILED: %d %s", resp2.status_code, resp2.text[:300])
                all_ok = False

        except requests.RequestException as e:
            logger.error(f"❌ Telegram error: {e}")
            all_ok = False

    return all_ok


# ═══════════════════════════════════════════════════════════════
#  FORMATTING — CHANNEL EDITION
# ═══════════════════════════════════════════════════════════════

def _progress_bar(score: float, max_score: float, length: int = 10) -> str:
    """Barre de progression visuelle : ████░░░░░░ 2.5/4."""
    if max_score <= 0:
        return "░" * length
    filled = int(round((score / max_score) * length))
    filled = min(filled, length)
    return "█" * filled + "░" * (length - filled)


def _score_emoji(score: float, max_score: float) -> str:
    """Emoji selon le ratio score/max."""
    ratio = score / max_score if max_score > 0 else 0
    if ratio >= 0.75:
        return "🟢"
    elif ratio >= 0.5:
        return "🟡"
    elif ratio >= 0.25:
        return "🟠"
    return "🔴"


def _fmt_mcap(mcap: float) -> str:
    if not mcap:
        return "N/D"
    if mcap >= 1e9:
        return f"${mcap/1e9:.1f}B"
    return f"${mcap/1e6:.0f}M"


def _fmt_pct(val: float, show_sign: bool = False) -> str:
    if val is None:
        return "N/D"
    if show_sign:
        return f"{val:+.1%}"
    return f"{val:.1%}"


def format_header(qualifying_scores: list) -> str:
    """Message HEADER — résumé du scan pour le channel."""
    now = datetime.now().strftime("%d/%m/%Y %H:%M")

    forts = [s for s in qualifying_scores if s.signal.startswith("🔴")]
    moderes = [s for s in qualifying_scores if s.signal.startswith("🟡")]

    lines = [
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "🔍 <b>SHORT SQUEEZE SCANNER</b>",
        f"📅 {now}",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "",
    ]

    if not qualifying_scores:
        lines.append("📭 Aucun setup qualifié aujourd'hui.")
        lines.append("")
        lines.append("<i>Score minimum requis : 5.0/10</i>")
        return "\n".join(lines)

    lines.append(f"📊 <b>{len(qualifying_scores)} setup(s)</b> détectés\n")

    if forts:
        lines.append("🔴 <b>SIGNAUX FORTS</b>")
        for s in forts:
            phase = f"  {s.squeeze_phase}" if s.squeeze_phase else ""
            lines.append(
                f"   <b>{s.ticker}</b>  "
                f"{s.fundamental:.1f}/10 +{s.technical_bonus:.1f}⚡{phase}"
            )
        lines.append("")

    if moderes:
        lines.append("🟡 <b>À SURVEILLER</b>")
        for s in moderes:
            phase = f"  {s.squeeze_phase}" if s.squeeze_phase else ""
            lines.append(
                f"   <b>{s.ticker}</b>  "
                f"{s.fundamental:.1f}/10 +{s.technical_bonus:.1f}⚡{phase}"
            )
        lines.append("")

    lines.append("👇 <i>Détails par ticker ci-dessous</i>")

    return "\n".join(lines)


def format_ticker_detail(score, llm_analysis=None) -> str:
    """Message DÉTAILLÉ pour un ticker — version channel public.

    Prend un TickerScore + optionnellement un LLMAnalysis.
    """
    # ── En-tête ──
    phase = score.squeeze_phase or "—"
    price_str = f"${score.price:.2f}" if score.price else "N/D"
    mcap_str = _fmt_mcap(score.market_cap)
    sector = score.sector or "N/D"

    lines = [
        f"{'─' * 30}",
        f"{score.signal}  <b>{score.ticker}</b>",
        f"{'─' * 30}",
        "",
        f"💰 {price_str}  ·  🏢 {sector}  ·  📊 {mcap_str}",
        f"📍 Phase: <b>{phase}</b>",
        "",
    ]

    # ── Score global ──
    fund = score.fundamental
    tech = score.technical_bonus
    total_bar = _progress_bar(fund, 10, 15)
    lines.append(f"<b>Score fondamental</b>")
    lines.append(f"{total_bar}  {fund:.1f}/10")
    if tech > 0:
        tech_bar = _progress_bar(tech, 3, 8)
        lines.append(f"<b>Bonus technique</b>")
        lines.append(f"{tech_bar}  +{tech:.1f}/3 ⚡")
    lines.append("")

    # ── Pilier 1 — VAD ──
    p1 = score.pillar1
    e1 = _score_emoji(p1.score, p1.max_score)
    lines.append(f"{e1} <b>PILIER 1 — Structure VAD</b>  ({p1.score:.1f}/{p1.max_score:.0f})")
    bar1 = _progress_bar(p1.score, p1.max_score)
    lines.append(f"   {bar1}")
    for k, v in p1.details.items():
        label = _humanize_key(k)
        lines.append(f"   · {label}: {_escape_html(v)}")
    lines.append("")

    # ── Pilier 2 — Institutionnels ──
    p2 = score.pillar2
    e2 = _score_emoji(p2.score, p2.max_score)
    lines.append(f"{e2} <b>PILIER 2 — Positionnement Institutionnel</b>  ({p2.score:.1f}/{p2.max_score:.0f})")
    bar2 = _progress_bar(p2.score, p2.max_score)
    lines.append(f"   {bar2}")
    for k, v in p2.details.items():
        label = _humanize_key(k)
        lines.append(f"   · {label}: {_escape_html(v)}")
    lines.append("")

    # ── Pilier 3 — Divergence ──
    p3 = score.pillar3
    e3 = _score_emoji(p3.score, p3.max_score)
    lines.append(f"{e3} <b>PILIER 3 — Divergence VAD vs Institutionnels</b>  ({p3.score:.1f}/{p3.max_score:.0f})")
    bar3 = _progress_bar(p3.score, p3.max_score)
    lines.append(f"   {bar3}")
    for k, v in p3.details.items():
        label = _humanize_key(k)
        lines.append(f"   · {label}: {_escape_html(v)}")
    lines.append("")

    # ── Pilier 4 — Technique ──
    p4 = score.pillar4
    if p4.details:
        e4 = _score_emoji(p4.score, p4.max_score)
        lines.append(f"{e4} <b>PILIER 4 — Indicateurs Techniques</b>  ({p4.score:.1f}/{p4.max_score:.0f})")
        bar4 = _progress_bar(p4.score, p4.max_score)
        lines.append(f"   {bar4}")
        for k, v in p4.details.items():
            label = _humanize_key(k)
            lines.append(f"   · {label}: {_escape_html(v)}")
        lines.append("")

    # ── Analyse LLM (si disponible) ──
    if llm_analysis is not None:
        lines.append(llm_analysis.to_telegram_html())
        lines.append("")

    # ── Résumé action ──
    lines.append(_action_summary(score, llm_analysis))

    return "\n".join(lines)


def _action_summary(score, llm_analysis=None) -> str:
    """Résumé actionnable basé sur le scoring + LLM."""
    fund = score.fundamental
    tech = score.technical_bonus
    ai = llm_analysis.ai_conviction if llm_analysis and not llm_analysis.is_degraded else None

    # Si LLM a donné un score de conviction
    if ai is not None:
        if ai >= 7 and fund >= 6:
            return (
                "🎯 <b>CONVICTION HAUTE</b>\n"
                "Quant + IA convergent. Setup actionnable."
            )
        elif not llm_analysis.sanity_passed:
            return (
                "⚠️ <b>SIGNAL SUSPECT</b>\n"
                "L'IA a identifié des red flags. Prudence."
            )
        elif ai < 4:
            return (
                "🛑 <b>IA SCEPTIQUE</b>\n"
                "Score quant correct mais l'analyse qualitative ne suit pas."
            )

    # Fallback scoring only
    if fund >= 7 and tech >= 2:
        return (
            "🎯 <b>CONVICTION HAUTE</b>\n"
            "Le fondamental ET le technique convergent. Setup rare."
        )
    elif fund >= 7:
        return (
            "⚠️ <b>FONDAMENTAL FORT</b>\n"
            "Structure squeeze solide. Attendre confirmation technique."
        )
    elif fund >= 5 and tech >= 2:
        return (
            "🔎 <b>TECHNIQUE ACTIF</b>\n"
            "Les indicateurs bougent. Surveiller catalyseur fondamental."
        )
    else:
        return (
            "📋 <b>WATCHLIST</b>\n"
            "Setup en construction. À surveiller pour évolution."
        )


def _humanize_key(key: str) -> str:
    """Rend les clés de détails lisibles."""
    mapping = {
        "short_float": "Short Float",
        "days_to_cover": "Days to Cover",
        "borrow_rate": "Borrow Rate",
        "utilization": "Utilization",
        "inst_accumulation": "Accumulation Inst.",
        "call_oi_change": "Δ Call OI",
        "put_call_ratio": "Put/Call Ratio",
        "unusual_activity": "Activité Inhabituelle",
        "divergence": "Divergence",
        "squeeze": "TTM Squeeze",
        "obv": "On-Balance Volume",
        "keltner": "Keltner Breakout",
        "volume": "Volume Spike",
        "rsi": "RSI Momentum",
        "vwap": "VWAP Reclaim",
        "technical": "Technique",
    }
    return mapping.get(key, key.replace("_", " ").title())


# ═══════════════════════════════════════════════════════════════
#  PUBLIC API
# ═══════════════════════════════════════════════════════════════

def send_scan_results_rich(qualifying_scores: list, llm_analyses: dict = None) -> bool:
    """Envoie le header + 1 message détaillé par ticker au channel.

    Args:
        qualifying_scores: liste de TickerScore qualifiés
        llm_analyses: dict ticker -> LLMAnalysis (optionnel)
    """
    llm_analyses = llm_analyses or {}

    # Message 1 : Header du scan
    header = format_header(qualifying_scores)
    ok = send_telegram(header)

    # Messages détaillés
    for score in qualifying_scores:
        llm = llm_analyses.get(score.ticker)
        detail = format_ticker_detail(score, llm)
        send_telegram(detail)

    return ok


# Legacy compat
def send_scan_results(score_dicts: list[dict]) -> bool:
    """Fallback si appelé avec des dicts au lieu de TickerScore."""
    return send_scan_results_rich(score_dicts)


# ═══════════════════════════════════════════════════════════════
#  DIAGNOSTIC
# ═══════════════════════════════════════════════════════════════

def test_connection() -> None:
    """Diagnostic Telegram — python -m src.main --test-telegram"""
    print("=" * 50)
    print("  DIAGNOSTIC TELEGRAM")
    print("=" * 50)

    token = Config.TELEGRAM_BOT_TOKEN
    if not token:
        print("❌ TELEGRAM_BOT_TOKEN est VIDE dans .env")
        print("   → Crée un bot via @BotFather sur Telegram")
        return
    masked = token[:8] + "..." + token[-5:] if len(token) > 15 else "***"
    print(f"✅ Token : {masked}")

    chat_id = Config.TELEGRAM_CHAT_ID
    if not chat_id:
        print("❌ TELEGRAM_CHAT_ID est VIDE dans .env")
        print("   → Pour un channel: utilise @channel_username ou l'ID négatif")
        print("   → Pour trouver l'ID: forward un message du channel à @userinfobot")
        return
    print(f"✅ Chat/Channel ID : {chat_id}")

    # Test getMe
    print("\n--- Test connexion API ---")
    url = f"https://api.telegram.org/bot{token}/getMe"
    try:
        resp = requests.get(url, timeout=10)
        data = resp.json()
        if data.get("ok"):
            bot = data["result"]
            print(f"✅ Bot : @{bot.get('username')} ({bot.get('first_name')})")
        else:
            print(f"❌ Token INVALIDE : {data}")
            return
    except Exception as e:
        print(f"❌ Erreur réseau : {e}")
        return

    # Test envoi
    print(f"\n--- Test envoi vers {chat_id} ---")
    test_msg = (
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "🔍 <b>SHORT SQUEEZE SCANNER</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "\n"
        "✅ <b>Test de connexion réussi !</b>\n"
        "\n"
        f"📡 Channel : <code>{chat_id}</code>\n"
        "📊 Les alertes fonctionnent.\n"
        "\n"
        f"█████████░  Score test: 9.0/10\n"
        "\n"
        "<i>Ceci est un message de test.</i>"
    )
    ok = send_telegram(test_msg)
    if ok:
        print("✅ Message envoyé ! Vérifie le channel.")
    else:
        print("❌ Échec. Causes possibles :")
        print("   1. Le bot n'est pas admin du channel")
        print("   2. Le CHAT_ID est incorrect")
        print("   3. Pour un channel: utilise le format @nom_du_channel ou -100XXXXXXXXXX")


# ═══════════════════════════════════════════════════════════════
#  HELPERS
# ═══════════════════════════════════════════════════════════════

def _strip_html(text: str) -> str:
    import re
    return re.sub(r'<[^>]+>', '', text)


def _escape_html(text: str) -> str:
    """Échappe les < et > dans le texte pour éviter les erreurs HTML Telegram.

    N'échappe PAS ceux qui font partie de nos propres tags <b>, <i>, <code>.
    """
    # Convertir toutes les occurrences de < et > en entities
    result = str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return result


def _chunk_message(text: str, max_len: int) -> list[str]:
    if len(text) <= max_len:
        return [text]
    chunks, current = [], ""
    for line in text.split("\n"):
        if len(current) + len(line) + 1 > max_len:
            if current:
                chunks.append(current)
            current = line
        else:
            current = current + "\n" + line if current else line
    if current:
        chunks.append(current)
    return chunks
