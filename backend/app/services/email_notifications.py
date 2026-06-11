"""
services/email_notifications.py
================================
Orquestador de notificaciones para administradores: in-app y por email.

- notify_admins_inapp : crea UserNotificationRow para cada admin activo.
- notify_admins       : envía email a cada admin activo con email configurado.
"""

from __future__ import annotations

import json
import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.config import AppConfig
from app.models.user import User
from app.models.catalog_requests import UserNotificationRow
from app.services.email_service import EmailConfig, send_email

log = logging.getLogger(__name__)

EMAIL_CONFIG_KEY = "email_config"


def get_app_name(db: Session) -> str:
    """Devuelve el nombre de la aplicación guardado en app_config, o 'Finanzas' si no hay."""
    row = db.get(AppConfig, "app_name")
    return row.value if (row and row.value) else "Finanzas"


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


def notify_admins_inapp(
    db: Session,
    type_: str,
    title: str,
    body: str,
    related_id: int | None = None,
    related_type: str | None = None,
) -> int:
    """Crea notificaciones in-app para todos los admins activos.

    Devuelve el número de notificaciones creadas. No hace commit — el caller
    es responsable de llamar db.commit() cuando corresponda.
    """
    admins = db.scalars(
        select(User).where(
            User.is_admin == True,
            User.is_enabled == True,
        )
    ).all()

    for admin in admins:
        db.add(UserNotificationRow(
            user_id=admin.id,
            type=type_,
            title=title,
            body=body,
            related_id=related_id,
            related_type=related_type,
            is_read=False,
        ))
    return len(admins)
