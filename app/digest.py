import html
import os
import smtplib
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from zoneinfo import ZoneInfo

from .config import env_int


def env_bool(name, default=False):
    value = os.getenv(name)
    if value is None or not value.strip():
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def digest_settings():
    recipients = [
        value.strip() for value in os.getenv("DIGEST_EMAIL_TO", "").split(",")
        if value.strip()
    ]
    username = os.getenv("SMTP_USERNAME", "").strip()
    return {
        "host": os.getenv("SMTP_HOST", "").strip(),
        "port": min(65535, env_int("SMTP_PORT", 587, minimum=1)),
        "username": username,
        "password": os.getenv("SMTP_PASSWORD", ""),
        "sender": os.getenv("SMTP_FROM", "").strip() or username,
        "recipients": recipients,
        "starttls": env_bool("SMTP_STARTTLS", True),
    }


def _display_date(value, timezone_name):
    if not value:
        return ""
    try:
        parsed = datetime.strptime(str(value), "%Y-%m-%d %H:%M:%S").replace(
            tzinfo=timezone.utc
        )
        return parsed.astimezone(ZoneInfo(timezone_name)).strftime("%Y-%m-%d %H:%M %Z")
    except (TypeError, ValueError):
        return str(value)


def build_digest_message(items, sender, recipients, timezone_name):
    today = datetime.now(ZoneInfo(timezone_name)).strftime("%Y-%m-%d")
    message = EmailMessage()
    message["Subject"] = f"Watcher daily digest — {len(items)} new finding{'s' if len(items) != 1 else ''} — {today}"
    message["From"] = sender
    message["To"] = ", ".join(recipients)

    text_lines = [f"Watcher found {len(items)} new sales-relevant finding(s).", ""]
    html_rows = []
    for item in items:
        source = item["source_name"]
        title = item["title"]
        url = item["url"]
        enrichment = (item["enrichment"] or "").strip()
        collected = _display_date(item["created_at"], timezone_name)
        text_lines.extend([
            f"{source}: {title}",
            url,
            f"Collected: {collected}",
            *(["Summary: " + enrichment] if enrichment else []),
            "",
        ])
        html_rows.append(
            "<li>"
            f"<strong>{html.escape(source)}</strong><br>"
            f"<a href=\"{html.escape(url, quote=True)}\">{html.escape(title)}</a><br>"
            f"<small>Collected {html.escape(collected)}</small>"
            + (f"<p>{html.escape(enrichment)}</p>" if enrichment else "")
            + "</li>"
        )

    message.set_content("\n".join(text_lines))
    message.add_alternative(
        "<html><body>"
        f"<h2>Watcher daily digest</h2><p>{len(items)} new sales-relevant finding(s).</p>"
        f"<ol>{''.join(html_rows)}</ol>"
        "<p>Verify every finding at its linked source.</p>"
        "</body></html>",
        subtype="html",
    )
    return message


def send_daily_digest(db, timezone_name="America/Toronto", smtp_factory=smtplib.SMTP):
    settings = digest_settings()
    if not settings["host"] or not settings["sender"] or not settings["recipients"]:
        return {"status": "disabled", "items": 0}

    since = db.latest_digest_sent_at()
    if not since:
        since = (datetime.now(timezone.utc) - timedelta(days=1)).strftime(
            "%Y-%m-%d %H:%M:%S"
        )
    items = db.new_digest_items(since)
    if not items:
        db.record_digest_delivery(0)
        return {"status": "empty", "items": 0}

    message = build_digest_message(
        items, settings["sender"], settings["recipients"], timezone_name
    )
    with smtp_factory(settings["host"], settings["port"], timeout=30) as smtp:
        if settings["starttls"]:
            smtp.starttls()
        if settings["username"]:
            smtp.login(settings["username"], settings["password"])
        smtp.send_message(message)

    db.record_digest_delivery(len(items))
    return {"status": "sent", "items": len(items)}
