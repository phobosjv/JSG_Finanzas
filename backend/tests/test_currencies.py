"""
test_currencies.py
==================
Tests de la gestión de divisas configurables (v1.6.16).

Cubre:
- Admin añade y elimina divisas vía PATCH /admin/config/currencies.
- GET /config público expone supported_currencies.
- GET /admin/config expone supported_currencies.
- Transacción con divisa no configurada → error.
- Transacción con divisa no-EUR recién configurada → éxito.
- No-admin no puede cambiar divisas.
- exchange-rate acepta parámetro currency.
"""

from __future__ import annotations


# ---------------------------------------------------------------------------
#  Helpers
# ---------------------------------------------------------------------------

def _crear_security(client, ticker="SAN.MC", market="ibex35"):
    r = client.post("/api/securities", json={
        "name": ticker, "yahoo_ticker": ticker,
        "market": market, "currency": "EUR",
    })
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _patch_currencies(client, currencies):
    return client.patch("/api/admin/config/currencies", json={"currencies": currencies})


def _get_pos(auth_client, sec_id):
    r = auth_client.post("/api/portfolio/positions", json={"security_id": sec_id})
    assert r.status_code == 201
    return r.json()["id"]


# ---------------------------------------------------------------------------
#  Gestión admin de divisas
# ---------------------------------------------------------------------------

def test_admin_añade_divisas(admin_client):
    r = _patch_currencies(admin_client, ["USD", "GBP"])
    assert r.status_code == 200
    d = r.json()
    assert "EUR" in d["supported_currencies"]
    assert "GBP" in d["supported_currencies"]
    assert "USD" in d["supported_currencies"]


def test_eur_siempre_incluida_aunque_no_se_envie(admin_client):
    r = _patch_currencies(admin_client, ["GBP"])
    assert r.status_code == 200
    assert "EUR" in r.json()["supported_currencies"]


def test_codigo_invalido_da_error(admin_client):
    # 4 letras → inválido
    r = _patch_currencies(admin_client, ["GBPP"])
    assert r.status_code == 422


def test_no_admin_no_puede_cambiar_divisas(auth_client):
    r = _patch_currencies(auth_client, ["GBP"])
    assert r.status_code == 403


# ---------------------------------------------------------------------------
#  GET /config público
# ---------------------------------------------------------------------------

def test_config_publico_incluye_divisas(client):
    r = client.get("/api/config")
    assert r.status_code == 200
    d = r.json()
    assert "supported_currencies" in d
    assert "EUR" in d["supported_currencies"]


def test_admin_config_incluye_divisas(admin_client):
    r = admin_client.get("/api/admin/config")
    assert r.status_code == 200
    assert "supported_currencies" in r.json()


# ---------------------------------------------------------------------------
#  Validación en transacciones
# ---------------------------------------------------------------------------

def test_transaccion_divisa_no_configurada_da_error(auth_client, admin_client, seed_markets):
    """GBP no está configurada por defecto → error al importar CSV."""
    _crear_security(admin_client)
    # Por defecto solo hay EUR y USD
    r = auth_client.post("/api/portfolio/import-csv", json={"rows": [{
        "type": "buy", "ticker": "SAN.MC", "date": "2023-01-15",
        "shares": 100, "price": 3.25, "fee": 0.5,
        "currency": "GBP", "exchange_rate": 0.86,
    }]})
    assert r.status_code == 200
    d = r.json()
    # GBP no configurada → error de fila
    assert d["transactions_added"] == 0
    assert len(d["errors"]) == 1
    assert "GBP" in d["errors"][0]["reason"]


def test_transaccion_divisa_configurada_ok(auth_client, admin_client, seed_markets):
    """Una vez añadida GBP, las transacciones en GBP se aceptan."""
    _crear_security(admin_client)
    _patch_currencies(admin_client, ["USD", "GBP"])
    r = auth_client.post("/api/portfolio/import-csv", json={"rows": [{
        "type": "buy", "ticker": "SAN.MC", "date": "2023-01-15",
        "shares": 100, "price": 3.25, "fee": 0.5,
        "currency": "GBP", "exchange_rate": 0.86,
    }]})
    assert r.status_code == 200
    d = r.json()
    assert d["transactions_added"] == 1
    assert d["errors"] == []


# ---------------------------------------------------------------------------
#  exchange-rate con currency param
# ---------------------------------------------------------------------------

def test_exchange_rate_acepta_currency_param(auth_client):
    """El endpoint acepta el parámetro currency y devuelve el formato correcto."""
    r = auth_client.get("/api/markets/exchange-rate?date=2023-01-15&currency=GBP")
    assert r.status_code == 200
    d = r.json()
    # Puede ser rate=None si Yahoo no responde en test, pero el formato es correcto
    assert "rate" in d
    assert "source" in d
