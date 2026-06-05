"""
models/push.py
==============
Suscripciones push (Web Push Protocol) por dispositivo/usuario.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import ForeignKey, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class PushSubscription(Base):
    """
    Una suscripción push registrada por un dispositivo del usuario.
    Un mismo usuario puede tener varias (teléfono, ordenador, etc.).

    last_notified_keys: JSON array de strings "tipo:security_id" que se
    enviaron en la última notificación. Se compara con los alertas activos
    para evitar reenviar la misma alerta en cada ciclo de snapshots.
    """
    __tablename__ = "push_subscriptions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    endpoint: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    p256dh: Mapped[str] = mapped_column(Text, nullable=False)
    auth: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        nullable=False, server_default=func.datetime("now")
    )
    last_notified_keys: Mapped[str | None] = mapped_column(Text, nullable=True)
