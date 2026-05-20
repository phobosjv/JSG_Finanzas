"""
models/security.py
==================
Tabla 'securities'. Catalogo de valores que el usuario da de alta en
Utilidades. Replica crear-tablas.sql, incluyendo los CHECK de 'market' y
'currency' como CheckConstraint a nivel de tabla.

Nota sobre 'market': los valores permitidos ('ibex35','continuo','nasdaq')
coinciden exactamente con el Literal 'Market' de tax_report.py. Esa
correspondencia es la que permite al repositorio construir SecurityRef
sin traducir nada.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.price import PriceHistory, PriceSnapshot
    from app.models.portfolio import Position, Favorite

# Conjuntos validos, declarados una sola vez para reusarlos en validacion.
MARKETS = ("ibex35", "continuo", "nasdaq")
CURRENCIES = ("EUR", "USD")


class Security(Base):
    __tablename__ = "securities"
    __table_args__ = (
        CheckConstraint(
            "market IN ('ibex35','continuo','nasdaq')", name="ck_securities_market"
        ),
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

    def __repr__(self) -> str:
        return f"<Security id={self.id} ticker={self.yahoo_ticker!r} market={self.market}>"
