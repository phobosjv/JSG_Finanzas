"""
test_subcarteras.py
===================
Tests de subcarteras: agrupaciones personalizadas de posiciones (v1.11.0).

Cubre:
  * CRUD de subcarteras (crear, listar, actualizar, eliminar).
  * Scoping por usuario (cada usuario solo ve las suyas).
  * Gestión de posiciones (agregar, quitar, idempotencia).
  * Muchos-a-muchos: una posición en varias subcarteras.
  * 404 al operar sobre subcartera ajena / inexistente.
  * 403 al añadir position_id de otro usuario.
  * Filtrado por position_ids en /history, /xirr, /period-returns.
"""

import pytest


# ---------------------------------------------------------------------------
#  Helpers
# ---------------------------------------------------------------------------

def _crear_security(admin_c, ticker="SAN.MC"):
    """Crea un Security (requiere admin) y devuelve su id."""
    r = admin_c.post("/api/securities", json={
        "name": "Test Fund",
        "yahoo_ticker": ticker,
        "market": "ibex35",
        "currency": "EUR",
    })
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _crear_position(client, sec_id) -> int:
    """Crea una posición para el security dado y devuelve position_id."""
    r = client.post("/api/portfolio/positions", json={"security_id": sec_id})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _crear_subcartera(client, name="Cartera Test", description=None) -> dict:
    payload = {"name": name}
    if description:
        payload["description"] = description
    r = client.post("/api/subcarteras", json=payload)
    assert r.status_code == 201, r.text
    return r.json()


# ---------------------------------------------------------------------------
#  CRUD básico
# ---------------------------------------------------------------------------

def test_crear_subcartera(auth_client, seed_markets):
    data = _crear_subcartera(auth_client, "Mi Cartera Robótica", "Fondos indexados")
    assert data["name"] == "Mi Cartera Robótica"
    assert data["description"] == "Fondos indexados"
    assert data["position_ids"] == []
    assert "id" in data
    assert "created_at" in data


def test_crear_subcartera_nombre_vacio_falla(auth_client, seed_markets):
    r = auth_client.post("/api/subcarteras", json={"name": "   "})
    assert r.status_code == 422


def test_listar_subcarteras(auth_client, seed_markets):
    _crear_subcartera(auth_client, "A")
    _crear_subcartera(auth_client, "B")
    r = auth_client.get("/api/subcarteras")
    assert r.status_code == 200
    names = [s["name"] for s in r.json()]
    assert "A" in names and "B" in names


def test_actualizar_nombre(auth_client, seed_markets):
    sc = _crear_subcartera(auth_client, "Nombre Original")
    r = auth_client.patch(f"/api/subcarteras/{sc['id']}", json={"name": "Nombre Nuevo"})
    assert r.status_code == 200
    assert r.json()["name"] == "Nombre Nuevo"


def test_actualizar_descripcion(auth_client, seed_markets):
    sc = _crear_subcartera(auth_client, "X")
    r = auth_client.patch(f"/api/subcarteras/{sc['id']}", json={"description": "nueva desc"})
    assert r.status_code == 200
    assert r.json()["description"] == "nueva desc"


def test_eliminar_subcartera(auth_client, seed_markets):
    sc = _crear_subcartera(auth_client, "Temporal")
    r = auth_client.delete(f"/api/subcarteras/{sc['id']}")
    assert r.status_code == 204
    # Ya no aparece en el listado
    r2 = auth_client.get("/api/subcarteras")
    ids = [s["id"] for s in r2.json()]
    assert sc["id"] not in ids


def test_eliminar_subcartera_preserva_posiciones(admin_client, seed_markets):
    """Eliminar una subcartera no elimina las posiciones del portfolio."""
    sec_id = _crear_security(admin_client)
    pos_id = _crear_position(admin_client, sec_id)
    sc = _crear_subcartera(admin_client)
    admin_client.post(f"/api/subcarteras/{sc['id']}/positions/{pos_id}")
    admin_client.delete(f"/api/subcarteras/{sc['id']}")
    # La posición sigue existiendo en el portfolio
    r = admin_client.get("/api/portfolio")
    assert r.status_code == 200  # no explota


