"""
services/indicators.py
=======================
Calculo de rangos de precio a partir de una serie de cierres diarios.

Recibe datos ya leidos de la BD (lista de Decimal), devuelve datos.
Sin I/O, sin SQLAlchemy, sin FastAPI.

Convencion de plazos
---------------------
1 ano  ~252 sesiones de bolsa
2 anos ~504 sesiones
5 anos ~1260 sesiones

En la practica se trabaja con dias naturales (365/730/1825) porque el
historico en BD esta indexado por fecha de calendario. Si en un rango
hay huecos (festivos, sin cotizacion), simplemente no hay valor ese dia.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal


@dataclass
class RangeStats:
    min_1y: Decimal | None
    max_1y: Decimal | None
    min_2y: Decimal | None
    min_5y: Decimal | None


def compute_ranges(
    closes: list[tuple[date, Decimal]],
    reference_date: date | None = None,
) -> RangeStats:
    """
    Calcula minimos y maximo de 1/2/5 anos a partir de una lista de
    (fecha, cierre) ya ordenada cronologicamente.

    reference_date: fecha de referencia para calcular los plazos.
    Si es None se usa el maximo de fechas en la lista.

    Devuelve None en cada campo si no hay datos en ese plazo.
    """
    if not closes:
        return RangeStats(None, None, None, None)

    ref = reference_date or max(d for d, _ in closes)
    cut_1y = ref - timedelta(days=365)
    cut_2y = ref - timedelta(days=730)
    cut_5y = ref - timedelta(days=1825)

    vals_1y = [c for d, c in closes if d >= cut_1y]
    vals_2y = [c for d, c in closes if d >= cut_2y]
    vals_5y = [c for d, c in closes if d >= cut_5y]

    return RangeStats(
        min_1y=min(vals_1y) if vals_1y else None,
        max_1y=max(vals_1y) if vals_1y else None,
        min_2y=min(vals_2y) if vals_2y else None,
        min_5y=min(vals_5y) if vals_5y else None,
    )
