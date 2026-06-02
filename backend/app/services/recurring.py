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

    dates: list[date] = []
    for i in range(count):
        if frequency == "weekly":
            dates.append(start + timedelta(weeks=i))
        elif frequency == "monthly":
            dates.append(_add_months(start, i))
        elif frequency == "quarterly":
            dates.append(_add_months(start, 3 * i))
        elif frequency == "yearly":
            dates.append(_add_months(start, 12 * i))
        else:
            raise ValueError(f"Frecuencia no soportada: {frequency!r}")
    return dates
