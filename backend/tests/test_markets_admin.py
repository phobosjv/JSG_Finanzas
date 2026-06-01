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


# ---------------------------------------------------------------------------
#  is_fund_market (v1.7.0)
# ---------------------------------------------------------------------------

def test_crear_mercado_con_is_fund_market(admin_client):
    """POST /admin/markets con is_fund_market=True lo persiste correctamente."""
    resp = admin_client.post("/api/admin/markets", json={
        "code": "fondos_es",
        "name": "Fondos nacionales",
        "currency": "EUR",
        "fiscal_window_days": 365,
        "is_fund_market": True,
    })
    assert resp.status_code == 201
    data = resp.json()
    assert data["is_fund_market"] is True


def test_crear_mercado_sin_flag_es_false(admin_client):
    """Un mercado creado sin is_fund_market tiene el flag a False por defecto."""
    resp = admin_client.post("/api/admin/markets", json={
        "code": "bolsa_normal",
        "name": "Bolsa normal",
        "currency": "EUR",
        "fiscal_window_days": 60,
    })
    assert resp.status_code == 201
    assert resp.json()["is_fund_market"] is False


def test_patch_activa_is_fund_market(admin_client, seed_markets):
    """PATCH puede activar is_fund_market en un mercado existente."""
    resp = admin_client.patch("/api/admin/markets/ibex35", json={"is_fund_market": True})
    assert resp.status_code == 200
    assert resp.json()["is_fund_market"] is True

    # Y desactivarlo también
    resp2 = admin_client.patch("/api/admin/markets/ibex35", json={"is_fund_market": False})
    assert resp2.status_code == 200
    assert resp2.json()["is_fund_market"] is False


def test_fondos_incluidos_en_informe_fiscal(admin_client):
    """
    v1.7.0: las ganancias de fondos SÍ entran en el informe fiscal (acumulan
    en la base del ahorro como las acciones). Lo que no tributa es el TRASPASO,
    no el reembolso. Aquí ambos valores (acción y reembolso de fondo) deben
    sumar a total_gains_eur.

    Usa admin_client para todas las operaciones (admins también tienen portfolio).
    """
    # Crear mercados
    r1 = admin_client.post("/api/admin/markets", json={
        "code": "acciones_test", "name": "Acciones", "currency": "EUR",
        "fiscal_window_days": 60, "is_fund_market": False,
    })
    assert r1.status_code == 201
    r2 = admin_client.post("/api/admin/markets", json={
        "code": "fondos_test", "name": "Fondos", "currency": "EUR",
        "fiscal_window_days": 365, "is_fund_market": True,
    })
    assert r2.status_code == 201

    # Valores en cada mercado (se usa /api/securities porque /api/admin/securities
    # hace lo mismo pero devuelve el objeto con id directamente)
    sec_accion = admin_client.post("/api/securities", json={
        "name": "Santander Test", "isin": "ES0113900J37", "yahoo_ticker": "SAN_TFUND.MC",
        "market": "acciones_test", "currency": "EUR",
    }).json()["id"]
    sec_fondo = admin_client.post("/api/securities", json={
        "name": "Fondo Test", "isin": "LU0000000001", "yahoo_ticker": "0P0001TEST.F",
        "market": "fondos_test", "currency": "EUR",
    }).json()["id"]

    # Crear posiciones y operar (como admin)
    pos_accion = admin_client.post("/api/portfolio/positions", json={"security_id": sec_accion}).json()["id"]
    pos_fondo  = admin_client.post("/api/portfolio/positions", json={"security_id": sec_fondo}).json()["id"]

    for pos_id, price_buy, price_sell in [
        (pos_accion, "3.50", "4.00"),
        (pos_fondo,  "100.00", "120.00"),
    ]:
        rb = admin_client.post(f"/api/portfolio/{pos_id}/transactions", json={
            "type": "buy", "date": "2023-01-10", "shares": "10", "price": price_buy,
            "fee": "0", "currency": "EUR", "exchange_rate": "1",
        })
        assert rb.status_code == 201, f"buy pos={pos_id}: {rb.text}"
        rs = admin_client.post(f"/api/portfolio/{pos_id}/transactions", json={
            "type": "sell", "date": "2023-06-01", "shares": "10", "price": price_sell,
            "fee": "0", "currency": "EUR", "exchange_rate": "1",
        })
        assert rs.status_code == 201, f"sell pos={pos_id}: {rs.text}"

    # Informe fiscal 2023
    # Ganancia acción: 10 × (4.00 - 3.50) = 5 EUR
    # Ganancia fondo (reembolso): 10 × (120.00 - 100.00) = 200 EUR  → SÍ incluido
    resp = admin_client.get("/api/reports/tax/2023/summary")
    assert resp.status_code == 200
    report = resp.json()

    gains = report["total_gains_eur"]
    assert 204.9 < gains < 205.1, (
        f"total_gains_eur={gains}: debería ser ~205€ (acción + reembolso de fondo). "
        f"Los reembolsos de fondos acumulan en la base del ahorro."
    )
