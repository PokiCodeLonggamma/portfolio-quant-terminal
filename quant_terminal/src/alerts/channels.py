"""Output channels — Discord webhook / email SMTP / Telegram bot / Streamlit toast."""
from __future__ import annotations

import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import requests

from src.alerts.triggers import AlertEvent
from src.utils.logging import get_logger

log = get_logger(__name__)


# ---------------------------------------------------------------------------
# Discord
# ---------------------------------------------------------------------------
def send_discord(event: AlertEvent, webhook_url: str | None = None) -> bool:
    url = webhook_url or os.getenv("DISCORD_WEBHOOK_URL", "")
    if not url:
        log.debug("DISCORD_WEBHOOK_URL missing — skipping discord dispatch")
        return False
    color = {
        "info": 0x3B82F6,
        "warning": 0xF59E0B,
        "critical": 0xEF4444,
    }.get(event.severity, 0x3B82F6)
    payload = {
        "embeds": [{
            "title": event.title,
            "description": event.body,
            "color": color,
            "footer": {"text": f"trigger: {event.trigger_name} · {event.severity}"},
            "timestamp": event.fired_at.isoformat() + "Z",
        }],
    }
    try:
        r = requests.post(url, json=payload, timeout=10)
        r.raise_for_status()
        return True
    except Exception as exc:
        log.warning("Discord dispatch failed for %s: %s", event.trigger_name, exc)
        return False


# ---------------------------------------------------------------------------
# Email (SMTP)
# ---------------------------------------------------------------------------
def send_email(
    event: AlertEvent,
    *,
    smtp_host: str | None = None,
    smtp_port: int | None = None,
    username: str | None = None,
    password: str | None = None,
    from_addr: str | None = None,
    to_addrs: list[str] | None = None,
) -> bool:
    smtp_host = smtp_host or os.getenv("ALERT_SMTP_HOST", "")
    smtp_port = smtp_port or int(os.getenv("ALERT_SMTP_PORT", "587"))
    username = username or os.getenv("ALERT_SMTP_USERNAME", "")
    password = password or os.getenv("ALERT_SMTP_PASSWORD", "")
    from_addr = from_addr or os.getenv("ALERT_SMTP_FROM", username)
    to_env = os.getenv("ALERT_SMTP_TO", "")
    to_addrs = to_addrs or ([a.strip() for a in to_env.split(",") if a.strip()] if to_env else [])
    if not (smtp_host and from_addr and to_addrs):
        log.debug("SMTP not configured — skipping email dispatch")
        return False

    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"[Quant Terminal · {event.severity.upper()}] {event.title}"
    msg["From"] = from_addr
    msg["To"] = ", ".join(to_addrs)
    msg.attach(MIMEText(event.body, "plain"))
    html = (
        f"<h3 style='margin:0;font-family:sans-serif'>{event.title}</h3>"
        f"<p style='font-family:sans-serif'>{event.body}</p>"
        f"<hr><small>{event.trigger_name} · {event.fired_at.isoformat()} UTC</small>"
    )
    msg.attach(MIMEText(html, "html"))

    try:
        with smtplib.SMTP(smtp_host, smtp_port, timeout=10) as s:
            s.starttls()
            if username and password:
                s.login(username, password)
            s.sendmail(from_addr, to_addrs, msg.as_string())
        return True
    except Exception as exc:
        log.warning("Email dispatch failed for %s: %s", event.trigger_name, exc)
        return False


# ---------------------------------------------------------------------------
# Telegram
# ---------------------------------------------------------------------------
def send_telegram(event: AlertEvent, *, bot_token: str | None = None,
                  chat_id: str | None = None) -> bool:
    bot_token = bot_token or os.getenv("TELEGRAM_BOT_TOKEN", "")
    chat_id = chat_id or os.getenv("TELEGRAM_CHAT_ID", "")
    if not (bot_token and chat_id):
        log.debug("Telegram not configured — skipping telegram dispatch")
        return False
    sev_emoji = {"info": "ℹ️", "warning": "⚠️", "critical": "🚨"}.get(event.severity, "")
    text = f"{sev_emoji} *{event.title}*\n{event.body}\n_{event.trigger_name}_"
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    try:
        r = requests.post(url, json={"chat_id": chat_id, "text": text,
                                      "parse_mode": "Markdown"}, timeout=10)
        r.raise_for_status()
        return True
    except Exception as exc:
        log.warning("Telegram dispatch failed for %s: %s", event.trigger_name, exc)
        return False


# ---------------------------------------------------------------------------
# Dispatch all
# ---------------------------------------------------------------------------
def dispatch(event: AlertEvent) -> dict[str, bool]:
    """Send the event to every channel listed in `event.channels`.

    Returns dict {channel_name: success_bool}.
    """
    results: dict[str, bool] = {}
    for ch in event.channels:
        if ch == "discord":
            results["discord"] = send_discord(event)
        elif ch == "email":
            results["email"] = send_email(event)
        elif ch == "telegram":
            results["telegram"] = send_telegram(event)
        elif ch == "streamlit":
            # Streamlit toasts are surfaced inline by app.py reading the history.
            results["streamlit"] = True
        else:
            log.warning("Unknown channel: %s", ch)
            results[ch] = False
    return results
