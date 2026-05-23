"""
models/security.py
==================
Tabla 'securities'. Catálogo global de valores gestionado por administradores.

'market' es un string libre validado contra la tabla 'markets' en la capa de
API (no con CheckConstraint, ya que los mercados son ahora dinámicos).
'currency' sigue siendo EUR o USD: el motor de cálculo solo maneja
conversiones BCE EUR/USD; para nuevos mercados con otras divisas el admin
elige la divisa de cotización más próxima.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.price import PriceHistory, PriceSnapshot
    from app.models.portfolio import Position, Favorite
    from app.models.security import SecuritySplit

CURRENCIES = ("EUR", "USD")


class Security(Base):
    __tablename__ = "securities"
    __table_args__ = (
        # El CheckConstraint de 'market' se eliminó en la migración a3f9c1d2e5b4
        # (mercados ahora son dinámicos). Se mantiene el de 'currency' porque el
        # motor de cálculo solo soporta conversiones EUR/USD vía BCE.
        CheckConstraint(
            "currency IN ('EUR','USD')", name="ck_securities_currency"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    isin: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Indice UNIQUE sobre yahoo_ticker: no se repite un valor en el catalogo.
    yahoo_ticker: Mapped[str] = mapped_column(
        Text, nullable=False, unique=True, index=True
    )
    # Informativo: el ticker de Google se muestra pero no se usa para datos.
    google_ticker: Mapped[str | None] = mapped_column(Text, nullable=True)
    market: Mapped[str] = mapped_column(String, nullable=False)
    currency: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        nullable=False, server_default=func.datetime("now")
    )

    price_history: Mapped[list["PriceHistory"]] = relationship(
        back_populates="security", cascade="all, delete-orphan"
    )
    snapshot: Mapped["PriceSnapshot | None"] = relationship(
        back_populates="security", cascade="all, delete-orphan", uselist=False
    )
    positions: Mapped[list["Position"]] = relationship(back_populates="security")
    favorites: Mapped[list["Favorite"]] = relationship(back_populates="security")
    splits: Mapped[list["SecuritySplit"]] = relationship(
        back_populates="security", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Security id={self.id} ticker={self.yahoo_ticker!r} market={self.market}>"


class SecuritySplit(Base):
    """
    Evento de split o contrasplit global. Gestionado por el admin; afecta
    automáticamente a todos los usuarios que posean el valor.

    ratio_num:ratio_den  →  acciones nuevas por cada 'ratio_den' acciones antiguas.
    Ejemplos: split 2:1 → ratio_num=2, ratio_den=1
              contrasplit 1:2 → ratio_num=1, ratio_den=2
    """
    __tablename__ = "security_splits"
    __table_args__ = (
        CheckConstraint("ratio_num >= 1", name="ck_split_ratio_num_positive"),
        CheckConstraint("ratio_den >= 1", name="ck_split_ratio_den_positive"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    security_id: Mapped[int] = mapped_column(
        ForeignKey("securities.id", ondelete="CASCADE"), nullable=False, index=True
    )
    ex_date: Mapped[str] = mapped_column(String, nullable=False)  # 'YYYY-MM-DD'
    ratio_num: Mapped[int] = mapped_column(nullable=False)   # acciones nuevas
    ratio_den: Mapped[int] = mapped_column(nullable=False)   # acciones antiguas
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        nullable=False, server_default=func.datetime("now")
    )

    security: Mapped["Security"] = relationship(back_populates="splits")

    def __repr__(self) -> str:
        return (
            f"<SecuritySplit id={self.id} sec={self.security_id} "
            f"{self.ex_date} {self.ratio_num}:{self.ratio_den}>"
        )
