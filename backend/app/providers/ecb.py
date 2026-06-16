"""
providers/ecb.py
================
Implementacion de RateProvider usando la API SDMX del Banco Central Europeo.

La API
------
Endpoint publico, sin autenticacion:
  https://data-api.ecb.europa.eu/service/data/EXR/D.USD.EUR.SP00.A
  ?format=csvdata&startPeriod=YYYY-MM-DD&endPeriod=YYYY-MM-DD

Devuelve CSV con cabecera; las columnas relevantes son TIME_PERIOD y
OBS_VALUE. OBS_VALUE es "USD por 1 EUR" (tipo de referencia del BCE).
Ejemplo: 1.0944 → 1 EUR = 1.0944 USD → euros = dolares / 1.0944

Huecos en la serie
------------------
El BCE solo publica en dias habiles. Fines de semana y festivos no
aparecen. El scheduler decide que tipo usar para esos dias (normalmente
el ultimo publicado). El proveedor devuelve solo lo que el BCE da.

Timeout
-------
Se usa un timeout generoso (30 s) porque el endpoint del BCE puede ser
lento en horas pico.
"""

from __future__ import annotations

import csv
import io
from datetime import date
from decimal import Decimal, InvalidOperation

import httpx

from app.providers.base import RateProvider

# Divisas que publica el BCE en sus tipos de referencia diarios (euro foreign
# exchange reference rates). Es el conjunto CERRADO de divisas que la app puede
# manejar de verdad: solo de estas existe tipo de cambio. Fuente única de verdad
# para validar el alta de divisas y para alimentar el buscador del AdminPanel.
# (RUB se retiró en 2022; no se incluye.)
ECB_CURRENCIES: tuple[str, ...] = (
    "USD", "JPY", "BGN", "CZK", "DKK", "GBP", "HUF", "PLN", "RON", "SEK",
    "CHF", "ISK", "NOK", "TRY", "AUD", "BRL", "CAD", "CNY", "HKD", "IDR",
    "ILS", "INR", "KRW", "MXN", "MYR", "NZD", "PHP", "SGD", "THB", "ZAR",
)

_ECB_URL = (
    "https://data-api.ecb.europa.eu/service/data/EXR/D.USD.EUR.SP00.A"
    "?format=csvdata"
)

# Dimensión 'currency' vacía → el BCE devuelve TODAS las divisas (~30) en una
# sola petición. La CSV incluye entonces la columna CURRENCY.
_ECB_URL_ALL = (
    "https://data-api.ecb.europa.eu/service/data/EXR/D..EUR.SP00.A"
    "?format=csvdata"
)


class EcbProvider(RateProvider):

    def fetch_rates(self, from_date: date, to_date: date) -> dict[str, Decimal]:
        params = {
            "startPeriod": from_date.isoformat(),
            "endPeriod": to_date.isoformat(),
        }
        response = httpx.get(_ECB_URL, params=params, timeout=30.0)
        response.raise_for_status()
        return _parse_csv(response.text)

    def fetch_all_rates(
        self, from_date: date, to_date: date
    ) -> dict[tuple[str, str], Decimal]:
        """
        Tipos de TODAS las divisas del BCE en una sola petición.
        Devuelve {(fecha, divisa): rate}, con rate = "{divisa} por 1 EUR".
        """
        params = {
            "startPeriod": from_date.isoformat(),
            "endPeriod": to_date.isoformat(),
        }
        response = httpx.get(_ECB_URL_ALL, params=params, timeout=30.0)
        response.raise_for_status()
        return _parse_csv_multi(response.text)


def _parse_csv(text: str) -> dict[str, Decimal]:
    """
    Parsea el CSV del BCE y retorna {fecha: rate}.
    Ignora filas con datos ausentes o malformados en lugar de abortar.
    """
    rates: dict[str, Decimal] = {}
    reader = csv.DictReader(io.StringIO(text))
    for row in reader:
        date_str = row.get("TIME_PERIOD") or row.get("time_period", "")
        value_str = row.get("OBS_VALUE") or row.get("obs_value", "")
        if not date_str or not value_str:
            continue
        try:
            rates[date_str.strip()] = Decimal(value_str.strip())
        except InvalidOperation:
            continue
    return rates


def _parse_csv_multi(text: str) -> dict[tuple[str, str], Decimal]:
    """
    Parsea el CSV multi-divisa del BCE → {(fecha, divisa): rate}.
    La columna CURRENCY identifica la divisa (USD, GBP, JPY…). Ignora EUR (la
    base) y filas malformadas.
    """
    rates: dict[tuple[str, str], Decimal] = {}
    reader = csv.DictReader(io.StringIO(text))
    for row in reader:
        date_str = (row.get("TIME_PERIOD") or row.get("time_period") or "").strip()
        value_str = (row.get("OBS_VALUE") or row.get("obs_value") or "").strip()
        currency = (row.get("CURRENCY") or row.get("currency") or "").strip().upper()
        if not date_str or not value_str or not currency or currency == "EUR":
            continue
        try:
            rates[(date_str, currency)] = Decimal(value_str)
        except InvalidOperation:
            continue
    return rates
