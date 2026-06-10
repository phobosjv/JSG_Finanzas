"""
services/email_service.py
=========================
Servicio puro de envío de email. Sin dependencias de SQLAlchemy ni FastAPI.

Proveedores soportados:
  smtp_gmail   — Gmail con contraseña de aplicación (SMTP + STARTTLS, puerto 587)
  smtp_outlook — Outlook/Microsoft 365 (SMTP + STARTTLS, puerto 587)
  smtp_generic — SMTP genérico configurable (host, puerto, TLS opcional)
  sendgrid     — API REST de SendGrid (httpx)
  mailgun      — API REST de Mailgun (httpx)
"""

from __future__ import annotations

import smtplib
import ssl
from dataclasses import dataclass, field
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import httpx

# Configuraciones de servidor predefinidas
_SMTP_PRESETS: dict[str, tuple[str, int]] = {
    "smtp_gmail":   ("smtp.gmail.com",     587),
    "smtp_outlook": ("smtp.office365.com", 587),
}


@dataclass
class EmailConfig:
    provider: str          # smtp_gmail | smtp_outlook | smtp_generic | sendgrid | mailgun
    from_name: str
    from_address: str
    smtp_host: str | None = None
    smtp_port: int | None = None
    smtp_user: str | None = None
    smtp_password: str | None = None
    smtp_use_tls: bool = True   # STARTTLS
    api_key: str | None = None
    mailgun_domain: str | None = None


def send_email(config: EmailConfig, to: str, subject: str, body_html: str) -> None:
    """Envía un email según el proveedor configurado.

    Lanza excepción si el envío falla (el caller decide si loguear o relanzar).
    """
    if config.provider in ("smtp_gmail", "smtp_outlook", "smtp_generic"):
        _send_smtp(config, to, subject, body_html)
    elif config.provider == "sendgrid":
        _send_sendgrid(config, to, subject, body_html)
    elif config.provider == "mailgun":
        _send_mailgun(config, to, subject, body_html)
    else:
        raise ValueError(f"Proveedor de email desconocido: {config.provider!r}")


# ---------------------------------------------------------------------------
#  SMTP (Gmail, Outlook, genérico)
# ---------------------------------------------------------------------------

def _send_smtp(config: EmailConfig, to: str, subject: str, body_html: str) -> None:
    if config.provider in _SMTP_PRESETS:
        host, port = _SMTP_PRESETS[config.provider]
    else:
        host = config.smtp_host or ""
        port = config.smtp_port or 587

    if not host:
        raise ValueError("smtp_host es obligatorio para smtp_generic")

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = f"{config.from_name} <{config.from_address}>"
    msg["To"] = to
    msg.attach(MIMEText(body_html, "html", "utf-8"))

    context = ssl.create_default_context()
    with smtplib.SMTP(host, port, timeout=15) as server:
        server.ehlo()
        if config.smtp_use_tls or config.provider in _SMTP_PRESETS:
            server.starttls(context=context)
            server.ehlo()
        if config.smtp_user and config.smtp_password:
            server.login(config.smtp_user, config.smtp_password)
        server.send_message(msg)


# ---------------------------------------------------------------------------
#  SendGrid
# ---------------------------------------------------------------------------

def _send_sendgrid(config: EmailConfig, to: str, subject: str, body_html: str) -> None:
    if not config.api_key:
        raise ValueError("api_key es obligatorio para SendGrid")

    payload = {
        "personalizations": [{"to": [{"email": to}]}],
        "from": {"email": config.from_address, "name": config.from_name},
        "subject": subject,
        "content": [{"type": "text/html", "value": body_html}],
    }
    resp = httpx.post(
        "https://api.sendgrid.com/v3/mail/send",
        headers={"Authorization": f"Bearer {config.api_key}"},
        json=payload,
        timeout=15,
    )
    if resp.status_code not in (200, 202):
        raise RuntimeError(f"SendGrid error {resp.status_code}: {resp.text[:200]}")


# ---------------------------------------------------------------------------
#  Mailgun
# ---------------------------------------------------------------------------

def _send_mailgun(config: EmailConfig, to: str, subject: str, body_html: str) -> None:
    if not config.api_key:
        raise ValueError("api_key es obligatorio para Mailgun")
    if not config.mailgun_domain:
        raise ValueError("mailgun_domain es obligatorio para Mailgun")

    resp = httpx.post(
        f"https://api.mailgun.net/v3/{config.mailgun_domain}/messages",
        auth=("api", config.api_key),
        data={
            "from": f"{config.from_name} <{config.from_address}>",
            "to": to,
            "subject": subject,
            "html": body_html,
        },
        timeout=15,
    )
    if resp.status_code != 200:
        raise RuntimeError(f"Mailgun error {resp.status_code}: {resp.text[:200]}")
