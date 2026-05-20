"""
models/portfolio.py
===================
Dominio de cartera: favorites, positions, transactions, dividends.

Decisiones que vienen del diseno y se respetan aqui:
  * 'positions' NO guarda numero de acciones ni precio medio: son datos
    derivados de 'transactions' via FIFO (calculations.compute_position).
  * 'transactions' y 'dividends' llevan currency + exchange_rate. El
    exchange_rate es el tipo EUR/USD del BCE en la fecha de la operacion
    (1 para EUR). Es lo unico que el nucleo de calculo necesita; 'currency'
    queda para validacion de coherencia en la capa repositorio.

FKs y ondelete (copiados de crear-tablas.sql, con intencion):
  * positions.security_id  -> RESTRICT: no se borra un valor con historico.
  * positions.user_id      -> CASCADE: al borrar el usuario, cae su cartera.
  * transactions.position_id, dividends.position_id -> CASCADE.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    CheckConstraint, ForeignKey, Index, String, Text,
    UniqueConstraint, func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, Money

if TYPE_CHECKING:
    from app.models.user import User
    from app.models.security import Security


class Favorite(Base):
    """Relacion usuario <-> valor marcado como favorito. PK compuesta."""
    __tablename__ = "favorites"

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    security_id: Mapped[int] = mapped_column(
        ForeignKey("securities.id", ondelete="CASCADE"), primary_key=True
    )
    target_buy_price: Mapped["object | None"] = mapped_column(Money, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        nullable=False, server_default=func.datetime("now")
    )

    user: Mapped["User"] = relationship(back_populates="favorites")
    security: Mapped["Security"] = relationship(back_populates="favorites")


class Position(Base):
    """
    Un registro por valor que el usuario tiene o ha tenido.
    No almacena nº de acciones ni precio medio: se derivan de transactions.
    """
    __tablename__ = "positions"
    __table_args__ = (
        UniqueConstraint("user_id", "security_id", name="uq_positions_user_security"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    # RESTRICT: integridad del historico frente a borrados del catalogo.
    security_id: Mapped[int] = mapped_column(
        ForeignKey("securities.id", ondelete="RESTRICT"), nullable=False
    )
    target_sell_price: Mapped["object | None"] = mapped_column(Money, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        nullable=False, server_default=func.datetime("now")
    )

    user: Mapped["User"] = relationship(back_populates="positions")
    security: Mapped["Security"] = relationship(back_populates="positions")
    transactions: Mapped[list["TransactionRow"]] = relationship(
        back_populates="position", cascade="all, delete-orphan"
    )
    dividends: Mapped[list["DividendRow"]] = relationship(
        back_populates="position", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Position id={self.id} user={self.user_id} sec={self.security_id}>"


class TransactionRow(Base):
    """
    Fila de la tabla 'transactions' (compra o venta).

    Se llama 'TransactionRow' y no 'Transaction' a proposito: 'Transaction'
    ya es el dataclass puro de calculations.py. El repositorio traduce
    TransactionRow -> calculations.Transaction. Mantener nombres distintos
    evita colisiones de import y deja claro que son cosas de capas distintas.
    """
    __tablename__ = "transactions"
    __table_args__ = (
        CheckConstraint("type IN ('buy','sell')", name="ck_tx_type"),
        CheckConstraint("shares > 0", name="ck_tx_shares_positive"),
        CheckConstraint("currency IN ('EUR','USD')", name="ck_tx_currency"),
        Index("idx_tx_position_date", "position_id", "date"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    position_id: Mapped[int] = mapped_column(
        ForeignKey("positions.id", ondelete="CASCADE"), nullable=False
    )
    type: Mapped[str] = mapped_column(String, nullable=False)  # 'buy' | 'sell'
    date: Mapped[str] = mapped_column(String, nullable=False)  # 'YYYY-MM-DD'
    shares: Mapped["object"] = mapped_column(Money, nullable=False)
    price: Mapped["object"] = mapped_column(Money, nullable=False)
    fee: Mapped["object"] = mapped_column(Money, nullable=False, default=0)
    currency: Mapped[str] = mapped_column(String, nullable=False)
    # EUR/USD del BCE en 'date'; 1 si la operacion es en EUR.
    exchange_rate: Mapped["object"] = mapped_column(Money, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(
        nullable=False, server_default=func.datetime("now")
    )

    position: Mapped["Position"] = relationship(back_populates="transactions")

    def __repr__(self) -> str:
        return (
            f"<TransactionRow id={self.id} {self.type} {self.date} "
            f"shares={self.shares} price={self.price}>"
        )


class DividendRow(Base):
    """
    Fila de la tabla 'dividends'. Mismo criterio de nombre que TransactionRow:
    'Dividend' ya es el dataclass de calculations.py.
    """
    __tablename__ = "dividends"
    __table_args__ = (
        CheckConstraint("currency IN ('EUR','USD')", name="ck_div_currency"),
        Index("idx_div_position_date", "position_id", "date"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    position_id: Mapped[int] = mapped_column(
        ForeignKey("positions.id", ondelete="CASCADE"), nullable=False
    )
    date: Mapped[str] = mapped_column(String, nullable=False)  # fecha de cobro
    shares_at_date: Mapped["object"] = mapped_column(Money, nullable=False)
    gross_per_share: Mapped["object"] = mapped_column(Money, nullable=False)
    gross_amount: Mapped["object"] = mapped_column(Money, nullable=False)
    withholding_tax: Mapped["object"] = mapped_column(Money, nullable=False, default=0)
    currency: Mapped[str] = mapped_column(String, nullable=False)
    exchange_rate: Mapped["object"] = mapped_column(Money, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(
        nullable=False, server_default=func.datetime("now")
    )

    position: Mapped["Position"] = relationship(back_populates="dividends")

    def __repr__(self) -> str:
        return (
            f"<DividendRow id={self.id} {self.date} "
            f"gross={self.gross_amount} wh={self.withholding_tax}>"
        )
