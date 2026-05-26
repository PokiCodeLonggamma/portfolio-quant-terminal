"""Short Squeeze Scanner — Pipeline principal.

Orchestre les 3 couches de données et produit le scoring final.
Peut tourner en one-shot (CLI) ou en scheduler (cron/schedule).

Usage:
    python -m src.main              # Scan one-shot
    python -m src.main --schedule   # Scheduler quotidien 18h30 EST
    python -m src.main --ticker HIMS  # Scan un seul ticker
"""

import sys
import argparse
import logging
from datetime import date

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich import box

from config.settings import Config
from src.storage.database import (
    init_db,
    upsert_short_interest,
    upsert_institutional,
    upsert_options,
    upsert_score,
)
from src.scrapers.finviz_scraper import screen_high_short_interest, get_ticker_details
from src.scrapers.edgar_13f import get_institutional_delta, check_13d_activity
from src.scrapers.options_flow import get_options_data
from src.analysis.scoring import score_ticker, TickerScore
from src.analysis.technical import analyze_technical
from src.alerts.telegram_bot import send_scan_results_rich, test_connection as test_telegram

console = Console()
logger = logging.getLogger("scanner")


def setup_logging(verbose: bool = False) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    # Réduire le bruit de yfinance et requests
    logging.getLogger("yfinance").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("peewee").setLevel(logging.WARNING)


def scan_single_ticker(ticker: str) -> TickerScore:
    """Scan complet d'un ticker unique — utile pour le debug ou l'analyse ponctuelle."""
    today = date.today().isoformat()

    console.print(f"\n[bold cyan]Scanning {ticker}...[/]")

    # 1. Données Finviz
    console.print("  ├─ Finviz details...", style="dim")
    details = get_ticker_details(ticker)

    # 2. EDGAR 13F
    console.print("  ├─ SEC EDGAR 13F...", style="dim")
    edgar_data = get_institutional_delta(ticker)

    # 3. Options flow
    console.print("  ├─ Options flow...", style="dim")
    options = get_options_data(ticker)

    # 4. Fusion des données
    merged = {**details, **edgar_data, **options}

    # 5. Technical analysis
    console.print("  ├─ Technical analysis...", style="dim")
    tech_signals = analyze_technical(ticker)

    # 6. Vérifier les 13D récents (accumulations agressives >5%)
    console.print("  └─ 13D activity check...", style="dim")
    recent_13d = check_13d_activity(ticker, days_back=90)
    if recent_13d:
        merged["has_13d_activity"] = True
        merged["recent_13d"] = recent_13d

    # 7. Scoring
    score = score_ticker(merged, tech_signals)

    # 7. Persistance
    upsert_short_interest(ticker, details, today)
    upsert_institutional(ticker, {
        "inst_own_pct": details.get("inst_own_pct"),
        "inst_trans_pct": details.get("inst_trans_pct"),
        "num_holders": edgar_data.get("holders_current"),
    }, today)
    upsert_options(ticker, options, today)
    upsert_score(ticker, {
        "pillar1": score.pillar1.score,
        "pillar2": score.pillar2.score,
        "pillar3": score.pillar3.score,
        "total_score": score.total,
        "signal": score.signal,
    }, today)

    return score