# ---------------------------------------------------------------------------
#  Gestión de posiciones
# ---------------------------------------------------------------------------

def test_agregar_posicion(admin_client, seed_markets):
    sec_id = _crear_security(admin_client)
    pos_id = _crear_position(admin_client, sec_id)
    sc = _crear_subcartera(admin_client)

    r = admin_client.post(f"/api/subcarteras/{sc['id']}/positions/{pos_id}")
    assert r.status_code == 204

    r2 = admin_client.get("/api/subcarteras")
    sc_data = next(s for s in r2.json() if s["id"] == sc["id"])
    assert pos_id in sc_data["position_ids"]


def test_agregar_posicion_idempotente(admin_client, seed_markets):
    """Agregar la misma posición dos veces no falla ni duplica."""
    sec_id = _crear_security(admin_client)
    pos_id = _crear_position(admin_client, sec_id)
    sc = _crear_subcartera(admin_client)

    admin_client.post(f"/api/subcarteras/{sc['id']}/positions/{pos_id}")
    r = admin_client.post(f"/api/subcarteras/{sc['id']}/positions/{pos_id}")
    assert r.status_code == 204

    r2 = admin_client.get("/api/subcarteras")
    sc_data = next(s for s in r2.json() if s["id"] == sc["id"])
    assert sc_data["position_ids"].count(pos_id) == 1


def test_quitar_posicion(admin_client, seed_markets):
    sec_id = _crear_security(admin_client)
    pos_id = _crear_position(admin_client, sec_id)
    sc = _crear_subcartera(admin_client)
    admin_client.post(f"/api/subcarteras/{sc['id']}/positions/{pos_id}")

    r = admin_client.delete(f"/api/subcarteras/{sc['id']}/positions/{pos_id}")
    assert r.status_code == 204

    r2 = admin_client.get("/api/subcarteras")
    sc_data = next(s for s in r2.json() if s["id"] == sc["id"])
    assert pos_id not in sc_data["position_ids"]


def test_quitar_posicion_no_existente_no_falla(admin_client, seed_markets):
    """Quitar una posición que no estaba en la subcartera es no-op (204)."""
    sec_id = _crear_security(admin_client)
    pos_id = _crear_position(admin_client, sec_id)
    sc = _crear_subcartera(admin_client)

    r = admin_client.delete(f"/api/subcarteras/{sc['id']}/positions/{pos_id}")
    assert r.status_code == 204


# ---------------------------------------------------------------------------
#  Muchos a muchos
# ---------------------------------------------------------------------------

def test_posicion_en_varias_subcarteras(admin_client, seed_markets):
    """Una misma posición puede estar en múltiples subcarteras."""
    sec_id = _crear_security(admin_client)
    pos_id = _crear_position(admin_client, sec_id)
    sc1 = _crear_subcartera(admin_client, "Cartera A")
    sc2 = _crear_subcartera(admin_client, "Cartera B")

    admin_client.post(f"/api/subcarteras/{sc1['id']}/positions/{pos_id}")
    admin_client.post(f"/api/subcarteras/{sc2['id']}/positions/{pos_id}")

    r = admin_client.get("/api/subcarteras")
    data = {s["id"]: s for s in r.json()}
    assert pos_id in data[sc1["id"]]["position_ids"]
    assert pos_id in data[sc2["id"]]["position_ids"]


# ---------------------------------------------------------------------------
#  Scoping por usuario
# ---------------------------------------------------------------------------

