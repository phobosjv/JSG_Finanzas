"""
services/recurring.py
=====================
Lógica PURA para aportaciones periódicas (DCA — dollar cost averaging).

Genera el calendario de fechas de una serie de aportaciones a partir de una
fecha de inicio, una frecuencia y un número de aportaciones. No hace I/O ni
calcula precios: el router resuelve el precio histórico de cada fecha y crea
las transacciones de compra.

Frecuencias soportadas:
  weekly    — cada 7 días
  monthly   — el mismo día de mes (recortado al último día si no existe)
  quarterly — cada 3 meses
  yearly    — cada 12 meses
"""

from __future__ import annotations

import calendar
from datetime import date, timedelta
from typing import Literal

Frequency = Literal["weekly", "monthly", "quarterly", "yearly"]

# Número máximo de aportaciones en una sola serie (defensa frente a abusos).
MAX_CONTRIBUTIONS = 600


def _add_months(d: date, months: int) -> date:
    """
    Suma 'months' meses a 'd' conservando el día de mes; si el mes destino no
    tiene ese día (p. ej. 31 de enero + 1 mes), se recorta al último día.
    """
    total = d.month - 1 + months
    year = d.year + total // 12
    month = total % 12 + 1
    last_day = calendar.monthrange(year, month)[1]
    return date(year, month, min(d.day, last_day))


def nth_contribution_date(start: date, frequency: Frequency, index: int) -> date:
    """
    Fecha de la aportación de índice 'index' (0 = la primera, en 'start').

    Se calcula SIEMPRE desde 'start' (no incrementando la fecha anterior) para
    evitar el "drift" de día de mes: si una fecha se recortó (p. ej. 31→28), la
    siguiente vuelve a anclar al día original de 'start'.

    Lanza ValueError si la frecuencia no está soportada.
    """
    if frequency == "weekly":
        return start + timedelta(weeks=index)
    if frequency == "monthly":
        return _add_months(start, index)
    if frequency == "quarterly":
        return _add_months(start, 3 * index)
    if frequency == "yearly":
        return _add_months(start, 12 * index)
    raise ValueError(f"Frecuencia no soportada: {frequency!r}")


def generate_contribution_dates(
    start: date, frequency: Frequency, count: int,
) -> list[date]:
    """
    Devuelve la lista de 'count' fechas de aportación a partir de 'start',
    avanzando según 'frequency'. La primera aportación es en 'start'.

    Lanza ValueError si count < 1, count > MAX_CONTRIBUTIONS o la frecuencia
    no está soportada.
    """
    if count < 1:
        raise ValueError("El número de aportaciones debe ser >= 1")
    if count > MAX_CONTRIBUTIONS:
        raise ValueError(f"Demasiadas aportaciones (máximo {MAX_CONTRIBUTIONS})")
    return [nth_contribution_date(start, frequency, i) for i in range(count)]


def contribution_dates_until(
    start: date, frequency: Frequency, end: date,
) -> list[date]:
    """
    Devuelve las fechas de aportación desde 'start' (incluida) hasta 'end'
    (incluida), avanzando según 'frequency'. La serie la define el rango de
    fechas, no un recuento fijo.

    Lanza ValueError si end < start, si la frecuencia no está soportada o si el
    rango produce más de MAX_CONTRIBUTIONS aportaciones.
    """
    if end < start:
        raise ValueError("La fecha de fin no puede ser anterior a la de inicio")
    dates: list[date] = []
    i = 0
    while True:
        d = nth_contribution_date(start, frequency, i)
        if d > end:
            break
        dates.append(d)
        if len(dates) > MAX_CONTRIBUTIONS:
            raise ValueError(f"Demasiadas aportaciones (máximo {MAX_CONTRIBUTIONS})")
        i += 1
    return dates
