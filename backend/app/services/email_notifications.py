"""
services/email_notifications.py
================================
Orquestador de notificaciones por email para administradores.

Lee la configuración de email y los admins con email desde la BD,
y llama al servicio puro email_service.send_email().
"""

from __future__ import annotations

import json
import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.config import AppConfig
from app.models.user import User
from app.services.email_service import EmailConfig, send_email

log = logging.getLogger(__name__)

EMAIL_CONFIG_KEY = "email_config"


def load_email_config(db: Session) -> EmailConfig | None:
    """Carga la configuración de email almacenada en app_config. None si no hay."""
    row = db.get(AppConfig, EMAIL_CONFIG_KEY)
    if not row:
        return None
    try:
        data = json.loads(row.value)
        return EmailConfig(**data)
    except Exception:
        log.exception("No se pudo deserializar la configuración de email")
        return None


def notify_admins(db: Session, subject: str, body_html: str) -> None:
    """Envía un email a todos los admins activos que tengan email configurado.

    Los errores de envío se registran pero no interrumpen el flujo principal.
    No hace nada si no hay configuración de email guardada.
    """
    config = load_email_config(db)
    if not config:
        return

    admins = db.scalars(
        select(User).where(
            User.is_admin == True,
            User.is_enabled == True,
            User.email.is_not(None),
        )
    ).all()

    for admin in admins:
        if not admin.email:
            continue
        try:
            send_email(config, admin.email, subject, body_html)
        except Exception:
            log.exception("Error enviando email de notificación a %s", admin.email)
