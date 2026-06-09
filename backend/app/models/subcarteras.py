"""
models/subcarteras.py
=====================
Subcarteras: agrupaciones personalizadas de posiciones definidas por el usuario.
Relación muchos-a-muchos con positions a través de subcartera_positions.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import ForeignKey, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class SubcarteraRow(Base):
    """Subcartera definida por el usuario: agrupa posiciones arbitrarias."""

    __tablename__ = "subcarteras"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        nullable=False, server_default=func.datetime("now")
    )


class SubcarteraPositionRow(Base):
    """Tabla de unión muchos-a-muchos: subcartera ↔ position."""

    __tablename__ = "subcartera_positions"

    subcartera_id: Mapped[int] = mapped_column(
        ForeignKey("subcarteras.id", ondelete="CASCADE"),
        primary_key=True,
        nullable=False,
    )
    position_id: Mapped[int] = mapped_column(
        ForeignKey("positions.id", ondelete="CASCADE"),
        primary_key=True,
        nullable=False,
    )
