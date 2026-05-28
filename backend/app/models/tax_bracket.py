"""
models/tax_bracket.py
=====================
Tabla 'tax_brackets'. Tramos del IRPF del ahorro configurables por el admin.

Cada tramo define un intervalo de base imponible [min_amount, max_amount)
y el tipo marginal aplicable. El último tramo tiene max_amount = NULL
(sin techo). Los tramos se presentan ordenados por sort_order.

Vigentes en España desde 2023 (valores por defecto cargados en la migración):
  0 – 6.000 €     → 19 %
  6.000 – 50.000   → 21 %
  50.000 – 200.000 → 23 %
  200.000 – 300.000 → 27 %
  > 300.000         → 28 %
"""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import Integer
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, Money


class TaxBracketRow(Base):
    __tablename__ = "tax_brackets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    min_amount: Mapped[Decimal] = mapped_column(Money, nullable=False)
    max_amount: Mapped[Decimal | None] = mapped_column(Money, nullable=True)
    rate: Mapped[Decimal] = mapped_column(Money, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    def __repr__(self) -> str:
        top = f"{self.max_amount}" if self.max_amount is not None else "∞"
        return f"<TaxBracketRow {self.min_amount}–{top} @ {self.rate}%>"
