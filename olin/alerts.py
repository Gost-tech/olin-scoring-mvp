"""Durable operational alerts using only the Python standard library."""
from __future__ import annotations

import os
import smtplib
from datetime import datetime, timezone
from email.message import EmailMessage
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
ENV_PATH = ROOT / ".env"
LOG_PATH = ROOT / "logs" / "alerts.log"


def _config_value(name: str, default: str = "") -> str:
    """Read an environment value, with a minimal .env fallback."""
    value = os.getenv(name)
    if value is not None:
        return value.strip()
    try:
        for raw_line in ENV_PATH.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, raw_value = line.split("=", 1)
            if key.strip() == name:
                return raw_value.strip().strip('"').strip("'")
    except FileNotFoundError:
        pass
    return default


def _write_log(subject: str, body: str, delivery_error: str = "") -> None:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).isoformat()
    error_suffix = f" | email_delivery_error={delivery_error}" if delivery_error else ""
    with LOG_PATH.open("a", encoding="utf-8") as handle:
        handle.write(f"[{timestamp}] {subject}{error_suffix}\n{body.rstrip()}\n\n")


def send_alert(subject: str, body: str) -> str:
    """Send an SMTP alert or append it to logs/alerts.log.

    SMTP defaults to localhost:25. Authentication and STARTTLS are optional and
    controlled by OLIN_SMTP_USERNAME, OLIN_SMTP_PASSWORD and OLIN_SMTP_USE_TLS.
    If email delivery fails, the alert is preserved in the local log.
    """
    subject = subject.strip() or "Olin operational alert"
    body = body.strip() or "No details supplied."
    recipient = _config_value("OLIN_ALERT_EMAIL")
    if not recipient:
        _write_log(subject, body)
        return "log"

    host = _config_value("OLIN_SMTP_HOST", "localhost")
    try:
        port = int(_config_value("OLIN_SMTP_PORT", "25"))
    except ValueError as exc:
        _write_log(subject, body, f"invalid OLIN_SMTP_PORT: {exc}")
        return "log"
    username = _config_value("OLIN_SMTP_USERNAME")
    password = _config_value("OLIN_SMTP_PASSWORD")
    use_tls = _config_value("OLIN_SMTP_USE_TLS", "0").lower() in {
        "1", "true", "yes", "on",
    }
    sender = _config_value("OLIN_SMTP_FROM", username or recipient)

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = sender
    message["To"] = recipient
    message.set_content(body)

    try:
        with smtplib.SMTP(host, port, timeout=15) as smtp:
            if use_tls:
                smtp.starttls()
            if username:
                smtp.login(username, password)
            smtp.send_message(message)
        return "email"
    except (OSError, smtplib.SMTPException, ValueError) as exc:
        _write_log(subject, body, str(exc))
        return "log"
