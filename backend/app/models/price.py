"""
models/price.py
===============
Tablas del dominio de precios:
  * PriceHistory   -- historico diario de cotizaciones (lo rellena el
                      scheduler nocturno). Cierre en divisa nativa del valor.
  * PriceSnapshot  -- ultima cotizacion + indicadores precalculados; una
                      fila por valor (PK = security_id).
  * EcbRate        -- cache de tipos de cambio EUR/USD del BCE, dato congelado.

Los importes monetarios usan el tipo 'Money' para entrar/salir como Decimal.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Integer, String, UniqueConstraint, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, Money

if TYPE_CHECKING:
    from app.models.security import Security


class PriceHistory(Base):
    __tablename__ = "price_history"
    __table_args__ = (
        UniqueConstraint("security_id", "date", name="uq_history_security_date"),
        Index("idx_history_security_date", "security_id", "date"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    security_id: Mapped[int] = mapped_column(
        ForeignKey("securities.id", ondelete="CASCADE"), nullable=False
    )
    date: Mapped[str] = mapped_column(String, nullable=False)  # 'YYYY-MM-DD'
    close: Mapped["object"] = mapped_column(Money, nullable=False)
    volume: Mapped[int | None] = mapped_column(Integer, nullable=True)

    security: Mapped["Security"] = relationship(back_populates="price_history")

    def __repr__(self) -> str:
        return f"<PriceHistory sec={self.security_id} {self.date} close={self.close}>"


class PriceSnapshot(Base):
    __tablename__ = "price_snapshots"

    # PK = security_id: relacion 1 a 1 con el valor.
    security_id: Mapped[int] = mapped_column(
        ForeignKey("securities.id", ondelete="CASCADE"), primary_key=True
    )
    last_price: Mapped["object | None"] = mapped_column(Money, nullable=True)
    prev_close: Mapped["object | None"] = mapped_column(Money, nullable=True)
    daily_change_pct: Mapped["object | None"] = mapped_column(Money, nullable=True)
    min_1y: Mapped["object | None"] = mapped_column(Money, nullable=True)
    min_2y: Mapped["object | None"] = mapped_column(Money, nullable=True)
    min_5y: Mapped["object | None"] = mapped_column(Money, nullable=True)
    max_1y: Mapped["object | None"] = mapped_column(Money, nullable=True)
    last_dividend: Mapped["object | None"] = mapped_column(Money, nullable=True)
    updated_at: Mapped[str | None] = mapped_column(String, nullable=True)

    security: Mapped["Security"] = relationship(back_populates="snapshot")

    def __repr__(self) -> str:
        return f"<PriceSnapshot sec={self.security_id} last={self.last_price}>"


class EcbRate(Base):
    """Tipo EUR/USD de referencia del BCE. PK = fecha; dato cacheado."""
    __tablename__ = "ecb_rates"

    date: Mapped[str] = mapped_column(String, primary_key=True)  # 'YYYY-MM-DD'
    rate: Mapped["object"] = mapped_column(Money, nullable=False)

    def __repr__(self) -> str:
        return f"<EcbRate {self.date} rate={self.rate}>"
