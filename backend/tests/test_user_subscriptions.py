"""
test_user_subscriptions.py
===========================
Tests del control de suscripciones de usuarios (v1.3.0):
  - Habilitar / deshabilitar usuarios con anotación.
  - Usuario deshabilitado no puede hacer login (403).
  - Usuario caducado se deshabilita automáticamente al hacer login (403).
  - Historial de estados se registra correctamente.
  - Fecha de caducidad (PATCH /admin/users/{id}/expiry).
  - Nombre de la aplicación (GET /config, PATCH /admin/config/app-name).
"""

import pytest
from datetime import date, timedelta


# ---------------------------------------------------------------------------
#  Helper: crear usuario vía API y devolver su id
# ---------------------------------------------------------------------------

def _create_user(admin_client, username, password="pass1234567"):
    resp = admin_client.post("/api/admin/users", json={
        "username": username,
        "password": password,
    })
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


# ---------------------------------------------------------------------------
#  Habilitar / deshabilitar
# ---------------------------------------------------------------------------

def test_deshabilitar_usuario(admin_client):
    uid = _create_user(admin_client, "user_dis")
    resp = admin_client.patch(f"/api/admin/users/{uid}/status", json={
        "enabled": False,
        "annotation": "Cuenta suspendida por impago",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["is_enabled"] is False


def test_habilitar_usuario(admin_client):
    uid = _create_user(admin_client, "user_en")
    # Primero deshabilitar
    admin_client.patch(f"/api/admin/users/{uid}/status", json={"enabled": False})
    # Luego habilitar
    resp = admin_client.patch(f"/api/admin/users/{uid}/status", json={
        "enabled": True,
        "annotation": "Cuenta reactivada",
    })
    assert resp.status_code == 200
    assert resp.json()["is_enabled"] is True


def test_admin_no_puede_deshabilitarse_a_si_mismo(admin_client):
    # Obtener el propio id
    me = admin_client.get("/api/auth/me").json()
    resp = admin_client.patch(f"/api/admin/users/{me['id']}/status", json={"enabled": False})
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
#  Login de usuario deshabilitado
# ---------------------------------------------------------------------------

def test_usuario_deshabilitado_no_puede_hacer_login(admin_client, client):
    uid = _create_user(admin_client, "user_blocked", "blocked_pass123")
    admin_client.patch(f"/api/admin/users/{uid}/status", json={"enabled": False})

    resp = client.post("/api/auth/login", json={
        "username": "user_blocked",
        "password": "blocked_pass123",
    })
    assert resp.status_code == 403
    assert resp.json()["detail"] == "Contactar con el administrador"


# ---------------------------------------------------------------------------
#  Caducidad
# ---------------------------------------------------------------------------

def test_poner_fecha_caducidad(admin_client):
    uid = _create_user(admin_client, "user_exp")
    future = (date.today() + timedelta(days=30)).isoformat()
    resp = admin_client.patch(f"/api/admin/users/{uid}/expiry", json={"expires_at": future})
    assert resp.status_code == 200
    assert resp.json()["expires_at"] is not None


def test_borrar_fecha_caducidad(admin_client):
    uid = _create_user(admin_client, "user_noexp")
    future = (date.today() + timedelta(days=30)).isoformat()
    admin_client.patch(f"/api/admin/users/{uid}/expiry", json={"expires_at": future})
    resp = admin_client.patch(f"/api/admin/users/{uid}/expiry", json={"expires_at": None})
    assert resp.status_code == 200
    assert resp.json()["expires_at"] is None


def test_usuario_caducado_no_puede_hacer_login(admin_client, client):
    """Un usuario con expires_at en el pasado se deshabilita y no puede entrar."""
    uid = _create_user(admin_client, "user_expired", "expired_pass123")
    # Fecha en el pasado
    past = (date.today() - timedelta(days=1)).isoformat()
    admin_client.patch(f"/api/admin/users/{uid}/expiry", json={"expires_at": past})

    resp = client.post("/api/auth/login", json={
        "username": "user_expired",
        "password": "expired_pass123",
    })
    assert resp.status_code == 403
    assert resp.json()["detail"] == "account_expired"

    # Comprobar que ahora está deshabilitado en la BD
    users = admin_client.get("/api/admin/users").json()
    u = next(x for x in users if x["id"] == uid)
    assert u["is_enabled"] is False


# ---------------------------------------------------------------------------
#  Historial de estados
# ---------------------------------------------------------------------------

def test_historial_tiene_evento_registered_al_crear(admin_client):
    uid = _create_user(admin_client, "user_hist")
    resp = admin_client.get(f"/api/admin/users/{uid}/history")
    assert resp.status_code == 200
    history = resp.json()
    statuses = [e["status"] for e in history]
    assert "registered" in statuses


def test_historial_registra_disable_enable(admin_client):
    uid = _create_user(admin_client, "user_hist2")
    admin_client.patch(f"/api/admin/users/{uid}/status", json={
        "enabled": False,
        "annotation": "suspendido",
    })
    admin_client.patch(f"/api/admin/users/{uid}/status", json={
        "enabled": True,
        "annotation": "reactivado",
    })
    resp = admin_client.get(f"/api/admin/users/{uid}/history")
    assert resp.status_code == 200
    history = resp.json()
    statuses = [e["status"] for e in history]
    assert "disabled" in statuses
    assert "enabled" in statuses
    # Verificar que la anotación queda guardada
    disabled_entry = next(e for e in history if e["status"] == "disabled")
    assert disabled_entry["annotation"] == "suspendido"


def test_historial_registra_actor(admin_client):
    uid = _create_user(admin_client, "user_hist3")
    admin_client.patch(f"/api/admin/users/{uid}/status", json={"enabled": False})
    resp = admin_client.get(f"/api/admin/users/{uid}/history")
    history = resp.json()
    disabled_entry = next(e for e in history if e["status"] == "disabled")
    # El actor debe ser el admin que hizo la acción
    assert disabled_entry["actor_username"] == "adminuser"


def test_historial_usuario_inexistente_da_404(admin_client):
    resp = admin_client.get("/api/admin/users/99999/history")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
#  Nombre de la aplicación
# ---------------------------------------------------------------------------

def test_get_public_config_devuelve_nombre_por_defecto(client):
    resp = client.get("/api/config")
    assert resp.status_code == 200
    assert "app_name" in resp.json()


def test_admin_cambia_nombre_app(admin_client, client):
    resp = admin_client.patch("/api/admin/config/app-name", json={"app_name": "Mi Cartera"})
    assert resp.status_code == 200
    assert resp.json()["app_name"] == "Mi Cartera"

    # El endpoint público refleja el cambio
    public = client.get("/api/config").json()
    assert public["app_name"] == "Mi Cartera"


def test_admin_nombre_app_vacio_da_422(admin_client):
    resp = admin_client.patch("/api/admin/config/app-name", json={"app_name": "   "})
    assert resp.status_code == 422


def test_admin_config_incluye_app_name(admin_client):
    resp = admin_client.get("/api/admin/config")
    assert resp.status_code == 200
    assert "app_name" in resp.json()
