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
    """Con snapshots, top-movers filtra estrictamente por signo (v1.6.0).

    direction=up  → solo daily_change_pct > 0 (excluye negativos y cero).
    direction=down → solo daily_change_pct < 0 (excluye positivos y cero).
    """
    from sqlalchemy.orm import Session
    from app.models import PriceSnapshot

    san_id = _crear_security(admin_client, ticker="SAN.MC")
    ibe_id = _crear_security(admin_client, ticker="IBE.MC")
    rep_id = _crear_security(admin_client, ticker="REP.MC")

    # SAN y REP suben; IBE baja
    with Session(engine) as s:
        s.add(PriceSnapshot(security_id=san_id, last_price=4.0,  daily_change_pct=2.5))
        s.add(PriceSnapshot(security_id=ibe_id, last_price=10.0, daily_change_pct=-1.0))
        s.add(PriceSnapshot(security_id=rep_id, last_price=15.0, daily_change_pct=0.8))
        s.commit()

    # Mayores subidas: solo pct > 0, ordenados de mayor a menor
    up = admin_client.get("/api/markets/top-movers?market=ibex35&direction=up&n=5").json()
    tickers_up = [x["yahoo_ticker"] for x in up]
    assert "SAN.MC" in tickers_up      # +2.5 %
    assert "REP.MC" in tickers_up      # +0.8 %
    assert "IBE.MC" not in tickers_up  # -1.0 % → excluido
    assert up[0]["yahoo_ticker"] == "SAN.MC"  # mayor subida primero

    # Mayores bajadas: solo pct < 0
    down = admin_client.get("/api/markets/top-movers?market=ibex35&direction=down&n=5").json()
    tickers_down = [x["yahoo_ticker"] for x in down]
    assert "IBE.MC" in tickers_down      # -1.0 %
    assert "SAN.MC" not in tickers_down  # +2.5 % → excluido
    assert "REP.MC" not in tickers_down  # +0.8 % → excluido


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


# ---------------------------------------------------------------------------
#  Tests de regresión — bugs corregidos en búsqueda profunda (v1.5.1)
# ---------------------------------------------------------------------------

# ── Bug 1: delete_position usaba HTTP_422_UNPROCESSABLE_ENTITY (deprecado) ──
# Verificado por test_delete_position_con_ventas_rechazado (ya existente):
# la corrección elimina el DeprecationWarning al ejecutar pytest.


# ── Bug 2: catalog export/import perdía sort_order ──────────────────────────

def test_catalog_export_incluye_sort_order(admin_client, seed_markets, engine):
    """
    GET /admin/catalog/export debe serializar el campo sort_order de cada
    mercado. Antes de la corrección el campo no se incluía, y un ciclo
    export→import lo perdía (todos los mercados quedaban con sort_order=0).
    """
    from sqlalchemy.orm import Session
    from app.models import MarketRow

    # Asignar sort_order distintos a los mercados de prueba
    with Session(engine) as db:
        db.get(MarketRow, "ibex35").sort_order   = 3
        db.get(MarketRow, "continuo").sort_order = 1
        db.get(MarketRow, "nasdaq").sort_order   = 2
        db.commit()

    resp = admin_client.get("/api/admin/catalog/export")
    assert resp.status_code == 200
    catalog = resp.json()

    by_code = {m["code"]: m for m in catalog["markets"]}
    assert "sort_order" in by_code["ibex35"], "sort_order ausente en exportación"
    # Los valores exactos deben sobrevivir la serialización
    assert by_code["ibex35"]["sort_order"]   == 3
    assert by_code["continuo"]["sort_order"] == 1
    assert by_code["nasdaq"]["sort_order"]   == 2


def test_catalog_import_restaura_sort_order(admin_client, engine):
    """
    POST /admin/catalog/import debe crear los mercados con el sort_order
    que viene en el JSON. Antes de la corrección, el schema CatalogMarketIn
    no tenía el campo y el endpoint ignoraba cualquier valor, creando siempre
    mercados con sort_order=0.

    Aritmética: se importan 2 mercados con sort_order 5 y 2. Después de la
    importación ambos deben tener exactamente esos valores.
    """
    from sqlalchemy.orm import Session
    from app.models import MarketRow

    catalog = {
        "markets": [
            {"code": "tst_a", "name": "Test A", "currency": "EUR",
             "fiscal_window_days": 60, "sort_order": 5},
            {"code": "tst_b", "name": "Test B", "currency": "USD",
             "fiscal_window_days": 365, "sort_order": 2},
        ],
        "securities": [],
    }
    resp = admin_client.post("/api/admin/catalog/import", json=catalog)
    assert resp.status_code == 200
    assert resp.json()["markets_imported"] == 2

    with Session(engine) as db:
        m_a = db.get(MarketRow, "tst_a")
        m_b = db.get(MarketRow, "tst_b")
        assert m_a is not None
        assert m_b is not None
        # Bug: antes del fix ambos habrían tenido sort_order=0
        assert m_a.sort_order == 5, f"Esperado 5, obtenido {m_a.sort_order}"
        assert m_b.sort_order == 2, f"Esperado 2, obtenido {m_b.sort_order}"


