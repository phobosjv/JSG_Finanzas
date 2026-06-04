"""
test_isin_pipeline.py
=====================
Tests del pipeline admin que rellena ISINs vacíos desde Yahoo
(POST /api/admin/securities/fill-isins) y de la normalización de ISIN
del proveedor Yahoo.

La llamada a Yahoo se mockea (monkeypatch sobre YahooProvider.fetch_isin)
para no hacer red.
"""

import pytest

from app.providers.yahoo import _normalize_isin


# ---------------------------------------------------------------------------
#  Normalización de ISIN
# ---------------------------------------------------------------------------

def test_normalize_isin_valido():
    assert _normalize_isin("ES0144580Y14") == "ES0144580Y14"
    # minúsculas / espacios se sanean
    assert _normalize_isin(" us0378331005 ") == "US0378331005"


def test_normalize_isin_rechaza_basura():
    assert _normalize_isin("-") is None       # Yahoo cuando no lo conoce
    assert _normalize_isin("") is None
    assert _normalize_isin(None) is None
    assert _normalize_isin("ES123") is None    # demasiado corto
    assert _normalize_isin("0044580Y14XY") is None  # no empieza por 2 letras
    assert _normalize_isin(12345) is None      # no es str


# ---------------------------------------------------------------------------
#  POST /admin/securities/fill-isins
# ---------------------------------------------------------------------------

def _crear_sec(client, name, ticker, isin=None):
    body = {"name": name, "yahoo_ticker": ticker, "market": "ibex35", "currency": "EUR"}
    if isin:
        body["isin"] = isin
    r = client.post("/api/securities", json=body)
    assert r.status_code == 201, r.text
    return r.json()["id"]


def test_fill_isins_rellena_los_vacios(admin_client, seed_markets, monkeypatch):
    """Rellena solo los valores sin ISIN; los que Yahoo no resuelve van a not_found."""
    _crear_sec(admin_client, "Con ISIN", "SAN.MC", isin="ES0113900J37")
    _crear_sec(admin_client, "Sin ISIN A", "ITX.MC")
    _crear_sec(admin_client, "Sin ISIN B", "DESCONOCIDO.MC")

    fake = {"ITX.MC": "ES0148396007", "DESCONOCIDO.MC": None}

    def fake_fetch_isin(self, ticker):
        return fake.get(ticker)

    monkeypatch.setattr(
        "app.providers.yahoo.YahooProvider.fetch_isin", fake_fetch_isin
    )

    r = admin_client.post("/api/admin/securities/fill-isins")
    assert r.status_code == 200
    data = r.json()
    assert data["checked"] == 2          # solo los dos sin ISIN
    assert data["updated"] == 1          # ITX resuelto
    assert data["not_found"] == ["DESCONOCIDO.MC"]


def test_fill_isins_persiste_y_no_resobrescribe(admin_client, seed_markets, monkeypatch):
    """Tras rellenar, el valor deja de estar pendiente y el ISIN existente no se toca."""
    _crear_sec(admin_client, "Sin ISIN", "ITX.MC")

    monkeypatch.setattr(
        "app.providers.yahoo.YahooProvider.fetch_isin",
        lambda self, ticker: "ES0148396007",
    )
    r1 = admin_client.post("/api/admin/securities/fill-isins")
    assert r1.json()["updated"] == 1

    # Segunda pasada: ya no hay pendientes; aunque el mock devuelva otro ISIN,
    # no se vuelve a tocar (no figura entre los pendientes).
    monkeypatch.setattr(
        "app.providers.yahoo.YahooProvider.fetch_isin",
        lambda self, ticker: "XX0000000000",
    )
    r2 = admin_client.post("/api/admin/securities/fill-isins")
    assert r2.json()["checked"] == 0
    assert r2.json()["updated"] == 0


def test_fill_isins_no_admin(auth_client, seed_markets):
    resp = auth_client.post("/api/admin/securities/fill-isins")
    assert resp.status_code == 403