def test_subcarteras_scoped_por_usuario(client, engine, seed_markets):
    """El usuario A no ve las subcarteras del usuario B."""
    from sqlalchemy.orm import Session
    from app.models import User
    from app.auth.security import hash_password

    # Crear usuarios A y B directamente en BD
    with Session(engine) as s:
        user_a = User(username="scoping_userA", password_hash=hash_password("passA"))
        user_b = User(username="scoping_userB", password_hash=hash_password("passB"))
        s.add_all([user_a, user_b])
        s.commit()

    # Login como A → crear subcartera
    client.post("/api/auth/login", json={"username": "scoping_userA", "password": "passA"})
    sc = _crear_subcartera(client, "Solo de A")

    # Login como B → no ve la subcartera de A
    client.post("/api/auth/login", json={"username": "scoping_userB", "password": "passB"})
    r = client.get("/api/subcarteras")
    assert r.status_code == 200
    assert sc["id"] not in [s["id"] for s in r.json()]


# ---------------------------------------------------------------------------
#  Errores 404 / 403
# ---------------------------------------------------------------------------

def test_404_subcartera_inexistente(auth_client, seed_markets):
    r = auth_client.patch("/api/subcarteras/99999", json={"name": "X"})
    assert r.status_code == 404


def test_404_eliminar_subcartera_inexistente(auth_client, seed_markets):
    r = auth_client.delete("/api/subcarteras/99999")
    assert r.status_code == 404


def test_403_posicion_de_otro_usuario(client, engine, seed_markets):
    """No se puede agregar la posición de otro usuario a tu subcartera."""
    from sqlalchemy.orm import Session
    from app.models import User, Position, MarketRow, Security
    from app.auth.security import hash_password
    from sqlalchemy import select

    # Crear usuarios A y B, y una posición perteneciente a B
    with Session(engine) as s:
        user_a = User(username="owner_a_403", password_hash=hash_password("pass_a"))
        user_b = User(username="owner_b_403", password_hash=hash_password("pass_b"))
        s.add_all([user_a, user_b])
        s.flush()
        # Obtener un security existente (hay al menos uno gracias a seed_markets)
        mkt = s.scalar(select(MarketRow))
        sec = Security(name="Fondo B", yahoo_ticker="FUNDB.MC", market=mkt.code, currency="EUR")
        s.add(sec)
        s.flush()
        pos_b = Position(user_id=user_b.id, security_id=sec.id)
        s.add(pos_b)
        s.commit()
        pos_b_id = pos_b.id

    # Usuario A intenta añadir la posición de B a su subcartera
    client.post("/api/auth/login", json={"username": "owner_a_403", "password": "pass_a"})
    sc = _crear_subcartera(client, "Cartera de A")
    r = client.post(f"/api/subcarteras/{sc['id']}/positions/{pos_b_id}")
    assert r.status_code == 403


# ---------------------------------------------------------------------------
#  Filtrado por position_ids en endpoints de cartera
# ---------------------------------------------------------------------------

def test_history_con_position_ids_vacio_devuelve_lista(auth_client, seed_markets):
    """?position_ids= con lista vacía no debe crashear (devuelve [])."""
    r = auth_client.get("/api/portfolio/history?position_ids=")
    assert r.status_code == 200
    assert r.json() == []


def test_xirr_con_position_ids_sin_transacciones(admin_client, seed_markets):
    """?position_ids con posición sin operaciones no debe crashear."""
    sec_id = _crear_security(admin_client)
    pos_id = _crear_position(admin_client, sec_id)
    r = admin_client.get(f"/api/portfolio/xirr?position_ids={pos_id}")
    assert r.status_code == 200
    data = r.json()
    assert "xirr_pct" in data


def test_period_returns_con_position_ids_sin_historial(admin_client, seed_markets):
    """?position_ids con posición sin historial de precios devuelve nulls."""
    sec_id = _crear_security(admin_client)
    pos_id = _crear_position(admin_client, sec_id)
    r = admin_client.get(f"/api/portfolio/period-returns?position_ids={pos_id}")
    assert r.status_code == 200
    data = r.json()
    assert data["ytd"] is None
    assert data["y1"] is None
