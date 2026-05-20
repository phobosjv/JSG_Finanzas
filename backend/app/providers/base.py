"""
providers/base.py
=================
Interfaces y tipos de datos compartidos por todos los proveedores de precios.

Separacion de responsabilidades
--------------------------------
- PriceProvider: cotizaciones historicas y precio en vivo.
- RateProvider: tipos de cambio EUR/USD del BCE.

Los proveedores no conocen SQLAlchemy, FastAPI ni ninguna otra capa.
Solo reciben parametros simples y devuelven dataclasses puros.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date
from decimal import Decimal


@dataclass
class PriceBar:
    """Un cierre diario de un valor."""
    date: date
    close: Decimal
    volume: int | None


@dataclass
class LiveQuote:
    """Cotizacion en tiempo real (o del ultimo cierre disponible)."""
    last_price: Decimal
    prev_close: Decimal
    # (last_price - prev_close) / prev_close * 100, redondeado a 2 decimales
    daily_change_pct: Decimal
    # Ultimo dividendo por accion publicado; None si no hay datos.
    last_dividend: Decimal | None


class PriceProvider(ABC):
    @abstractmethod
    def fetch_history(
        self, ticker: str, from_date: date, to_date: date
    ) -> list[PriceBar]:
        """
        Retorna cierres diarios [from_date, to_date] inclusive.
        Puede devolver lista vacia si no hay datos para el rango.
        """

    @abstractmethod
    def fetch_live_quote(self, ticker: str) -> LiveQuote:
        """
        Retorna la cotizacion mas reciente disponible.
        Lanza ValueError si no hay suficientes datos.
        """


class RateProvider(ABC):
    @abstractmethod
    def fetch_rates(self, from_date: date, to_date: date) -> dict[str, Decimal]:
        """
        Retorna tipos EUR/USD del BCE para el rango [from_date, to_date].

        Clave: 'YYYY-MM-DD'. Valor: USD por 1 EUR (p.ej. 1.10 significa
        que 1 EUR vale 1.10 USD → euros = dolares / rate).

        Solo incluye dias habiles (el BCE no publica en fines de semana
        ni festivos). El scheduler decide que hacer con los huecos.
        """
