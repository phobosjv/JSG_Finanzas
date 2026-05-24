"""
test_api.py
===========
Tests de integración de los endpoints FastAPI.

Cada test usa la fixture 'client' o 'auth_client' (TestClient con BD
en memoria). No hay red real, no hay fichero de BD en disco.

Aritmética de los tests de cartera
------------------------------------
Compra: 10 acc × 15.00 € + comisión 5.00 € → coste total 155.00 €
Precio medio = 155.00 / 10 = 15.50 €/acc

Posición cerrada (test_portfolio_closed):
  Compra: 5 acc × 10.00 € + 0 fee → coste 50.00 €
  Venta:  5 acc × 12.00 € + 0 fee → ingresos 60.00 €
  Beneficio realizado = 60.00 - 50.00 = 10.00 €
"""

import pytest


# ---------------------------------------------------------------------------
#  Auth
# ---------------------------------------------------------------------------

def test_login_exitoso(client, test_user):
    resp = client.post("/api/auth/login", json={
        "username": "testuser",
        "password": "testpass123",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["username"] == "testuser"
    assert "id" in data
    # La cookie de sesión debe estar presente
    assert "session" in client.cookies


def test_login_credenciales_incorrectas(client, test_user):
    resp = client.post("/api/auth/login", json={
        "username": "testuser",
        "password": "wrongpassword",
    })
    assert resp.status_code == 401


def test_login_usuario_inexistente(client):
    resp = client.post("/api/auth/login", json={
        "username": "nobody",
        "password": "whatever",
    })
    assert resp.status_code == 401


def test_me_sin_sesion(client):
    resp = client.get("/api/auth/me")
    assert resp.status_code == 401


def test_me_con_sesion(auth_client, test_user):
    resp = auth_client.get("/api/auth/me")
    assert resp.status_code == 200
    assert resp.json()["username"] == "testuser"


def test_logout(auth_client):
    resp = auth_client.post("/api/auth/logout")
    assert resp.status_code == 204
    # Tras logout, /me debe devolver 401
    resp2 = auth_client.get("/api/auth/me")
    assert resp2.status_code == 401


# ---------------------------------------------------------------------------
#  Catálogo de valores (securities)
# ---------------------------------------------------------------------------

def test_securities_lista_vacia(auth_client):
    resp = auth_client.get("/api/securities")
    assert resp.status_code == 200
    assert resp.json() == []


def test_crear_security(admin_client, seed_markets):
    resp = admin_client.post("/api/securities", json={
        "name": "Banco Santander",
        "yahoo_ticker": "SAN.MC",
        "market": "ibex35",
        "currency": "EUR",
    })
    assert resp.status_code == 201
    data = resp.json()
    assert data["yahoo_ticker"] == "SAN.MC"
    assert data["market"] == "ibex35"
    assert "id" in data


def test_crear_security_ticker_duplicado(admin_client, seed_markets):
    body = {"name": "Santander", "yahoo_ticker": "SAN.MC", "market": "ibex35", "currency": "EUR"}
    admin_client.post("/api/securities", json=body)
    resp = admin_client.post("/api/securities", json=body)
    assert resp.status_code == 409


def test_crear_security_market_invalido(admin_client, seed_markets):
    resp = admin_client.post("/api/securities", json={
        "name": "Test",
        "yahoo_ticker": "TEST",
        "market": "nyse",       # no existe en la tabla de mercados
        "currency": "USD",
    })
    assert resp.status_code == 422


def test_crear_security_requiere_admin(auth_client, seed_markets):
    """Un usuario normal recibe 403 al intentar crear un security."""
    resp = auth_client.post("/api/securities", json={
        "name": "Santander", "yahoo_ticker": "SAN.MC",
        "market": "ibex35", "currency": "EUR",
    })
    assert resp.status_code == 403


def test_listar_securities(admin_client, seed_markets):
    admin_client.post("/api/securities", json={
        "name": "Apple", "yahoo_ticker": "AAPL", "market": "nasdaq", "currency": "USD",
    })
    resp = admin_client.get("/api/securities")
    assert resp.status_code == 200
    assert len(resp.json()) == 1


def test_borrar_security_sin_posiciones(admin_client, seed_markets):
    r = admin_client.post("/api/securities", json={
        "name": "Temporal", "yahoo_ticker": "TMP", "market": "ibex35", "currency": "EUR",
    })
    sec_id = r.json()["id"]
    resp = admin_client.delete(f"/api/securities/{sec_id}")
    assert resp.status_code == 204


def test_obtener_security_por_id(admin_client, seed_markets):
    r = admin_client.post("/api/securities", json={
        "name": "Inditex", "yahoo_ticker": "ITX.MC", "market": "ibex35", "currency": "EUR",
    })
    sec_id = r.json()["id"]
    resp = admin_client.get(f"/api/securities/{sec_id}")
    assert resp.status_code == 200
    assert resp.json()["yahoo_ticker"] == "ITX.MC"


def test_obtener_security_inexistente(auth_client):
    resp = auth_client.get("/api/securities/9999")
    assert resp.status_code == 404


def test_borrar_security_inexistente(admin_client):
    resp = admin_client.delete("/api/securities/9999")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
#  Portfolio: posiciones y transacciones
# ---------------------------------------------------------------------------

def _crear_security(client, ticker="SAN.MC"):
    r = client.post("/api/securities", json={
        "name": "Test security",
        "yahoo_ticker": ticker,
        "market": "ibex35",
        "currency": "EUR",
    })
    return r.json()["id"]


def test_portfolio_vacio(auth_client):
    resp = auth_client.get("/api/portfolio")
    assert resp.status_code == 200
    assert resp.json() == []


def test_crear_posicion(admin_client, seed_markets):
    sec_id = _crear_security(admin_client)
    resp = admin_client.post("/api/portfolio/positions", json={"security_id": sec_id})
    assert resp.status_code == 201
    data = resp.json()
    assert data["security_id"] == sec_id


def test_crear_posicion_idempotente(admin_client, seed_markets):
    """Crear la misma posición dos veces devuelve la existente sin error."""
    sec_id = _crear_security(admin_client)
    body = {"security_id": sec_id}
    r1 = admin_client.post("/api/portfolio/positions", json=body)
    r2 = admin_client.post("/api/portfolio/positions", json=body)
    assert r1.status_code == 201
    assert r2.status_code == 201
    assert r1.json()["id"] == r2.json()["id"]


def test_crear_posicion_security_inexistente(auth_client):
    resp = auth_client.post("/api/portfolio/positions", json={"security_id": 9999})
    assert resp.status_code == 404


def test_anadir_transaccion(admin_client, seed_markets):
    sec_id = _crear_security(admin_client)
    pos = admin_client.post("/api/portfolio/positions", json={"security_id": sec_id}).json()
    pos_id = pos["id"]

    resp = admin_client.post(f"/api/portfolio/{pos_id}/transactions", json={
        "type": "buy",
        "date": "2024-01-10",
        "shares": "10",
        "price": "15.00",
        "fee": "5.00",
        "currency": "EUR",
        "exchange_rate": "1",
    })
    assert resp.status_code == 201
    tx = resp.json()
    assert tx["type"] == "buy"
    assert float(tx["shares"]) == 10.0


def test_transaccion_currency_incoherente(admin_client, seed_markets):
    """EUR con exchange_rate != 1 debe fallar con 422."""
    sec_id = _crear_security(admin_client)
    pos_id = admin_client.post("/api/portfolio/positions", json={"security_id": sec_id}).json()["id"]

    resp = admin_client.post(f"/api/portfolio/{pos_id}/transactions", json={
        "type": "buy", "date": "2024-01-10",
        "shares": "10", "price": "15.00", "fee": "0",
        "currency": "EUR",
        "exchange_rate": "1.10",   # EUR exige 1
    })
    assert resp.status_code == 422


def test_listar_y_borrar_transaccion(admin_client, seed_markets):
    sec_id = _crear_security(admin_client)
    pos_id = admin_client.post("/api/portfolio/positions", json={"security_id": sec_id}).json()["id"]
    tx_id = admin_client.post(f"/api/portfolio/{pos_id}/transactions", json={
        "type": "buy", "date": "2024-01-10",
        "shares": "5", "price": "20.00", "fee": "0",
        "currency": "EUR", "exchange_rate": "1",
    }).json()["id"]

    # Listar
    resp = admin_client.get(f"/api/portfolio/{pos_id}/transactions")
    assert resp.status_code == 200
    assert len(resp.json()) == 1

    # Borrar
    del_resp = admin_client.delete(f"/api/portfolio/{pos_id}/transactions/{tx_id}")
    assert del_resp.status_code == 204

    # Verificar que ya no está
    resp2 = admin_client.get(f"/api/portfolio/{pos_id}/transactions")
    assert resp2.json() == []


# ---------------------------------------------------------------------------
#  Favoritos
# ---------------------------------------------------------------------------

def test_favoritos_flujo_completo(admin_client, seed_markets):
    sec_id = _crear_security(admin_client, ticker="IBE.MC")

    # Añadir
    r = admin_client.post(f"/api/favorites/{sec_id}")
    assert r.status_code == 201

    # Listar
    favs = admin_client.get("/api/favorites").json()
    assert any(f["security_id"] == sec_id for f in favs)

    # Precio objetivo
    patch = admin_client.patch(f"/api/favorites/{sec_id}", json={"target_buy_price": "9.50"})
    assert patch.status_code == 200
    assert float(patch.json()["target_buy_price"]) == 9.50

    # Quitar
    del_resp = admin_client.delete(f"/api/favorites/{sec_id}")
    assert del_resp.status_code == 204
    favs2 = admin_client.get("/api/favorites").json()
    assert not any(f["security_id"] == sec_id for f in favs2)


# ---------------------------------------------------------------------------
#  Dividendos
# ---------------------------------------------------------------------------

def test_dividendos_flujo_completo(admin_client, seed_markets):
    sec_id = _crear_security(admin_client, ticker="REE.MC")
    pos_id = admin_client.post("/api/portfolio/positions", json={"security_id": sec_id}).json()["id"]

    # Añadir dividendo
    resp = admin_client.post(f"/api/portfolio/{pos_id}/dividends", json={
        "date": "2024-06-01",
        "shares_at_date": "100",
        "gross_per_share": "0.50",
        "gross_amount": "50.00",
        "withholding_tax": "9.50",
        "currency": "EUR",
        "exchange_rate": "1",
    })
    assert resp.status_code == 201
    div = resp.json()
    assert float(div["gross_amount"]) == 50.0
    assert float(div["withholding_tax"]) == 9.5
    div_id = div["id"]

    # Listar
    lista = admin_client.get(f"/api/portfolio/{pos_id}/dividends").json()
    assert len(lista) == 1
    assert lista[0]["id"] == div_id

    # Borrar
    del_resp = admin_client.delete(f"/api/portfolio/{pos_id}/dividends/{div_id}")
    assert del_resp.status_code == 204
    assert admin_client.get(f"/api/portfolio/{pos_id}/dividends").json() == []


def test_dividendo_currency_incoherente(admin_client, seed_markets):
    """USD con exchange_rate=1 debe fallar."""
    sec_id = _crear_security(admin_client)
    pos_id = admin_client.post("/api/portfolio/positions", json={"security_id": sec_id}).json()["id"]
    resp = admin_client.post(f"/api/portfolio/{pos_id}/dividends", json={
        "date": "2024-06-01",
        "shares_at_date": "10",
        "gross_per_share": "1.00",
        "gross_amount": "10.00",
        "currency": "USD",
        "exchange_rate": "1",   # USD requiere rate != 1
    })
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
#  Portfolio: posición cerrada y precio objetivo de venta
# ---------------------------------------------------------------------------

def _buy(auth_client, pos_id, shares, price, fee="0"):
    return auth_client.post(f"/api/portfolio/{pos_id}/transactions", json={
        "type": "buy", "date": "2024-01-10",
        "shares": str(shares), "price": str(price), "fee": fee,
        "currency": "EUR", "exchange_rate": "1",
    })

def _sell(auth_client, pos_id, shares, price, fee="0"):
    return auth_client.post(f"/api/portfolio/{pos_id}/transactions", json={
        "type": "sell", "date": "2024-06-01",
        "shares": str(shares), "price": str(price), "fee": fee,
        "currency": "EUR", "exchange_rate": "1",
    })


def test_venta_excede_acciones_da_422(admin_client, seed_markets):
    """Vender más acciones de las que hay en cartera debe retornar 422."""
    sec_id = _crear_security(admin_client, ticker="OVER.MC")
    pos_id = admin_client.post("/api/portfolio/positions", json={"security_id": sec_id}).json()["id"]
    _buy(admin_client, pos_id, 5, "10.00")   # 5 acciones en cartera

    resp = admin_client.post(f"/api/portfolio/{pos_id}/transactions", json={
        "type": "sell", "date": "2024-06-01",
        "shares": "10",           # más de las 5 disponibles
        "price": "12.00", "fee": "0",
        "currency": "EUR", "exchange_rate": "1",
    })
    assert resp.status_code == 422


def test_portfolio_closed_aparece_tras_venta_total(admin_client, seed_markets):
    # Compra 5 acc × 10.00 € y venta total: posición queda cerrada
    sec_id = _crear_security(admin_client, ticker="CLOSED.MC")
    pos_id = admin_client.post("/api/portfolio/positions", json={"security_id": sec_id}).json()["id"]
    _buy(admin_client, pos_id, 5, "10.00")
    _sell(admin_client, pos_id, 5, "12.00")

    # No aparece en posiciones abiertas
    abiertas = admin_client.get("/api/portfolio").json()
    assert not any(p["position_id"] == pos_id for p in abiertas)

    # Sí aparece en cerradas con beneficio = 10 €
    cerradas = admin_client.get("/api/portfolio/closed").json()
    c = next((p for p in cerradas if p["position_id"] == pos_id), None)
    assert c is not None
    # coste = 50 €, ingresos = 60 €, beneficio realizado = 10 €
    assert float(c["cost_eur"])        == 50.0
    assert float(c["proceeds_eur"])    == 60.0
    assert float(c["realized_pnl_eur"]) == 10.0


def test_portfolio_abierto_no_incluye_cerradas(admin_client, seed_markets):
    """Una posición con acciones en cartera no debe aparecer en /closed."""
    sec_id = _crear_security(admin_client, ticker="OPEN.MC")
    pos_id = admin_client.post("/api/portfolio/positions", json={"security_id": sec_id}).json()["id"]
    _buy(admin_client, pos_id, 10, "5.00")
    # No venta → posición abierta
    cerradas = admin_client.get("/api/portfolio/closed").json()
    assert not any(p["position_id"] == pos_id for p in cerradas)


def test_target_sell_patch(admin_client, seed_markets):
    # Compra para que la posición aparezca en /portfolio
    sec_id = _crear_security(admin_client, ticker="TGT.MC")
    pos_id = admin_client.post("/api/portfolio/positions", json={"security_id": sec_id}).json()["id"]
    _buy(admin_client, pos_id, 10, "5.00")

    # Establecer precio objetivo
    r = admin_client.patch(f"/api/portfolio/{pos_id}/target-sell",
                          json={"target_sell_price": "7.50"})
    assert r.status_code == 200
    assert float(r.json()["target_sell_price"]) == 7.5

    # Aparece en el summary de /portfolio
    posiciones = admin_client.get("/api/portfolio").json()
    p = next(x for x in posiciones if x["position_id"] == pos_id)
    assert float(p["target_sell_price"]) == 7.5

    # Borrarlo (None)
    r2 = admin_client.patch(f"/api/portfolio/{pos_id}/target-sell",
                           json={"target_sell_price": None})
    assert r2.status_code == 200
    assert r2.json()["target_sell_price"] is None


# ---------------------------------------------------------------------------
#  Portfolio: eliminar posición completa
# ---------------------------------------------------------------------------

def test_delete_position_sin_ventas(admin_client, seed_markets):
    """
    Una posición con solo compras (sin ventas) puede eliminarse.
    Tras el borrado: desaparece de /portfolio y no queda rastro en /closed.

    Aritmética: 3 compras × 10 acc → posición abierta sin ventas.
    DELETE /portfolio/positions/{id} → 204.
    """
    sec_id = _crear_security(admin_client, ticker="DEL.MC")
    pos_id = admin_client.post("/api/portfolio/positions", json={"security_id": sec_id}).json()["id"]
    _buy(admin_client, pos_id, 10, "5.00")
    _buy(admin_client, pos_id, 5, "6.00")

    # Verificar que aparece en posiciones abiertas
    abiertas = admin_client.get("/api/portfolio").json()
    assert any(p["position_id"] == pos_id for p in abiertas)

    # Borrar la posición completa
    r = admin_client.delete(f"/api/portfolio/positions/{pos_id}")
    assert r.status_code == 204

    # Ya no aparece en abiertas ni cerradas
    abiertas2 = admin_client.get("/api/portfolio").json()
    assert not any(p["position_id"] == pos_id for p in abiertas2)
    cerradas = admin_client.get("/api/portfolio/closed").json()
    assert not any(p["position_id"] == pos_id for p in cerradas)


def test_delete_position_con_ventas_rechazado(admin_client, seed_markets):
    """
    Una posición con al menos una venta NO puede eliminarse → 422.
    El historial fiscal debe preservarse; el usuario debe eliminar
    las ventas manualmente si realmente quiere limpiar la posición.

    Aritmética: compra 10 acc, venta 5 acc → posición abierta con ventas.
    DELETE → 422.
    """
    sec_id = _crear_security(admin_client, ticker="NOVEND.MC")
    pos_id = admin_client.post("/api/portfolio/positions", json={"security_id": sec_id}).json()["id"]
    _buy(admin_client, pos_id, 10, "10.00")
    _sell(admin_client, pos_id, 5, "12.00")

    r = admin_client.delete(f"/api/portfolio/positions/{pos_id}")
    assert r.status_code == 422
    assert "ventas" in r.json()["detail"].lower()


def test_delete_position_inexistente_devuelve_404(admin_client, seed_markets):
    """
    Intentar borrar un position_id que no existe (o no pertenece al usuario)
    devuelve 404. _require_position aplica la comprobación de ownership.
    """
    r = admin_client.delete("/api/portfolio/positions/99999")
    assert r.status_code == 404


# ---------------------------------------------------------------------------
#  Markets: overview y top-movers (sin snapshots reales)
# ---------------------------------------------------------------------------

def test_markets_overview_vacio(auth_client):
    """Sin valores en BD, overview devuelve lista vacía."""
    resp = auth_client.get("/api/markets/overview?market=ibex35")
    assert resp.status_code == 200
    assert resp.json() == []


def test_markets_overview_devuelve_valor(admin_client, seed_markets):
    sec_id = _crear_security(admin_client, ticker="SAN.MC")
    resp = admin_client.get("/api/markets/overview?market=ibex35")
    assert resp.status_code == 200
    items = resp.json()
    assert len(items) == 1
    item = items[0]
    assert item["id"] == sec_id
    assert item["yahoo_ticker"] == "SAN.MC"
    assert item["is_favorite"] is False
    # Sin snapshot: precios None
    assert item["last_price"] is None
    assert item["daily_change_pct"] is None


def test_markets_overview_favorito(admin_client, seed_markets):
    sec_id = _crear_security(admin_client, ticker="IBE.MC")
    admin_client.post(f"/api/favorites/{sec_id}")
    resp = admin_client.get("/api/markets/overview?market=ibex35")
    item = next(x for x in resp.json() if x["id"] == sec_id)
    assert item["is_favorite"] is True


def test_markets_overview_favorites_only(admin_client, seed_markets):
    san_id = _crear_security(admin_client, ticker="SAN.MC")
    ibe_id = _crear_security(admin_client, ticker="IBE.MC")
    admin_client.post(f"/api/favorites/{ibe_id}")

    resp = admin_client.get("/api/markets/overview?favorites_only=true")
    ids = [x["id"] for x in resp.json()]
    assert ibe_id in ids
    assert san_id not in ids


def test_markets_top_movers_sin_snapshots(admin_client, seed_markets):
    """Sin snapshots no hay valores con daily_change_pct → lista vacía."""
    _crear_security(admin_client, ticker="SAN.MC")
    resp = admin_client.get("/api/markets/top-movers?market=ibex35&direction=up")
    assert resp.status_code == 200
    assert resp.json() == []


def test_markets_top_movers_con_snapshot(admin_client, seed_markets, engine):
    """Con snapshots, top-movers ordena correctamente."""
    from sqlalchemy.orm import Session
    from app.models import PriceSnapshot

    san_id = _crear_security(admin_client, ticker="SAN.MC")
    ibe_id = _crear_security(admin_client, ticker="IBE.MC")

    # Insertar snapshots directamente en la BD de test
    with Session(engine) as s:
        s.add(PriceSnapshot(security_id=san_id, last_price=4.0, daily_change_pct=2.5))
        s.add(PriceSnapshot(security_id=ibe_id, last_price=10.0, daily_change_pct=-1.0))
        s.commit()

    # Mayores subidas: SAN primero (2.5 > -1.0)
    up = admin_client.get("/api/markets/top-movers?market=ibex35&direction=up&n=5").json()
    assert up[0]["yahoo_ticker"] == "SAN.MC"
    assert up[1]["yahoo_ticker"] == "IBE.MC"

    # Mayores bajadas: IBE primero (-1.0 < 2.5)
    down = admin_client.get("/api/markets/top-movers?market=ibex35&direction=down&n=5").json()
    assert down[0]["yahoo_ticker"] == "IBE.MC"
    assert down[1]["yahoo_ticker"] == "SAN.MC"


def test_markets_top_movers_n_limita_resultados(admin_client, seed_markets, engine):
    """El parámetro n limita la cantidad de resultados."""
    from sqlalchemy.orm import Session
    from app.models import PriceSnapshot

    ids = []
    for ticker in ["A.MC", "B.MC", "C.MC"]:
        r = admin_client.post("/api/securities", json={
            "name": ticker, "yahoo_ticker": ticker, "market": "ibex35", "currency": "EUR",
        })
        ids.append(r.json()["id"])

    with Session(engine) as s:
        for sec_id, pct in zip(ids, [3.0, 2.0, 1.0]):
            s.add(PriceSnapshot(security_id=sec_id, last_price=10.0, daily_change_pct=pct))
        s.commit()

    resp = admin_client.get("/api/markets/top-movers?market=ibex35&direction=up&n=2")
    assert resp.status_code == 200
    assert len(resp.json()) == 2


# ---------------------------------------------------------------------------
#  Backup export / import
# ---------------------------------------------------------------------------

def test_backup_export_vacio(auth_client):
    resp = auth_client.get("/api/backup/export")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("application/json")
    data = resp.json()
    assert data["version"] == "1"
    assert data["positions"] == []


def test_backup_export_con_datos(admin_client, seed_markets):
    sec_id = _crear_security(admin_client, ticker="SAN.MC")
    pos_id = admin_client.post("/api/portfolio/positions", json={"security_id": sec_id}).json()["id"]
    _buy(admin_client, pos_id, 10, "5.00")

    resp = admin_client.get("/api/backup/export")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["positions"]) == 1
    pos = data["positions"][0]
    assert pos["security_ticker"] == "SAN.MC"
    assert len(pos["transactions"]) == 1


def test_backup_import_idempotente(admin_client, seed_markets):
    """Importar el mismo backup dos veces no duplica transacciones."""
    sec_id = _crear_security(admin_client, ticker="SAN.MC")
    pos_id = admin_client.post("/api/portfolio/positions", json={"security_id": sec_id}).json()["id"]
    _buy(admin_client, pos_id, 10, "5.00")

    # Exportar
    backup = admin_client.get("/api/backup/export").json()

    # Importar dos veces
    r1 = admin_client.post("/api/backup/import", json=backup)
    assert r1.status_code == 200
    r2 = admin_client.post("/api/backup/import", json=backup)
    assert r2.status_code == 200

    # Solo hay 1 transacción (sin duplicados)
    txs = admin_client.get(f"/api/portfolio/{pos_id}/transactions").json()
    assert len(txs) == 1


def test_backup_import_security_inexistente(auth_client):
    """Si el ticker del backup no existe en el catálogo, se reporta como error."""
    backup = {
        "version": "1",
        "positions": [{
            "yahoo_ticker": "NOEXI.ST",
            "transactions": [{
                "type": "buy", "date": "2024-01-01",
                "shares": "1", "price": "10", "fee": "0",
                "currency": "EUR", "exchange_rate": "1",
            }],
            "dividends": [],
        }],
    }
    resp = auth_client.post("/api/backup/import", json=backup)
    assert resp.status_code == 200
    result = resp.json()
    assert result["errors"] != []


# ---------------------------------------------------------------------------
#  Tipo de cambio USD — integración
# ---------------------------------------------------------------------------

def test_portfolio_usd_aplica_tipo_cambio_bce(admin_client, seed_markets, engine):
    """
    Un valor en USD usa el tipo BCE más reciente para calcular market_value_eur.

    Snapshot: last_price = 110 USD
    Tipo BCE: 1.1 (1 EUR = 1.1 USD) → euros = dólares / rate
    Compra:   10 acc × 10 EUR (coste 100 EUR)
    market_value_eur = 10 acc × 110 USD / 1.1 = 1 000 EUR
    """
    from decimal import Decimal
    from sqlalchemy.orm import Session
    from app.models import EcbRate, PriceSnapshot

    r = admin_client.post("/api/securities", json={
        "name": "Apple Inc.", "yahoo_ticker": "AAPL",
        "market": "nasdaq", "currency": "USD",
    })
    sec_id = r.json()["id"]

    with Session(engine) as db:
        db.add(EcbRate(date="2026-01-15", rate=Decimal("1.1")))
        db.add(PriceSnapshot(
            security_id=sec_id,
            last_price=Decimal("110"),
            prev_close=None,
            daily_change_pct=None,
            min_1y=None, min_2y=None, min_5y=None, max_1y=None,
            last_dividend=None,
        ))
        db.commit()

    pos_id = admin_client.post("/api/portfolio/positions", json={"security_id": sec_id}).json()["id"]
    _buy(admin_client, pos_id, 10, "10.00")

    resp = admin_client.get("/api/portfolio")
    assert resp.status_code == 200
    pos = resp.json()[0]

    # 10 acc × 110 USD / 1.1 = 1000 EUR
    assert float(pos["market_value_eur"]) == pytest.approx(1000.0)


# ---------------------------------------------------------------------------
#  Admin — gestión de usuarios
# ---------------------------------------------------------------------------

def test_admin_me_incluye_is_admin(admin_client):
    """El endpoint /me devuelve is_admin=True para el admin."""
    resp = admin_client.get("/api/auth/me")
    assert resp.status_code == 200
    assert resp.json()["is_admin"] is True


def test_usuario_normal_is_admin_false(auth_client):
    """Un usuario normal tiene is_admin=False en /me."""
    resp = auth_client.get("/api/auth/me")
    assert resp.status_code == 200
    assert resp.json()["is_admin"] is False


def test_admin_lista_usuarios(admin_client, test_user):
    """El admin puede listar todos los usuarios."""
    resp = admin_client.get("/api/admin/users")
    assert resp.status_code == 200
    usernames = [u["username"] for u in resp.json()]
    assert "adminuser" in usernames
    assert "testuser" in usernames


def test_usuario_normal_no_puede_ver_admin(auth_client):
    """Un usuario normal recibe 403 al intentar acceder a /admin/users."""
    resp = auth_client.get("/api/admin/users")
    assert resp.status_code == 403


def test_admin_crea_usuario(admin_client):
    """El admin puede crear un nuevo usuario."""
    resp = admin_client.post("/api/admin/users", json={
        "username": "newuser",
        "password": "newpass123",
        "is_admin": False,
    })
    assert resp.status_code == 201
    data = resp.json()
    assert data["username"] == "newuser"
    assert data["is_admin"] is False


def test_admin_crea_usuario_duplicado_da_409(admin_client):
    """Crear un usuario con username ya existente devuelve 409."""
    body = {"username": "dup", "password": "duppass123", "is_admin": False}
    admin_client.post("/api/admin/users", json=body)
    resp = admin_client.post("/api/admin/users", json=body)
    assert resp.status_code == 409


def test_admin_cambia_password(admin_client, test_user, client):
    """El admin puede cambiar la contraseña de otro usuario."""
    resp = admin_client.patch(
        f"/api/admin/users/{test_user.id}/password",
        json={"password": "nuevapass456"},
    )
    assert resp.status_code == 200

    # Verifica que el nuevo password funciona
    login = client.post("/api/auth/login", json={
        "username": "testuser",
        "password": "nuevapass456",
    })
    assert login.status_code == 200


def test_admin_no_puede_borrarse_a_si_mismo(admin_client, test_admin):
    """El admin no puede eliminar su propia cuenta."""
    resp = admin_client.delete(f"/api/admin/users/{test_admin.id}")
    assert resp.status_code == 400


def test_admin_borra_usuario(admin_client, test_user):
    """El admin puede eliminar otro usuario."""
    resp = admin_client.delete(f"/api/admin/users/{test_user.id}")
    assert resp.status_code == 204


def test_admin_cambia_rol_a_admin(admin_client, test_user):
    """El admin puede promover a otro usuario a admin."""
    resp = admin_client.patch(
        f"/api/admin/users/{test_user.id}/role",
        json={"is_admin": True},
    )
    assert resp.status_code == 200
    assert resp.json()["is_admin"] is True


def test_admin_no_puede_cambiar_su_propio_rol(admin_client, test_admin):
    """El admin no puede cambiar su propio rol."""
    resp = admin_client.patch(
        f"/api/admin/users/{test_admin.id}/role",
        json={"is_admin": False},
    )
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
#  Integridad FIFO: borrado y edición de transacciones
# ---------------------------------------------------------------------------

def test_borrar_compra_con_venta_cubierta_da_422(admin_client, seed_markets):
    """
    Borrar una compra que es necesaria para cubrir una venta existente debe
    devolver 422 en lugar de dejar la posición en estado inconsistente.

    Compra 10 acc, venta 10 acc → la compra NO se puede borrar porque la
    venta se quedaría sin respaldo FIFO.
    """
    sec_id = _crear_security(admin_client, ticker="FIBQ.MC")
    pos_id = admin_client.post("/api/portfolio/positions", json={"security_id": sec_id}).json()["id"]

    buy_id = _buy(admin_client, pos_id, 10, "5.00").json()["id"]
    _sell(admin_client, pos_id, 10, "6.00")

    resp = admin_client.delete(f"/api/portfolio/{pos_id}/transactions/{buy_id}")
    assert resp.status_code == 422


def test_borrar_compra_sin_ventas_ok(admin_client, seed_markets):
    """Borrar una compra que no tiene ventas cubiertas sí está permitido."""
    sec_id = _crear_security(admin_client, ticker="FBNV.MC")
    pos_id = admin_client.post("/api/portfolio/positions", json={"security_id": sec_id}).json()["id"]

    buy_id = _buy(admin_client, pos_id, 10, "5.00").json()["id"]

    resp = admin_client.delete(f"/api/portfolio/{pos_id}/transactions/{buy_id}")
    assert resp.status_code == 204


def test_editar_compra_a_menos_acciones_invalida_venta_da_422(admin_client, seed_markets):
    """
    Editar una compra reduciendo las acciones por debajo de las vendidas
    debe devolver 422.

    Compra 10 acc, venta 8 acc → editar compra a 5 acc deja 8 ventas sin
    respaldo → 422.
    """
    sec_id = _crear_security(admin_client, ticker="FEDT.MC")
    pos_id = admin_client.post("/api/portfolio/positions", json={"security_id": sec_id}).json()["id"]

    buy_id = _buy(admin_client, pos_id, 10, "5.00").json()["id"]
    _sell(admin_client, pos_id, 8, "6.00")

    resp = admin_client.patch(f"/api/portfolio/{pos_id}/transactions/{buy_id}", json={
        "type": "buy", "date": "2024-01-10",
        "shares": "5",       # 5 < 8 vendidas → inválido
        "price": "5.00", "fee": "0",
        "currency": "EUR", "exchange_rate": "1",
    })
    assert resp.status_code == 422


def test_editar_compra_a_mas_acciones_ok(admin_client, seed_markets):
    """Aumentar acciones de una compra siempre es válido."""
    sec_id = _crear_security(admin_client, ticker="FEUP.MC")
    pos_id = admin_client.post("/api/portfolio/positions", json={"security_id": sec_id}).json()["id"]

    buy_id = _buy(admin_client, pos_id, 10, "5.00").json()["id"]
    _sell(admin_client, pos_id, 8, "6.00")

    resp = admin_client.patch(f"/api/portfolio/{pos_id}/transactions/{buy_id}", json={
        "type": "buy", "date": "2024-01-10",
        "shares": "20",      # más que antes → siempre válido
        "price": "5.00", "fee": "0",
        "currency": "EUR", "exchange_rate": "1",
    })
    assert resp.status_code == 200
    assert float(resp.json()["shares"]) == 20.0