def run_full_scan() -> list[TickerScore]:
    """Pipeline complet : screening → enrichissement → scoring → alertes."""
    today = date.today().isoformat()

    # ── Phase 1 : Screening Finviz ──
    console.print(Panel(
        "[bold]Phase 1 — Screening Finviz[/]\n"
        f"Seuil Short Float : {Config.MIN_SHORT_FLOAT:.0%}",
        title="🔍 Short Squeeze Scanner",
        border_style="cyan",
    ))

    tickers = screen_high_short_interest(Config.MIN_SHORT_FLOAT)
    if not tickers:
        console.print("[red]Aucun ticker trouvé par le screener Finviz.[/]")
        return []

    console.print(f"[green]{len(tickers)} tickers identifiés[/]")

    # ── Phase 2 : Enrichissement et scoring ──
    console.print(Panel(
        "[bold]Phase 2 — Enrichissement & Scoring[/]",
        border_style="cyan",
    ))

    all_scores: list[TickerScore] = []

    for i, ticker in enumerate(tickers):
        console.print(f"\n[bold][{i+1}/{len(tickers)}] {ticker}[/]")

        try:
            # Finviz details
            details = get_ticker_details(ticker)

            # Filtre market cap
            mcap = details.get("market_cap") or 0
            if mcap < Config.MIN_MARKET_CAP:
                console.print(f"  [dim]Skip — MCap ${mcap/1e6:.0f}M < ${Config.MIN_MARKET_CAP/1e6:.0f}M[/]")
                continue

            # Quick Pilier 1 pre-check avant les appels coûteux
            sf = details.get("short_float") or 0
            dtc = details.get("days_to_cover") or 0
            if sf < 0.15 and dtc < 3:
                console.print(f"  [dim]Skip — SI trop faible ({sf:.0%}, DTC {dtc:.1f}j)[/]")
                continue

            # EDGAR (coûteux en temps — uniquement si le pre-check passe)
            edgar_data = get_institutional_delta(ticker)

            # Options
            options = get_options_data(ticker)

            # Technical analysis
            tech_signals = analyze_technical(ticker)

            # Merge et score
            merged = {**details, **edgar_data, **options}
            score = score_ticker(merged, tech_signals)

            # Persist
            upsert_short_interest(ticker, details, today)
            upsert_institutional(ticker, {
                "inst_own_pct": details.get("inst_own_pct"),
                "inst_trans_pct": details.get("inst_trans_pct"),
                "num_holders": edgar_data.get("holders_current"),
            }, today)
            upsert_options(ticker, options, today)
            upsert_score(ticker, {
                "pillar1": score.pillar1.score,
                "pillar2": score.pillar2.score,
                "pillar3": score.pillar3.score,
                "total_score": score.total,
                "signal": score.signal,
            }, today)

            all_scores.append(score)

            # Affichage inline
            color = "red" if score.total >= 7 else "yellow" if score.total >= 5 else "dim"
            phase = score.squeeze_phase or ""
            console.print(
                f"  → {score.signal} {score.fundamental:.1f}+{score.technical_bonus:.1f} "
                f"(P1:{score.pillar1.score:.1f} P2:{score.pillar2.score:.1f} "
                f"P3:{score.pillar3.score:.1f} P4:{score.pillar4.score:.1f}) {phase}",
                style=color,
            )

        except Exception as e:
            logger.error(f"Error scanning {ticker}: {e}")
            continue

    # ── Phase 3 : Résultats ──
    all_scores.sort(key=lambda s: s.total, reverse=True)
    qualifying = [s for s in all_scores if s.total >= Config.MIN_SCORE_ALERT]

    display_results(all_scores)

    # ── Phase 4 : Alertes (quantitatif uniquement — LLM sur demande) ──
    if qualifying and Config.telegram_enabled():
        send_scan_results_rich(qualifying)
        console.print("[green]✓ Alerte Telegram envoyée[/]")
        if Config.llm_enabled():
            console.print("[dim]💡 Pour l'analyse IA : python -m src.main --analyze-scan[/]")
    elif qualifying and not Config.telegram_enabled():
        console.print("[yellow]⚠ Telegram non configuré — pas d'alerte envoyée[/]")

    # ── Phase 5 : Export fichier ──
    export_path = Config.ROOT / "data" / f"scan_{today}.txt"
    _export_results(all_scores, export_path)
    console.print(f"[green]✓ Résultats exportés → {export_path}[/]")

    return all_scores


def _export_results(scores: list[TickerScore], path) -> None:
    """Exporte les résultats en fichier texte lisible."""
    from datetime import datetime
    with open(path, "w", encoding="utf-8") as f:
        f.write(f"Short Squeeze Scanner — {datetime.now().strftime('%Y-%m-%d %H:%M')}\n")
        f.write("=" * 70 + "\n\n")

        qualifying = [s for s in scores if s.total >= 5]
        f.write(f"Setups qualifiés (≥5/10) : {len(qualifying)}/{len(scores)}\n\n")

        for s in sorted(scores, key=lambda x: x.total, reverse=True):
            if s.total < 3:
                continue
            f.write(f"{'─' * 60}\n")
            f.write(f"{s.ticker} — {s.signal} ({s.fundamental:.1f}/10 + {s.technical_bonus:.1f} tech)\n")
            f.write(f"  Pilier 1 — VAD ({s.pillar1.score:.1f}/4)\n")
            for k, v in s.pillar1.details.items():
                f.write(f"    {k}: {v}\n")
            f.write(f"  Pilier 2 — Institutionnels ({s.pillar2.score:.1f}/4)\n")
            for k, v in s.pillar2.details.items():
                f.write(f"    {k}: {v}\n")
            f.write(f"  Pilier 3 — Divergence ({s.pillar3.score:.1f}/2)\n")
            for k, v in s.pillar3.details.items():
                f.write(f"    {k}: {v}\n")
            f.write(f"  Pilier 4 — Technique ({s.pillar4.score:.1f}/3)  {s.squeeze_phase}\n")
            for k, v in s.pillar4.details.items():
                f.write(f"    {k}: {v}\n")
            f.write("\n")


