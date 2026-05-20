"""
services/currency.py
====================
Utilidades de tipo de cambio EUR/USD que complementan calculations.py.

'to_eur' ya esta en calculations.py (se usa en el nucleo FIFO).
Aqui vive la logica de busqueda del tipo mas cercano, que el scheduler
necesita para rellenar huecos (fines de semana, festivos del BCE).

Regla del tipo mas cercano
--------------------------
El BCE no publica en dias no habiles. Cuando se necesita el tipo de un
dia sin dato se usa el ultimo tipo publicado ANTERIOR a ese dia.
Si no existe ninguno anterior (al principio de la serie) se usa el
primero disponible posterior. Si la serie esta vacia se eleva ValueError.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal


def closest_rate(target: date, rates: dict[str, Decimal]) -> Decimal:
    """
    Devuelve el tipo EUR/USD mas cercano (anterior preferido) a 'target'.

    rates: {YYYY-MM-DD: rate} tal como devuelve EcbProvider.fetch_rates().
    """
    if not rates:
        raise ValueError("El diccionario de tipos esta vacio")

    sorted_dates = sorted(rates)

    # Buscar el ultimo anterior o igual
    candidates = [d for d in sorted_dates if d <= target.isoformat()]
    if candidates:
        return rates[candidates[-1]]

    # No hay ninguno anterior: usar el primero disponible
    return rates[sorted_dates[0]]


def fill_missing_rates(
    dates: list[date],
    known_rates: dict[str, Decimal],
) -> dict[str, Decimal]:
    """
    Para cada fecha en 'dates', resuelve el tipo usando closest_rate.
    Devuelve un dict completo {YYYY-MM-DD: rate} sin huecos.
    """
    return {d.isoformat(): closest_rate(d, known_rates) for d in dates}