# ── Bug 3: texto del plazo de recompra hardcodeado a market=="nasdaq" ────────

def test_tax_report_plazo_texto_deriva_de_fiscal_window_days():
    """
    El aviso de regla de recompra en el informe fiscal debe mostrar el plazo
    correcto derivado de fiscal_window_days, no del código de mercado.

    Bug: antes de la corrección, solo el mercado code="nasdaq" mostraba
    "un año". Cualquier otro mercado con fiscal_window_days=365 (p.ej. "nyse")
    decía incorrectamente "dos meses" aunque la ventana aplicada era de 1 año.

    Aritmética:
    - Mercado "nyse" con fiscal_window_days=365.
    - Compra 10 acc a 100 € el 2024-01-01.
    - Venta 10 acc a 80 € el 2024-06-01 → pérdida = -200 €.
    - Recompra 10 acc el 2024-08-01 (dentro de la ventana de 1 año).
    - Resultado esperado: aviso dice "un año", no "dos meses".
    """
    from datetime import date
    from decimal import Decimal
    from app.services.calculations import Transaction, SaleMatch
    from app.services.tax_report import SecurityRef, SecuritySales, build_tax_report

    buy_date  = date(2024, 1, 1)
    sell_date = date(2024, 6, 1)
    rebuy_date = date(2024, 8, 1)   # 61 días después de la venta → fuera de 2m, dentro de 1a

    # Mercado con código ≠ "nasdaq" pero fiscal_window_days=365
    sec = SecurityRef(security_id=1, name="Apple", isin=None,
                      market="nyse", fiscal_window_days=365)

    buy_tx = Transaction(
        type="buy", date=buy_date,
        shares=Decimal("10"), price=Decimal("100"),
        fee=Decimal("0"), exchange_rate=Decimal("1"),
    )
    rebuy_tx = Transaction(
        type="buy", date=rebuy_date,
        shares=Decimal("10"), price=Decimal("85"),
        fee=Decimal("0"), exchange_rate=Decimal("1"),
    )
    match = SaleMatch(
        sell_date=sell_date, buy_date=buy_date,
        shares=Decimal("10"),
        cost_native=Decimal("1000"), cost_eur=Decimal("1000"),
        proceeds_native=Decimal("800"), proceeds_eur=Decimal("800"),
        gain_native=Decimal("-200"), gain_eur=Decimal("-200"),
    )

    sec_sales = SecuritySales(security=sec, matches=[match], all_buys=[buy_tx, rebuy_tx])
    report = build_tax_report(2024, [sec_sales], [])

    assert len(report.sale_lines) == 1
    line = report.sale_lines[0]
    assert line.loss_disallowed is True
    assert line.disallowed_reason is not None
    # El texto debe mencionar "un año", nunca "dos meses"
    assert "un año" in line.disallowed_reason, (
        f"Esperado 'un año' en el aviso, obtenido: {line.disallowed_reason!r}"
    )
    assert "dos meses" not in line.disallowed_reason


def test_tax_report_plazo_texto_crypto_muestra_dias():
    """
    Mercado crypto con fiscal_window_days=1: el aviso debe mencionar "1 día",
    no "dos meses".

    Aritmética: compra el día D-0, venta el día D con pérdida, recompra el D+1
    (dentro del plazo de 1 día). Aviso debe decir "1 día".
    """
    from datetime import date
    from decimal import Decimal
    from app.services.calculations import Transaction, SaleMatch
    from app.services.tax_report import SecurityRef, SecuritySales, build_tax_report

    buy_date   = date(2024, 6, 1)
    sell_date  = date(2024, 6, 2)
    rebuy_date = date(2024, 6, 3)   # 1 día después de la venta

    sec = SecurityRef(security_id=2, name="Bitcoin", isin=None,
                      market="crypto", fiscal_window_days=1)

    buy_tx = Transaction(
        type="buy", date=buy_date,
        shares=Decimal("1"), price=Decimal("60000"),
        fee=Decimal("0"), exchange_rate=Decimal("1"),
    )
    rebuy_tx = Transaction(
        type="buy", date=rebuy_date,
        shares=Decimal("1"), price=Decimal("55000"),
        fee=Decimal("0"), exchange_rate=Decimal("1"),
    )
    match = SaleMatch(
        sell_date=sell_date, buy_date=buy_date,
        shares=Decimal("1"),
        cost_native=Decimal("60000"), cost_eur=Decimal("60000"),
        proceeds_native=Decimal("58000"), proceeds_eur=Decimal("58000"),
        gain_native=Decimal("-2000"), gain_eur=Decimal("-2000"),
    )

    sec_sales = SecuritySales(security=sec, matches=[match], all_buys=[buy_tx, rebuy_tx])
    report = build_tax_report(2024, [sec_sales], [])

    line = report.sale_lines[0]
    assert line.loss_disallowed is True
    assert "1 día" in line.disallowed_reason, (
        f"Esperado '1 día' en el aviso, obtenido: {line.disallowed_reason!r}"
    )