def display_results(scores: list[TickerScore]) -> None:
    """Affiche les résultats dans un tableau Rich."""
    if not scores:
        console.print("[yellow]Aucun résultat à afficher.[/]")
        return

    table = Table(
        title="🔍 Short Squeeze Scanner — Résultats",
        box=box.ROUNDED,
        show_lines=True,
    )

    table.add_column("Ticker", style="bold", width=8)
    table.add_column("Signal", width=12)
    table.add_column("Score", justify="center", width=10)
    table.add_column("P1 (VAD)", justify="center", width=9)
    table.add_column("P2 (Inst)", justify="center", width=9)
    table.add_column("P3 (Div)", justify="center", width=9)
    table.add_column("P4 (Tech)", justify="center", width=9)
    table.add_column("Phase", width=14)
    table.add_column("SI%", justify="right", width=7)
    table.add_column("DTC", justify="right", width=6)

    for s in scores[:20]:  # Top 20
        si = s.pillar1.details.get("short_float", "")
        dtc = s.pillar1.details.get("days_to_cover", "")

        if s.total >= 7:
            style = "bold red"
        elif s.total >= 5:
            style = "yellow"
        else:
            style = "dim"

        total_str = f"{s.fundamental:.1f}+{s.technical_bonus:.1f}"

        table.add_row(
            s.ticker,
            s.signal,
            total_str,
            f"{s.pillar1.score:.1f}/4",
            f"{s.pillar2.score:.1f}/4",
            f"{s.pillar3.score:.1f}/2",
            f"{s.pillar4.score:.1f}/3",
            s.squeeze_phase or "—",
            si.split(" ")[1] if " " in si else si,
            dtc.split(" ")[1] if " " in dtc else dtc,
            style=style,
        )

    console.print(table)

    # Détails des top picks
    qualifying = [s for s in scores if s.total >= 5]
    if qualifying:
        console.print(f"\n[bold green]✓ {len(qualifying)} setup(s) avec score ≥ 5/10[/]\n")
        for s in qualifying:
            p4_text = ""
            if s.pillar4.details:
                p4_text = (
                    f"\n\n[cyan]Pilier 4 — Technique ({s.pillar4.score:.1f}/3)[/]  {s.squeeze_phase}\n"
                    + "\n".join(f"  {k}: {v}" for k, v in s.pillar4.details.items())
                )

            console.print(Panel(
                f"[bold]{s.ticker}[/] — {s.signal} ({s.fundamental:.1f}/10 + {s.technical_bonus:.1f} tech)\n\n"
                f"[cyan]Pilier 1 — VAD ({s.pillar1.score:.1f}/4)[/]\n"
                + "\n".join(f"  {k}: {v}" for k, v in s.pillar1.details.items())
                + f"\n\n[cyan]Pilier 2 — Institutionnels ({s.pillar2.score:.1f}/4)[/]\n"
                + "\n".join(f"  {k}: {v}" for k, v in s.pillar2.details.items())
                + f"\n\n[cyan]Pilier 3 — Divergence ({s.pillar3.score:.1f}/2)[/]\n"
                + "\n".join(f"  {k}: {v}" for k, v in s.pillar3.details.items())
                + p4_text,
                title=f"📊 {s.ticker}",
                border_style="green" if s.total >= 7 else "yellow",
            ))


def display_single_result(score: TickerScore) -> None:
    """Affiche le résultat détaillé d'un ticker unique."""
    p4_text = ""
    if score.pillar4.details:
        p4_text = (
            f"\n\n[cyan]Pilier 4 — Technique ({score.pillar4.score:.1f}/3)[/]  {score.squeeze_phase}\n"
            + "\n".join(f"  {k}: {v}" for k, v in score.pillar4.details.items())
        )

    console.print(Panel(
        f"[bold]{score.ticker}[/] — {score.signal} ({score.fundamental:.1f}/10 + {score.technical_bonus:.1f} tech)\n\n"
        f"[cyan]Pilier 1 — Structure VAD ({score.pillar1.score:.1f}/4)[/]\n"
        + "\n".join(f"  {k}: {v}" for k, v in score.pillar1.details.items())
        + f"\n\n[cyan]Pilier 2 — Positionnement Institutionnel ({score.pillar2.score:.1f}/4)[/]\n"
        + "\n".join(f"  {k}: {v}" for k, v in score.pillar2.details.items())
        + f"\n\n[cyan]Pilier 3 — Divergence ({score.pillar3.score:.1f}/2)[/]\n"
        + "\n".join(f"  {k}: {v}" for k, v in score.pillar3.details.items())
        + p4_text,
        title=f"📊 Analyse {score.ticker}",
        border_style="red" if score.total >= 7 else "yellow" if score.total >= 5 else "blue",
    ))


