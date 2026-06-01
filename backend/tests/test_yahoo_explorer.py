"""
test_yahoo_explorer.py
======================
Tests del explorador de valores Yahoo Finance (v1.6.18).

GET /api/admin/securities/search?q=<texto>

Todos los tests mockean yf.Search para no hacer llamadas reales de red.
"""

from __future__ import annotations

import pytest


# ---------------------------------------------------------------------------
#  Mock de yf.Search
# ---------------------------------------------------------------------------

def _crear_security(client, ticker="SAN.MC", market="ibex35"):
    r = client.post("/api/securities", json={
        "name": ticker, "yahoo_ticker": ticker,
        "market": market, "currency": "EUR",
    })
    assert r.status_code == 201, r.text
    return r.json()["id"]


class _FakeSearch:
    """Simula yfinance.Search con resultados fijos."""
    def __init__(self, query, max_results=15, enable_fuzzy_query=False):
        self.quotes = [
            {
                "symbol": "SAN.MC",
                "shortname": "Banco Santander",
                "exchange": "MCE",
                "exchDisp": "Madrid",
                "quoteType": "EQUITY",
                "currency": "EUR",
            },
            {
                "symbol": "AAPL",
                "shortname": "Apple Inc.",
                "exchange": "NMS",
                "exchDisp": "NasdaqGS",
                "quoteType": "EQUITY",
                "currency": "USD",
            },
        ]


@pytest.fixture(autouse=True)
def mock_yf_search(monkeypatch):
    """Reemplaza yf.Search en el módulo del endpoint para evitar llamadas reales."""
    import yfinance as yf
    monkeypatch.setattr(yf, "Search", _FakeSearch)


# ---------------------------------------------------------------------------
#  Tests
# ---------------------------------------------------------------------------

def test_search_devuelve_resultados(admin_client, seed_markets):
    r = admin_client.get("/api/admin/securities/search?q=santander")
    assert r.status_code == 200
    data = r.json()
    assert len(data) == 2
    san = next(d for d in data if d["ticker"] == "SAN.MC")
    assert san["name"] == "Banco Santander"
    assert san["exchange"] == "Madrid"
    assert san["type"] == "EQUITY"
    assert san["currency"] == "EUR"
    # No está en el catálogo (no se ha creado)
    assert san["in_catalog"] is False
    assert san["catalog_market"] is None


def test_search_marca_in_catalog(admin_client, seed_markets):
    """Si el ticker ya está en el catálogo, in_catalog=True con el mercado correcto."""
    _crear_security(admin_client, ticker="SAN.MC", market="ibex35")
    r = admin_client.get("/api/admin/securities/search?q=santander")
    assert r.status_code == 200
    data = r.json()
    san = next(d for d in data if d["ticker"] == "SAN.MC")
    assert san["in_catalog"] is True
    assert san["catalog_market"] == "ibex35"
    # AAPL no está en catálogo
    aapl = next(d for d in data if d["ticker"] == "AAPL")
    assert aapl["in_catalog"] is False


def test_search_sin_autenticacion(client, seed_markets):
    r = client.get("/api/admin/securities/search?q=santander")
    assert r.status_code == 401


def test_search_no_admin(auth_client, seed_markets):
    r = auth_client.get("/api/admin/securities/search?q=santander")
    assert r.status_code == 403
