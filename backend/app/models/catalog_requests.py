"""
models/catalog_requests.py
===========================
Solicitudes de usuario para agregar productos al catálogo, notificaciones
in-app y mensajes libres al administrador (v1.12.0).
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, ForeignKey, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class SecurityRequestRow(Base):
    """Solicitud de usuario normal para añadir un producto al catálogo.

    status: pending → approved | rejected (por el admin).
    """

    __tablename__ = "security_requests"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    ticker: Mapped[str] = mapped_column(Text, nullable=False)
    isin: Mapped[str | None] = mapped_column(Text, nullable=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    # Mercado propuesto por el usuario (code de MarketRow). Puede ser nulo si
    # el mercado se borró después de crear la solicitud.
    market_id: Mapped[str | None] = mapped_column(
        ForeignKey("markets.code", ondelete="SET NULL"), nullable=True
    )
    currency: Mapped[str | None] = mapped_column(Text, nullable=True)
    # pending | approved | rejected
    status: Mapped[str] = mapped_column(Text, nullable=False, default="pending")
    # FK al Security creado al aprobar (nulo hasta entonces)
    security_id: Mapped[int | None] = mapped_column(
        ForeignKey("securities.id", ondelete="SET NULL"), nullable=True
    )
    # Admin que revisó la solicitud
    reviewed_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        nullable=False, server_default=func.datetime("now")
    )


class UserNotificationRow(Base):
    """Notificación in-app para un usuario. Se muestra en la campana (AlertBell).

    tipos:
      request_pending   — solicitud enviada, pendiente de revisión.
      request_approved  — solicitud aprobada por el admin.
      request_rejected  — solicitud rechazada por el admin.
      catalog_message   — el admin ha recibido un mensaje (no se usa actualmente
                          como notificación de usuario; se reserva para futuro).

    related_id / related_type permiten vincular con SecurityRequestRow o
    CatalogMessageRow sin FK dura, manteniendo flexibilidad.
    """

    __tablename__ = "user_notifications"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    type: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    related_id: Mapped[int | None] = mapped_column(nullable=True)
    related_type: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_read: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        nullable=False, server_default=func.datetime("now")
    )


class CatalogMessageRow(Base):
    """Mensaje libre de un usuario al administrador.

    Puede ser un contacto directo (security_request_id=NULL) o una
    respuesta del usuario tras recibir la resolución de su solicitud
    (security_request_id apunta a la SecurityRequestRow).
    """

    __tablename__ = "catalog_messages"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    message: Mapped[str] = mapped_column(Text, nullable=False)
    security_request_id: Mapped[int | None] = mapped_column(
        ForeignKey("security_requests.id", ondelete="SET NULL"), nullable=True
    )
    is_resolved: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        nullable=False, server_default=func.datetime("now")
    )
