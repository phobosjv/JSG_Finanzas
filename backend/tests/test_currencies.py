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


def test_divisa_no_publicada_por_bce_rechazada(admin_client):
    """Un código de 3 letras válido en formato pero que el BCE no publica
    (p. ej. 'ABC') se rechaza con 422 y mensaje claro (v1.20.0)."""
    r = _patch_currencies(admin_client, ["USD", "ABC"])
    assert r.status_code == 422
    assert "ABC" in r.json()["detail"]


def test_no_admin_no_puede_cambiar_divisas(auth_client):
    r = _patch_currencies(auth_client, ["GBP"])
    assert r.status_code == 403


# ---------------------------------------------------------------------------
#  Divisas disponibles (lista canónica del BCE) — v1.20.0
# ---------------------------------------------------------------------------

def test_available_currencies_endpoint(admin_client):
    r = admin_client.get("/api/admin/config/available-currencies")
    assert r.status_code == 200
    lst = r.json()["available_currencies"]
    # Incluye divisas conocidas del BCE y NO incluye EUR (es la base implícita).
    assert "USD" in lst and "GBP" in lst and "JPY" in lst
    assert "EUR" not in lst
    assert len(lst) >= 25


def test_available_currencies_no_admin(auth_client):
    r = auth_client.get("/api/admin/config/available-currencies")
    assert r.status_code == 403


# ---------------------------------------------------------------------------
#  Backfill de tipos BCE al añadir una divisa nueva — v1.20.0
# ---------------------------------------------------------------------------

def test_backfill_disparado_al_anadir_divisa_nueva(admin_client, monkeypatch):
    """Añadir una divisa nueva (GBP, respecto al default USD) dispara el
    backfill de tipos del BCE."""
    calls = []
    monkeypatch.setattr(
        "app.api.admin_markets._backfill_currency_rates",
        lambda: calls.append(1),
    )
    r = _patch_currencies(admin_client, ["USD", "GBP"])
    assert r.status_code == 200
    assert calls == [1]


def test_backfill_no_disparado_si_sin_novedades(admin_client, monkeypatch):
    """Guardar la misma lista que el default (solo USD) NO dispara backfill."""
    calls = []
    monkeypatch.setattr(
        "app.api.admin_markets._backfill_currency_rates",
        lambda: calls.append(1),
    )
    r = _patch_currencies(admin_client, ["USD"])
    assert r.status_code == 200
    assert calls == []


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