# ── Bug 4: _is_loss_disallowed no detectaba compra parcialmente consumida ────

def test_perdida_disallowed_cuando_compra_parcialmente_consumida_en_ventana():
    """
    Bug: si el FIFO solo consume PARTE de una compra (p.ej. compra 10 acc,
    vende 5), el código anterior excluía TODA la transacción de compra de la
    comprobación de recompra. Las 5 acciones restantes del mismo lote —que sí
    están dentro del plazo— no se detectaban, y la pérdida se marcaba como
    computable cuando no debería serlo.

    Aritmética:
    - Mercado ibex35, fiscal_window_days=60.
    - Compra: 10 acc × 100 € el 2024-05-02 (30 días antes de la venta → dentro de ±60 días).
    - Venta: 5 acc × 80 € el 2024-06-01 → pérdida = 5×(80-100) = -100 €.
    - FIFO empareja 5 de las 10 acciones. Quedan 5 en cartera, compradas
      dentro de la ventana [2024-04-02, 2024-08-01].
    - Resultado esperado: loss_disallowed=True (las 5 restantes son recompra).
    """
    from datetime import date
    from decimal import Decimal
    from app.services.calculations import Transaction, SaleMatch
    from app.services.tax_report import SecurityRef, SecuritySales, build_tax_report

    sell_date = date(2024, 6, 1)
    buy_date  = date(2024, 5, 2)   # 30 días antes → dentro del plazo ±60 días

    sec = SecurityRef(security_id=1, name="Iberdrola", isin=None,
                      market="ibex35", fiscal_window_days=60)

    # Una sola compra de 10 acciones
    buy_tx = Transaction(
        type="buy", date=buy_date,
        shares=Decimal("10"), price=Decimal("100"),
        fee=Decimal("0"), exchange_rate=Decimal("1"),
    )

    # El FIFO solo consume 5 de las 10
    match = SaleMatch(
        sell_date=sell_date, buy_date=buy_date,
        shares=Decimal("5"),           # ← solo 5 consumidas
        cost_native=Decimal("500"),    # 5 × 100
        cost_eur=Decimal("500"),
        proceeds_native=Decimal("400"), # 5 × 80
        proceeds_eur=Decimal("400"),
        gain_native=Decimal("-100"),
        gain_eur=Decimal("-100"),
    )

    sec_sales = SecuritySales(security=sec, matches=[match], all_buys=[buy_tx])
    report = build_tax_report(2024, [sec_sales], [])

    assert len(report.sale_lines) == 1
    line = report.sale_lines[0]
    assert line.loss_disallowed is True, (
        "La pérdida debe marcarse: quedan 5 acc del mismo lote "
        "comprado dentro del plazo de 2 meses."
    )


