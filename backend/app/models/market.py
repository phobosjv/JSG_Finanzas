"""
models/market.py
================
Tabla 'markets'. Catálogo dinámico de mercados gestionado por administradores.

Campos:
  code              — clave primaria (ej: 'ibex35', 'nasdaq', 'nikkei')
  name              — nombre legible (ej: 'IBEX 35', 'Nikkei 225')
  index_ticker      — símbolo Yahoo para el índice del mercado (ej: '^N225')
  currency          — divisa de cotización display (ej: 'EUR', 'USD', 'JPY')
  fiscal_window_days— días del plazo de recompra para la regla IRPF:
                      60 para mercados UE/EEE, 365 para mercados fuera del EEE.
  sort_order        — orden de aparición en las pestañas de la UI (v1.5.0).
                      Menor número = más a la izquierda. Default 0.
  yahoo_exchange    — código de exchange en Yahoo Finance (ej: 'MCE', 'NMS', 'LSE').
                      Opcional. Permite filtrar búsquedas del explorador de valores.
  is_fund_market    — True si el mercado agrupa fondos de inversión. Los fondos se
                      excluyen del informe fiscal PDF (la retención la gestiona la entidad).
                      Se mantiene DERIVADO de market_type ('fund') para no romper la
                      lógica fiscal/scheduler existente.
  market_type       — tipo de producto del mercado (v1.7.6): 'stock' | 'fund' |
                      'etf' | 'crypto'. Base de la segmentación de Cartera/Dashboard
                      y de la agrupación del menú de Mercados.
  created_at        — timestamp de creación
"""

from __future__ import annotations

from sqlalchemy import Boolean, CheckConstraint, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base

# Tipos de producto soportados. 'stock' es el valor por defecto.
MARKET_TYPES = ("stock", "fund", "etf", "crypto")


class MarketRow(Base):
    __tablename__ = "markets"
    __table_args__ = (
        CheckConstraint(
            "market_type IN ('stock','fund','etf','crypto')", name="ck_market_type"
        ),
    )

    code: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    index_ticker: Mapped[str | None] = mapped_column(String, nullable=True)
    currency: Mapped[str] = mapped_column(String, nullable=False, default="EUR")
    fiscal_window_days: Mapped[int] = mapped_column(Integer, nullable=False, default=60)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    yahoo_exchange: Mapped[str | None] = mapped_column(String(20), nullable=True)
    is_fund_market: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    market_type: Mapped[str] = mapped_column(String, nullable=False, default="stock")
    created_at: Mapped[str] = mapped_column(String, nullable=False)

    def __repr__(self) -> str:
        return f"<MarketRow code={self.code!r} name={self.name!r} order={self.sort_order}>"
