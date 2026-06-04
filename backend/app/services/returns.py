"""
services/returns.py
===================
Rentabilidad anualizada ponderada por dinero (TIR / XIRR).

XIRR es la tasa anual 'r' que hace cero el valor actual neto de una serie de
flujos de caja fechados:

    Σ  importe_i / (1 + r) ** (días_i / 365)  =  0

Convención de signos (desde el punto de vista del inversor):
  * Dinero que SALE (compras)         → importe negativo.
  * Dinero que ENTRA (ventas, dividendos, valor final de la cartera) → positivo.

Los traspasos de fondos NO son flujos de caja (fiscalmente neutros, sin entrada
ni salida de dinero): el llamador debe excluirlos. El "valor final" (lo que vale
hoy la cartera) entra como flujo positivo a fecha de hoy.

Función PURA: sin I/O. Recibe (fecha, importe) y devuelve la tasa anual (float)
o None si no es resoluble (p. ej. todos los flujos del mismo signo, o un único
día).
"""

from __future__ import annotations

import math
from datetime import date


def _npv(rate: float, years: list[float], amounts: list[float]) -> float:
    return sum(a / (1.0 + rate) ** y for a, y in zip(amounts, years))


def _bisect(years: list[float], amounts: list[float]) -> float | None:
    lo, hi = -0.999999, 100.0
    f_lo = _npv(lo, years, amounts)
    f_hi = _npv(hi, years, amounts)
    if not (math.isfinite(f_lo) and math.isfinite(f_hi)) or f_lo * f_hi > 0:
        return None
    for _ in range(200):
        mid = (lo + hi) / 2.0
        f_mid = _npv(mid, years, amounts)
        if abs(f_mid) < 1e-7:
            return mid
        if f_lo * f_mid < 0:
            hi = mid
        else:
            lo, f_lo = mid, f_mid
    return (lo + hi) / 2.0


def xirr(cashflows: list[tuple[date, float]]) -> float | None:
    """
    Tasa anual (XIRR) de una serie de flujos (fecha, importe). Devuelve la tasa
    como fracción (0.15 = 15 %) o None si no es resoluble.
    """
    if len(cashflows) < 2:
        return None
    amounts = [a for _, a in cashflows]
    # Hace falta al menos un flujo positivo y uno negativo.
    if not (any(a > 0 for a in amounts) and any(a < 0 for a in amounts)):
        return None
    t0 = min(d for d, _ in cashflows)
    years = [(d - t0).days / 365.0 for d, _ in cashflows]
    if max(years) == 0.0:
        return None  # todos el mismo día: no se puede anualizar

    # Newton-Raphson con guess 0.1; si no converge, bisección.
    rate = 0.1
    for _ in range(100):
        f = _npv(rate, years, amounts)
        df = sum(
            -y * a / (1.0 + rate) ** (y + 1.0)
            for a, y in zip(amounts, years)
        )
        if df == 0 or not math.isfinite(df):
            break
        new_rate = rate - f / df
        if not math.isfinite(new_rate):
            break
        if new_rate <= -0.999999:
            new_rate = -0.999999
        if abs(new_rate - rate) < 1e-8:
            rate = new_rate
            break
        rate = new_rate

    if math.isfinite(rate) and abs(_npv(rate, years, amounts)) < 1e-4 and rate > -0.999999:
        return rate
    return _bisect(years, amounts)


def modified_dietz(
    v_start: float, v_end: float, flows: list[tuple[float, float]],
) -> float | None:
    """
    Rentabilidad del periodo (Modified Dietz), que ajusta por el momento de las
    aportaciones/retiradas. Devuelve la rentabilidad ACUMULADA del periodo (no
    anualizada) como fracción (0.12 = 12 %), o None si no es calculable.

    v_start : valor de la cartera al inicio del periodo.
    v_end   : valor al final.
    flows   : lista de (peso, importe), donde
                peso   = fracción del periodo que el flujo estuvo invertido
                         (1 = al inicio, 0 = al final),
                importe = + aportación (entra dinero), − retirada (sale).

      R = (V_fin − V_ini − ΣF) / (V_ini + Σ peso·F)
    """
    net_flow = sum(a for _, a in flows)
    weighted = sum(w * a for w, a in flows)
    denom = v_start + weighted
    if denom <= 0:
        return None
    return (v_end - v_start - net_flow) / denom