def test_perdida_computable_cuando_compra_totalmente_consumida_sin_otras_en_ventana():
    """
    Caso control: si el FIFO consume EXACTAMENTE todas las acciones del lote
    y no hay otras compras en la ventana, la pérdida SÍ es computable.

    Aritmética:
    - Compra 5 acc × 100 € el 2024-05-02 (30 días antes).
    - Venta 5 acc × 80 € el 2024-06-01 → pérdida = -100 €.
    - FIFO consume las 5 completas: no quedan acciones del lote.
    - Sin otras compras en la ventana.
    - Resultado: loss_disallowed=False (pérdida computable).
    """
    from datetime import date
    from decimal import Decimal
    from app.services.calculations import Transaction, SaleMatch
    from app.services.tax_report import SecurityRef, SecuritySales, build_tax_report

    sell_date = date(2024, 6, 1)
    buy_date  = date(2024, 5, 2)   # 30 días antes → dentro del plazo, pero lote agotado

    sec = SecurityRef(security_id=1, name="Iberdrola", isin=None,
                      market="ibex35", fiscal_window_days=60)

    buy_tx = Transaction(
        type="buy", date=buy_date,
        shares=Decimal("5"), price=Decimal("100"),
        fee=Decimal("0"), exchange_rate=Decimal("1"),
    )

    match = SaleMatch(
        sell_date=sell_date, buy_date=buy_date,
        shares=Decimal("5"),           # ← exactamente lo mismo que la compra
        cost_native=Decimal("500"),
        cost_eur=Decimal("500"),
        proceeds_native=Decimal("400"),
        proceeds_eur=Decimal("400"),
        gain_native=Decimal("-100"),
        gain_eur=Decimal("-100"),
    )

    sec_sales = SecuritySales(security=sec, matches=[match], all_buys=[buy_tx])
    report = build_tax_report(2024, [sec_sales], [])

    line = report.sale_lines[0]
    assert line.loss_disallowed is False, (
        "Con compra totalmente consumida y sin otras en la ventana, "
        "la pérdida debe ser computable."
    )


# ===========================================================================
#  DELETE /portfolio/reset — borrar toda la cartera del usuario
# ===========================================================================

def test_reset_portfolio_borra_posiciones_y_transacciones(admin_client, seed_markets):
    """
    DELETE /portfolio/reset elimina todas las posiciones del usuario y en
    cascada sus transacciones y dividendos. La cartera queda vacía.
    """
    sec = _crear_security(admin_client)
    pos = admin_client.post("/api/portfolio/positions", json={"security_id": sec}).json()["id"]
    _buy(admin_client, pos, 10, 100)
    _sell(admin_client, pos, 5, 120)

    assert len(admin_client.get("/api/portfolio").json()) >= 1

    resp = admin_client.delete("/api/portfolio/reset")
    assert resp.status_code == 204
    assert admin_client.get("/api/portfolio").json() == []


def test_reset_portfolio_no_afecta_a_otros_usuarios(admin_client, seed_markets, engine):
    """
    DELETE /portfolio/reset solo borra las posiciones del usuario activo.
    Crea un segundo usuario directamente en la BD para verificar aislamiento.
    """
    from sqlalchemy.orm import Session as _Session
    from sqlalchemy import select as _select, func as _func
    from app.models.portfolio import Position as _Position, TransactionRow as _TxRow
    from app.models.user import User as _User
    from app.auth.security import hash_password as _hp

    # El admin crea su posición vía API
    sec = _crear_security(admin_client)
    pos_admin = admin_client.post("/api/portfolio/positions", json={"security_id": sec}).json()["id"]
    _buy(admin_client, pos_admin, 5, 100)

    # Segundo usuario creado directamente en BD (no vía API para evitar
    # conflicto de cookie con admin_client)
    with _Session(engine) as s:
        other = _User(username="other_u", password_hash=_hp("pass"))
        s.add(other)
        s.flush()
        other_pos = _Position(user_id=other.id, security_id=sec)
        s.add(other_pos)
        s.flush()
        s.add(_TxRow(
            position_id=other_pos.id, type="buy", date="2024-01-10",
            shares=3, price=50, fee=0, currency="EUR", exchange_rate=1,
        ))
        s.commit()
        other_pos_id = other_pos.id

    # Reset del admin
    assert admin_client.delete("/api/portfolio/reset").status_code == 204
    assert admin_client.get("/api/portfolio").json() == []

    # La posición del otro usuario sigue intacta en la BD
    with _Session(engine) as s:
        still_exists = s.scalar(
            _select(_func.count()).select_from(_Position).where(_Position.id == other_pos_id)
        )
    assert still_exists == 1, "El reset no debe borrar posiciones de otros usuarios."


def test_reset_portfolio_conserva_favoritos(admin_client, seed_markets):
    """
    DELETE /portfolio/reset no borra los favoritos del usuario.
    """
    sec = _crear_security(admin_client)
    pos = admin_client.post("/api/portfolio/positions", json={"security_id": sec}).json()["id"]
    _buy(admin_client, pos, 10, 100)
    admin_client.post(f"/api/favorites/{sec}")

    admin_client.delete("/api/portfolio/reset")

    favs = admin_client.get("/api/favorites").json()
    assert any(f.get("id") == sec or f.get("security_id") == sec for f in favs), (
        "El reset no debe borrar los favoritos del usuario."
    )


def test_reset_portfolio_cartera_ya_vacia(admin_client, seed_markets):
    """DELETE /portfolio/reset sobre cartera vacía devuelve 204 sin errores."""
    assert admin_client.delete("/api/portfolio/reset").status_code == 204
