"""
test_email.py
=============
Tests de integración para v1.14.0: notificaciones por email para administradores.

Cubre:
  1. Campo email en usuarios (crear con email, listar, editar, borrar).
  2. Configuración de email (guardar, recuperar con máscara, actualizar preservando "***").
  3. Endpoint de test de email (422 sin email de admin, mock de send_email).
  4. Triggers de email en eventos (nueva solicitud, nuevo mensaje, respuesta de usuario).
  5. Permisos (403 para no-admin en endpoints de configuración).
"""

from __future__ import annotations

import json
import pytest
from datetime import datetime
from sqlalchemy.orm import Session
from unittest.mock import patch

from app.models import User, MarketRow
from app.models.config import AppConfig
from app.auth.security import hash_password
from app.services.email_notifications import EMAIL_CONFIG_KEY


# ---------------------------------------------------------------------------
#  Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def ea_pair(engine):
    """Crea un usuario normal y un admin con email. Devuelve (user, admin)."""
    with Session(engine) as db:
        u = User(username="email_user", password_hash=hash_password("upass123"))
        a = User(
            username="email_admin",
            password_hash=hash_password("apass123"),
            is_admin=True,
            email="admin@example.com",
        )
        db.add(u)
        db.add(a)
        db.commit()
        db.refresh(u)
        db.refresh(a)
        return u, a


@pytest.fixture()
def email_config_payload():
    return {
        "provider": "smtp_gmail",
        "from_name": "JSG Portfolio",
        "from_address": "noreply@example.com",
        "smtp_user": "testuser@gmail.com",
        "smtp_password": "myapppassword",
        "smtp_use_tls": True,
    }


def _login(client, username, password):
    client.post("/api/auth/login", json={"username": username, "password": password})


def _save_email_config(engine, payload: dict) -> None:
    """Guarda directamente la config de email en la BD (para tests que la necesitan pre-cargada)."""
    from app.services.email_service import EmailConfig
    config = EmailConfig(
        provider=payload["provider"],
        from_name=payload["from_name"],
        from_address=payload["from_address"],
        smtp_user=payload.get("smtp_user"),
        smtp_password=payload.get("smtp_password"),
        smtp_use_tls=payload.get("smtp_use_tls", True),
    )
    with Session(engine) as db:
        row = db.get(AppConfig, EMAIL_CONFIG_KEY)
        if row is None:
            db.add(AppConfig(key=EMAIL_CONFIG_KEY, value=json.dumps(config.__dict__)))
        else:
            row.value = json.dumps(config.__dict__)
        db.commit()


# ===========================================================================
#  Bloque 1 — Campo email en usuarios
# ===========================================================================

class TestUserEmailField:
    """El campo email se puede crear, leer, editar y borrar."""

    def test_create_user_with_email(self, client, ea_pair):
        _, admin = ea_pair
        _login(client, "email_admin", "apass123")

        resp = client.post("/api/admin/users", json={
            "username": "newuser_withemail",
            "password": "password123",
            "is_admin": True,
            "email": "newadmin@example.com",
        })
        assert resp.status_code == 201, resp.text
        data = resp.json()
        assert data["email"] == "newadmin@example.com"

    def test_create_user_without_email(self, client, ea_pair):
        _login(client, "email_admin", "apass123")
        resp = client.post("/api/admin/users", json={
            "username": "user_noemail",
            "password": "password123",
        })
        assert resp.status_code == 201
        assert resp.json()["email"] is None

    def test_list_users_includes_email(self, client, ea_pair):
        _login(client, "email_admin", "apass123")
        resp = client.get("/api/admin/users")
        assert resp.status_code == 200
        admins = [u for u in resp.json() if u["username"] == "email_admin"]
        assert len(admins) == 1
        assert admins[0]["email"] == "admin@example.com"

    def test_patch_user_email(self, client, ea_pair):
        user, admin = ea_pair
        _login(client, "email_admin", "apass123")

        resp = client.patch(f"/api/admin/users/{user.id}/email", json={"email": "user@example.com"})
        assert resp.status_code == 200
        assert resp.json()["email"] == "user@example.com"

    def test_patch_user_email_to_null(self, client, ea_pair):
        _, admin = ea_pair
        _login(client, "email_admin", "apass123")

        # Primero poner un email
        client.patch(f"/api/admin/users/{admin.id}/email", json={"email": "tmp@example.com"})
        # Luego borrarlo
        resp = client.patch(f"/api/admin/users/{admin.id}/email", json={"email": None})
        assert resp.status_code == 200
        assert resp.json()["email"] is None

    def test_patch_email_requires_admin(self, client, ea_pair):
        user, _ = ea_pair
        _login(client, "email_user", "upass123")
        resp = client.patch(f"/api/admin/users/{user.id}/email", json={"email": "x@x.com"})
        assert resp.status_code == 403


