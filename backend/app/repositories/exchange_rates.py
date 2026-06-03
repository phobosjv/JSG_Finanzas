"""
repositories/exchange_rates.py
==============================
Búsqueda del tipo de cambio EUR/{divisa} cacheado del BCE (multi-divisa, v1.8.0).

El rate es "{divisa} por 1 EUR" (convención BCE): euros = importe / rate.
Para EUR el tipo es siempre 1. Si no hay dato para una divisa, se devuelve 1
como último recurso (mejor esfuerzo: la valoración no puede convertir sin tipo).
"""
from __future__ import annotations

from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import EcbRate

_ONE = Decimal("1")


def latest_rate(db: Session, currency: str) -> Decimal:
    """Tipo más reciente para 'currency' (1 para EUR; 1 si no hay dato)."""
    if currency == "EUR":
        return _ONE
    row = db.scalar(
        select(EcbRate)
        .where(EcbRate.currency == currency)
        .order_by(EcbRate.date.desc())
    )
    return row.rate if row is not None else _ONE


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
