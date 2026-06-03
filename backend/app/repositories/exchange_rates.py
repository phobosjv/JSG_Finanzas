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

from app.models import EcbRate, TransactionRow

_ONE = Decimal("1")


def _latest_tx_rate(db: Session, currency: str) -> Decimal | None:
    """Último exchange_rate registrado en una transacción de esa divisa, o None."""
    return db.scalar(
        select(TransactionRow.exchange_rate)
        .where(TransactionRow.currency == currency)
        .order_by(TransactionRow.date.desc())
    )


def latest_rate(db: Session, currency: str) -> Decimal:
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
    return _latest_tx_rate(db, currency) or _ONE


def rate_on_date(db: Session, currency: str, date_str: str) -> Decimal:
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
    return latest_rate(db, currency)