def run_analyze_scan() -> None:
    """Reprend les qualifiés du dernier scan en DB et lance l'analyse IA sur chacun.

    Usage : python -m src.main --analyze-scan
    """
    from src.storage.database import get_latest_scores

    if not Config.llm_enabled():
        console.print("[red]❌ GEMINI_API_KEY non configurée dans .env[/]")
        return

    # Récupérer les qualifiés du dernier scan
    score_dicts = get_latest_scores(min_score=Config.MIN_SCORE_ALERT)
    if not score_dicts:
        console.print("[yellow]Aucun ticker qualifié dans le dernier scan.[/]")
        console.print("[dim]Lance d'abord un scan : python -m src.main[/]")
        return

    console.print(Panel(
        f"[bold]Analyse IA — {len(score_dicts)} candidats du dernier scan[/]",
        border_style="magenta",
    ))

    # Scanner chaque ticker pour avoir les TickerScore complets (pas juste les dicts DB)
    from src.analysis.llm_analyzer import analyze_candidate

    for sd in score_dicts:
        ticker = sd["ticker"]
        console.print(f"\n[bold magenta][🤖] {ticker}[/] — {sd.get('signal', '')} ({sd.get('total_score', 0):.1f})")

        try:
            # Re-scanner pour avoir le TickerScore complet avec pillar details
            score = scan_single_ticker(ticker)

            # Analyse LLM
            console.print("  🤖 Analyse IA en cours...", style="dim")
            analysis = analyze_candidate(score)

            if analysis.is_degraded:
                console.print(f"  [red]⚠ {analysis.error}[/]")
            else:
                console.print(
                    f"  → {analysis.conviction_emoji} Conviction {analysis.ai_conviction:.1f}/10",
                    style="magenta",
                )
                if analysis.catalyst:
                    console.print(f"  → Catalyst: {analysis.catalyst[:100]}", style="dim")
                if analysis.reasoning:
                    console.print(f"  → {analysis.reasoning[:120]}", style="dim")

            # Envoi Telegram avec LLM
            if Config.telegram_enabled():
                send_scan_results_rich([score], {ticker: analysis})

        except Exception as e:
            logger.error(f"Error analyzing {ticker}: {e}")
            continue

    if Config.telegram_enabled():
        console.print(f"\n[green]✓ {len(score_dicts)} analyses IA envoyées sur Telegram[/]")


def main():
    parser = argparse.ArgumentParser(
        description="Short Squeeze Scanner",
        epilog="""
Exemples:
  python -m src.main                    # Scan complet (sans IA)
  python -m src.main --ticker NVAX      # Scan + analyse IA d'un ticker
  python -m src.main --analyze-scan     # Analyse IA des qualifiés du dernier scan
  python -m src.main --test-telegram    # Test connexion Telegram
        """,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--ticker", "-t", help="Scan un ticker unique + analyse IA")
    parser.add_argument("--analyze-scan", action="store_true",
                        help="Analyse IA sur les qualifiés du dernier scan")
    parser.add_argument("--schedule", action="store_true", help="Mode scheduler (scan quotidien)")
    parser.add_argument("--verbose", "-v", action="store_true", help="Debug logging")
    parser.add_argument("--test-telegram", action="store_true", help="Test connexion Telegram")
    args = parser.parse_args()

    setup_logging(args.verbose)
    init_db()

    if args.test_telegram:
        test_telegram()
    elif args.analyze_scan:
        run_analyze_scan()
    elif args.ticker:
        score = scan_single_ticker(args.ticker.upper())
        display_single_result(score)

        # Analyse LLM automatique
        llm_analyses = {}
        if Config.llm_enabled():
            from src.analysis.llm_analyzer import analyze_candidate
            console.print("\n[magenta]  🤖 Analyse IA en cours...[/]")
            analysis = analyze_candidate(score)
            if analysis.is_degraded:
                console.print(f"  [red]⚠ {analysis.error}[/]")
            else:
                console.print(
                    f"  → {analysis.conviction_emoji} Conviction {analysis.ai_conviction:.1f}/10"
                    f" — {analysis.reasoning[:100]}",
                    style="magenta",
                )
            llm_analyses[score.ticker] = analysis
        else:
            console.print("[dim]  💡 Configure GEMINI_API_KEY pour l'analyse IA[/]")

        # Envoi Telegram
        if Config.telegram_enabled():
            send_scan_results_rich([score], llm_analyses)
            console.print("[green]✓ Alerte Telegram envoyée[/]")

    elif args.schedule:
        import schedule
        import time

        console.print("[bold cyan]Mode scheduler activé — scan quotidien à 18:30 EST[/]")
        schedule.every().day.at("18:30").do(run_full_scan)

        # Premier scan immédiat
        run_full_scan()

        while True:
            schedule.run_pending()
            time.sleep(60)
    else:
        run_full_scan()


if __name__ == "__main__":
    main()
