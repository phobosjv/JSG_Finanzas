"""
repositories/exchange_rates.py
==============================
Búsqueda del tipo de cambio EUR/{divisa} cacheado del BCE (multi-divisa, v1.8.0).

El rate es "{divisa} por 1 EUR" (convención BCE): euros = importe / rate.
Para EUR el tipo es siempre 1. Si el BCE aún no tiene la divisa cacheada, se cae
al último tipo registrado en una transacción de esa divisa (el que introdujo o
autorrellenó el usuario): es mucho mejor que devolver 1, que trataría p. ej. el
dólar como euro e inflaría la valoración. Como último recurso, 1.
"""
from __future__ import annotations

from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import EcbRate, Position, TransactionRow

_ONE = Decimal("1")


def _latest_tx_rate(
    db: Session, currency: str, user_id: int | None = None
) -> Decimal | None:
    """Último exchange_rate registrado en una transacción de esa divisa, o None.

    'user_id' acota la búsqueda a las transacciones de ESE usuario. Sin él, el
    respaldo salía de la última operación en esa divisa de CUALQUIER usuario:
    con 'ecb_rates' vacía, la cartera de un usuario se valoraba con el tipo que
    había tecleado otro. Se deja opcional para los pocos sitios sin contexto de
    usuario, pero pasarlo es lo correcto.
    """
    stmt = select(TransactionRow.exchange_rate).where(
        TransactionRow.currency == currency
    )
    if user_id is not None:
        stmt = stmt.join(
            Position, Position.id == TransactionRow.position_id
        ).where(Position.user_id == user_id)
    return db.scalar(stmt.order_by(TransactionRow.date.desc()))


def latest_rate(db: Session, currency: str, user_id: int | None = None) -> Decimal:
    """Tipo más reciente para 'currency' (1 para EUR)."""
    if currency == "EUR":
        return _ONE
    row = db.scalar(
        select(EcbRate)
        .where(EcbRate.currency == currency)
        .order_by(EcbRate.date.desc())
    )
    if row is not None:
        return row.rate
    return _latest_tx_rate(db, currency, user_id) or _ONE


def rate_on_date(
    db: Session, currency: str, date_str: str, user_id: int | None = None
) -> Decimal:
    """
    Tipo de 'currency' vigente en 'date_str' (el del día hábil anterior o igual).
    1 para EUR. Si no hay dato anterior, cae al más reciente disponible; si no
    hay ninguno, 1.
    """
    if currency == "EUR":
        return _ONE
    row = db.scalar(
        select(EcbRate)
        .where(EcbRate.currency == currency, EcbRate.date <= date_str)
        .order_by(EcbRate.date.desc())
    )
    if row is not None:
        return row.rate
    return latest_rate(db, currency, user_id)
