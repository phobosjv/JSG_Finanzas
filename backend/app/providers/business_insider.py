"""
providers/business_insider.py
=============================
Búsqueda heurística de ISIN por NOMBRE contra el buscador público de
markets.businessinsider.com (la misma fuente que usa yfinance por dentro).

Se usa como SEGUNDA pasada del rellenado de ISINs: para los valores que Yahoo
no resuelve por ticker, se busca por nombre y se acepta un ISIN solo si hay una
coincidencia CLARA (criterio conservador), para no asignar un ISIN equivocado.

Formato de la respuesta (JS):
    mmSuggestDeliver(0, new Array("Name","Category","Keywords",...),
        new Array(
            new Array("Iberdrola SA", "Stocks", "IBDSF|ES0144580Y14|IBDSF||IBE", ...),
            new Array("Iberdrola SA (spons. ADRs)", "Stocks", "IBDRY|US4507371015|IBDRY||", ...),
            new Array("Iberdrola International B.V.", "Bonds", "906796|US29266MAE93", ...),
            ...))
Cada fila: (Nombre, Categoría, Keywords, ...). En "Keywords", separado por '|',
aparece el ISIN y los tickers (incluido el nativo del mercado, p. ej. "IBE").
"""

from __future__ import annotations

import re

import httpx

from app.providers.yahoo import _normalize_isin

_BI_URL = "https://markets.businessinsider.com/ajax/SearchController_Suggest"

# Captura las tres primeras cadenas de cada `new Array("Nombre","Categoría","Keywords"...`.
_ROW_RE = re.compile(
    r'new Array\("((?:[^"\\]|\\.)*)",\s*"((?:[^"\\]|\\.)*)",\s*"((?:[^"\\]|\\.)*)"'
)

# Solo renta variable / fondos / ETFs: se excluyen bonos, certificados, etc.,
# que comparten nombre pero no son el valor que el usuario tiene en cartera.
_EQUITY_CATS = {"STOCKS", "FUNDS", "FUND", "ETF", "ETFS", "INDEX FUNDS", "FONDS"}


def _base_ticker(ticker: str | None) -> str | None:
    """Quita el sufijo de mercado de Yahoo ('IBE.MC' -> 'IBE')."""
    if not ticker:
        return None
    return ticker.split(".")[0].strip().upper() or None


def parse_isin_from_suggest(text: str, base_ticker: str | None) -> str | None:
    """
    Extrae un ISIN de la respuesta del buscador, de forma CONSERVADORA:

      1. Si el ticker nativo (base_ticker) coincide con algún campo de una única
         fila de renta variable/fondo, se devuelve el ISIN de esa fila.
      2. Si no hay coincidencia por ticker pero toda la respuesta de renta
         variable apunta a UN único ISIN, se devuelve ese.
      3. En cualquier otro caso (ambiguo o sin resultados) devuelve None.
    """
    matches_by_ticker: set[str] = set()
    all_equity_isins: set[str] = set()

    for _name, category, keywords in _ROW_RE.findall(text):
        if category.strip().upper() not in _EQUITY_CATS:
            continue
        fields = [f.strip().upper() for f in keywords.split("|")]
        isin = next((v for v in (_normalize_isin(f) for f in fields) if v), None)
        if not isin:
            continue
        all_equity_isins.add(isin)
        if base_ticker and base_ticker in fields:
            matches_by_ticker.add(isin)

    if len(matches_by_ticker) == 1:
        return next(iter(matches_by_ticker))
    if not matches_by_ticker and len(all_equity_isins) == 1:
        return next(iter(all_equity_isins))
    return None


def search_isin_by_name(name: str, ticker: str | None = None, *, timeout: float = 8.0) -> str | None:
    """
    Busca el ISIN de un valor por su nombre en Business Insider.

    Devuelve el ISIN solo ante una coincidencia clara (ver parse_isin_from_suggest)
    o None. Nunca lanza: cualquier fallo de red se traduce en None para que el
    pipeline pueda continuar con el resto de valores.
    """
    if not name:
        return None
    try:
        resp = httpx.get(
            _BI_URL,
            params={"max_results": 25, "query": name},
            timeout=timeout,
            headers={"User-Agent": "Mozilla/5.0"},
        )
        text = resp.text
    except Exception:
        return None
    return parse_isin_from_suggest(text, _base_ticker(ticker))