# ===========================================================================
#  Bloque 2 — Configuración de email
# ===========================================================================

class TestEmailConfig:
    """Guardar, recuperar (enmascarada), y actualizar la configuración de email."""

    def test_get_config_not_found(self, client, ea_pair):
        _login(client, "email_admin", "apass123")
        resp = client.get("/api/admin/config/email")
        assert resp.status_code == 404

    def test_save_and_retrieve_config(self, client, ea_pair, email_config_payload):
        _login(client, "email_admin", "apass123")

        resp = client.patch("/api/admin/config/email", json=email_config_payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["provider"] == "smtp_gmail"
        assert data["from_name"] == "JSG Portfolio"
        # La contraseña debe aparecer enmascarada
        assert data["smtp_password"] == "***"

    def test_get_config_masked(self, client, ea_pair, email_config_payload):
        _login(client, "email_admin", "apass123")
        client.patch("/api/admin/config/email", json=email_config_payload)

        resp = client.get("/api/admin/config/email")
        assert resp.status_code == 200
        data = resp.json()
        assert data["smtp_password"] == "***"
        assert data["smtp_user"] == "testuser@gmail.com"

    def test_update_preserves_password_when_stars(self, client, ea_pair, email_config_payload, engine):
        _login(client, "email_admin", "apass123")
        client.patch("/api/admin/config/email", json=email_config_payload)

        # Actualizar sin cambiar la contraseña (se envía "***")
        updated = {**email_config_payload, "from_name": "Nuevo nombre", "smtp_password": "***"}
        resp = client.patch("/api/admin/config/email", json=updated)
        assert resp.status_code == 200

        # La contraseña real en BD debe seguir siendo la original
        with Session(engine) as db:
            row = db.get(AppConfig, EMAIL_CONFIG_KEY)
            stored = json.loads(row.value)
            assert stored["smtp_password"] == "myapppassword"
            assert stored["from_name"] == "Nuevo nombre"

    def test_config_returns_email_configured_in_global_config(self, client, ea_pair, email_config_payload):
        _login(client, "email_admin", "apass123")
        resp = client.get("/api/admin/config")
        assert resp.json()["email_configured"] is False

        client.patch("/api/admin/config/email", json=email_config_payload)
        resp = client.get("/api/admin/config")
        assert resp.json()["email_configured"] is True
        assert resp.json()["email_provider"] == "smtp_gmail"

    def test_invalid_provider_rejected(self, client, ea_pair):
        _login(client, "email_admin", "apass123")
        resp = client.patch("/api/admin/config/email", json={
            "provider": "yahoo_mail",
            "from_name": "Test",
            "from_address": "t@t.com",
        })
        assert resp.status_code == 422

    def test_config_requires_admin(self, client, ea_pair, email_config_payload):
        _login(client, "email_user", "upass123")
        resp = client.patch("/api/admin/config/email", json=email_config_payload)
        assert resp.status_code == 403
        resp = client.get("/api/admin/config/email")
        assert resp.status_code == 403


# ===========================================================================
#  Bloque 3 — Test de email
# ===========================================================================

class TestEmailTest:
    """El endpoint de prueba envía email al admin logueado o devuelve 422."""

    def test_test_email_no_admin_email(self, client, engine):
        """422 si el admin no tiene email configurado."""
        with Session(engine) as db:
            a = User(username="noemail_admin", password_hash=hash_password("pass1234"), is_admin=True)
            db.add(a)
            db.commit()
        _login(client, "noemail_admin", "pass1234")
        resp = client.post("/api/admin/config/email/test")
        assert resp.status_code == 422
        assert "email" in resp.json()["detail"].lower()

    def test_test_email_no_config(self, client, ea_pair):
        """422 si no hay config de email guardada."""
        _login(client, "email_admin", "apass123")
        resp = client.post("/api/admin/config/email/test")
        assert resp.status_code == 422

    def test_test_email_calls_send_email(self, client, ea_pair, email_config_payload):
        """Con email de admin y config guardada, llama a send_email."""
        _login(client, "email_admin", "apass123")
        client.patch("/api/admin/config/email", json=email_config_payload)

        with patch("app.api.admin_markets.send_email") as mock_send:
            mock_send.return_value = None
            resp = client.post("/api/admin/config/email/test")

        assert resp.status_code == 200
        assert resp.json()["sent_to"] == "admin@example.com"
        mock_send.assert_called_once()
        # El destinatario es el email del admin logueado
        args = mock_send.call_args
        assert args[0][1] == "admin@example.com"  # to

    def test_test_email_send_error_returns_422(self, client, ea_pair, email_config_payload):
        """Si send_email lanza excepción, el endpoint devuelve 422 con detalle."""
        _login(client, "email_admin", "apass123")
        client.patch("/api/admin/config/email", json=email_config_payload)

        with patch("app.api.admin_markets.send_email", side_effect=RuntimeError("SMTP error")):
            resp = client.post("/api/admin/config/email/test")

        assert resp.status_code == 422
        assert "SMTP error" in resp.json()["detail"]

    def test_test_email_requires_admin(self, client, ea_pair):
        _login(client, "email_user", "upass123")
        resp = client.post("/api/admin/config/email/test")
        assert resp.status_code == 403


# ===========================================================================
#  Bloque 4 — Triggers de email en eventos
# ===========================================================================

class TestEmailTriggers:
    """notify_admins se llama cuando ocurren eventos relevantes."""

    @pytest.fixture()
    def market_id(self, engine, seed_markets):
        return "ibex35"

    def test_trigger_on_catalog_request(self, client, ea_pair, market_id):
        _login(client, "email_user", "upass123")

        with patch("app.api.catalog_requests.notify_admins") as mock_notify:
            resp = client.post("/api/catalog/requests", json={
                "ticker": "SAN.MC",
                "isin": None,
                "name": "Santander",
                "market_id": market_id,
                "currency": "EUR",
            })

        assert resp.status_code == 201
        mock_notify.assert_called_once()
        call_kwargs = mock_notify.call_args
        assert "SAN.MC" in call_kwargs[1]["subject"] or "SAN.MC" in call_kwargs[0][1]

    def test_trigger_on_catalog_message(self, client, ea_pair):
        _login(client, "email_user", "upass123")

        with patch("app.api.catalog_requests.notify_admins") as mock_notify:
            resp = client.post("/api/catalog/messages", json={
                "subject": "Pregunta",
                "message": "¿Pueden agregar este fondo?",
            })

        assert resp.status_code == 201
        mock_notify.assert_called_once()

    def test_trigger_on_notification_reply(self, client, ea_pair, engine):
        """Cuando el usuario responde a una notificación, se notifica a admins."""
        user, admin = ea_pair

        # Insertar una notificación para el usuario directamente en BD
        from app.models.catalog_requests import UserNotificationRow
        from datetime import datetime, timezone
        with Session(engine) as db:
            notif = UserNotificationRow(
                user_id=user.id,
                type="admin_message",
                title="Mensaje del admin",
                body="Hola, comprueba tus datos",
                is_read=False,
                created_at=datetime.now(timezone.utc).replace(tzinfo=None),
            )
            db.add(notif)
            db.commit()
            db.refresh(notif)
            notif_id = notif.id

        _login(client, "email_user", "upass123")
        with patch("app.api.notifications.notify_admins") as mock_notify:
            resp = client.post(f"/api/notifications/{notif_id}/reply", json={
                "message": "Gracias, ya lo he comprobado",
            })

        assert resp.status_code == 204
        mock_notify.assert_called_once()

    def test_email_trigger_failure_does_not_break_request(self, client, ea_pair, market_id):
        """Un fallo en el envío de email no debe romper el flujo principal."""
        _login(client, "email_user", "upass123")

        with patch(
            "app.api.catalog_requests.notify_admins",
            side_effect=RuntimeError("Email server down"),
        ):
            resp = client.post("/api/catalog/requests", json={
                "ticker": "IBE.MC",
                "isin": None,
                "name": "Iberdrola",
                "market_id": market_id,
                "currency": "EUR",
            })

        # La solicitud debe haberse creado correctamente a pesar del error de email
        assert resp.status_code == 201
