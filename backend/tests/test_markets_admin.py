"""
test_markets_admin.py
=====================
Tests del router /admin/markets y /admin/config.
Solo administradores pueden usar estos endpoints.
"""

import pytest


# ---------------------------------------------------------------------------
#  GET /admin/markets
# ---------------------------------------------------------------------------

def test_admin_lista_mercados(admin_client, seed_markets):
    resp = admin_client.get("/api/admin/markets")
    assert resp.status_code == 200
    codes = [m["code"] for m in resp.json()]
    assert "ibex35" in codes
    assert "continuo" in codes
    assert "nasdaq" in codes


def test_usuario_normal_no_puede_listar_mercados(auth_client):
    resp = auth_client.get("/api/admin/markets")
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
#  POST /admin/markets
# ---------------------------------------------------------------------------

def test_admin_crea_mercado(admin_client):
    resp = admin_client.post("/api/admin/markets", json={
        "code": "euronext",
        "name": "Euronext Paris",
        "index_ticker": "^FCHI",
        "currency": "EUR",
        "fiscal_window_days": 60,
    })
    assert resp.status_code == 201
    data = resp.json()
    assert data["code"] == "euronext"
    assert data["name"] == "Euronext Paris"
    assert data["fiscal_window_days"] == 60


def test_admin_crea_mercado_codigo_duplicado(admin_client, seed_markets):
    resp = admin_client.post("/api/admin/markets", json={
        "code": "ibex35",
        "name": "Duplicado",
        "currency": "EUR",
    })
    assert resp.status_code == 409


def test_admin_crea_mercado_codigo_invalido(admin_client):
    resp = admin_client.post("/api/admin/markets", json={
        "code": "código con espacios",
        "name": "Inválido",
        "currency": "EUR",
    })
    assert resp.status_code == 422


def test_usuario_normal_no_puede_crear_mercado(auth_client):
    resp = auth_client.post("/api/admin/markets", json={
        "code": "nyse",
        "name": "NYSE",
        "currency": "USD",
    })
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
#  PATCH /admin/markets/{code}
# ---------------------------------------------------------------------------

def test_admin_actualiza_mercado(admin_client, seed_markets):
    resp = admin_client.patch("/api/admin/markets/ibex35", json={
        "fiscal_window_days": 90,
    })
    assert resp.status_code == 200
    assert resp.json()["fiscal_window_days"] == 90


def test_admin_actualiza_mercado_inexistente(admin_client):
    resp = admin_client.patch("/api/admin/markets/noexiste", json={
        "name": "X",
    })
    assert resp.status_code == 404


def test_admin_actualiza_mercado_currency_invalida(admin_client, seed_markets):
    """PATCH con divisa no soportada debe devolver 422."""
    resp = admin_client.patch("/api/admin/markets/ibex35", json={
        "currency": "XYZ",
    })
    assert resp.status_code == 422


def test_admin_actualiza_mercado_fiscal_window_invalido(admin_client, seed_markets):
    """PATCH con fiscal_window_days <= 0 debe devolver 422."""
    r0 = admin_client.patch("/api/admin/markets/ibex35", json={"fiscal_window_days": 0})
    assert r0.status_code == 422
    r_neg = admin_client.patch("/api/admin/markets/ibex35", json={"fiscal_window_days": -10})
    assert r_neg.status_code == 422


# ---------------------------------------------------------------------------
#  DELETE /admin/markets/{code}
# ---------------------------------------------------------------------------

def test_admin_borra_mercado_vacio(admin_client):
    # Crear un mercado sin valores asignados
    admin_client.post("/api/admin/markets", json={
        "code": "tmp_mkt", "name": "Temp", "currency": "EUR",
    })
    resp = admin_client.delete("/api/admin/markets/tmp_mkt")
    assert resp.status_code == 204


def test_admin_borra_mercado_con_valores_falla(admin_client, seed_markets):
    """No se puede borrar un mercado que tiene securities asignados."""
    # Crear security asignado a ibex35
    admin_client.post("/api/securities", json={
        "name": "Test", "yahoo_ticker": "TST.MC",
        "market": "ibex35", "currency": "EUR",
    })
    resp = admin_client.delete("/api/admin/markets/ibex35")
    assert resp.status_code == 409


def test_admin_borra_mercado_inexistente(admin_client):
    resp = admin_client.delete("/api/admin/markets/noexiste")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
#  GET /admin/config
# ---------------------------------------------------------------------------

def test_admin_get_config(admin_client):
    resp = admin_client.get("/api/admin/config")
    assert resp.status_code == 200
    data = resp.json()
    assert "snapshot_interval_minutes" in data
    assert isinstance(data["snapshot_interval_minutes"], int)


def test_usuario_normal_no_puede_ver_config(auth_client):
    resp = auth_client.get("/api/admin/config")
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
#  PATCH /admin/config/snapshot-interval
# ---------------------------------------------------------------------------

def test_admin_cambia_intervalo(admin_client):
    resp = admin_client.patch("/api/admin/config/snapshot-interval", json={"minutes": 15})
    assert resp.status_code == 200
    assert resp.json()["snapshot_interval_minutes"] == 15

    # Verificar que se persistió
    cfg = admin_client.get("/api/admin/config").json()
    assert cfg["snapshot_interval_minutes"] == 15


def test_admin_intervalo_fuera_de_rango(admin_client):
    # < 5 minutos
    r1 = admin_client.patch("/api/admin/config/snapshot-interval", json={"minutes": 3})
    assert r1.status_code == 422
    # > 60 minutos
    r2 = admin_client.patch("/api/admin/config/snapshot-interval", json={"minutes": 90})
    assert r2.status_code == 422


def test_usuario_normal_no_puede_cambiar_intervalo(auth_client):
    resp = auth_client.patch("/api/admin/config/snapshot-interval", json={"minutes": 10})
    assert resp.status_code == 403
