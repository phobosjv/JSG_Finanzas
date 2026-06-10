"""
models/user.py
==============
Tablas 'users' y 'user_status_log'.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.portfolio import Position, Favorite


class UserStatusLog(Base):
    __tablename__ = "user_status_log"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    actor_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    # 'registered' | 'enabled' | 'disabled' | 'expired'
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    annotation: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(nullable=False)

    user: Mapped["User"] = relationship(
        foreign_keys=[user_id], back_populates="status_log"
    )
    actor: Mapped["User | None"] = relationship(foreign_keys=[actor_id])

    def __repr__(self) -> str:
        return f"<UserStatusLog user_id={self.user_id} status={self.status!r}>"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    # Hash bcrypt. El hashing es competencia de auth/security.py.
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    is_admin: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="0")
    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="1")
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    email: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        nullable=False, server_default=func.datetime("now")
    )
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    positions: Mapped[list["Position"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    favorites: Mapped[list["Favorite"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    status_log: Mapped[list["UserStatusLog"]] = relationship(
        foreign_keys="[UserStatusLog.user_id]",
        back_populates="user",
        cascade="all, delete-orphan",
        order_by="UserStatusLog.created_at",
    )

    def __repr__(self) -> str:
        return f"<User id={self.id} username={self.username!r}>"
