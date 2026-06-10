"""
test_user_notifications.py
===========================
Tests para el sistema de notificaciones in-app (v1.12.0).
"""

import pytest
from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy import select

from app.models import MarketRow, User
from app.auth.security import hash_password
from app.models.catalog_requests import CatalogMessageRow, UserNotificationRow


def _now_str():
    return datetime.now().isoformat(timespec="seconds")


# ---------------------------------------------------------------------------
#  Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def market_ntf(engine):
    with Session(engine) as db:
        db.merge(MarketRow(code="ntf_mkt", name="Notif Market",
                           currency="EUR", fiscal_window_days=60, market_type="stock",
                           created_at=_now_str()))
        db.commit()
    return "ntf_mkt"


@pytest.fixture()
def two_users(engine):
    """Crea usuario normal y usuario2 (para probar aislamiento)."""
    with Session(engine) as db:
        u1 = User(username="notif_user", password_hash=hash_password("pass1"))
        u2 = User(username="notif_user2", password_hash=hash_password("pass2"))
        db.add(u1); db.add(u2)
        db.commit()
        db.refresh(u1); db.refresh(u2)
        return u1, u2


@pytest.fixture()
def notif_user_id(engine, two_users):
    return two_users[0].id


def _login(client, username, password):
    client.post("/api/auth/login", json={"username": username, "password": password})


def _create_notif_via_request(client, market_id="ntf_mkt"):
    """Crea una solicitud (que genera notificación request_pending). Devuelve req_id."""
    resp = client.post("/api/catalog/requests", json={
        "ticker": "NTFK", "name": "Notif Stock", "market_id": market_id,
    })
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


# ---------------------------------------------------------------------------
#  Test: GET /notifications
# ---------------------------------------------------------------------------

class TestListNotifications:
    def test_list_returns_own_notifs(self, client, market_ntf, two_users):
        _login(client, "notif_user", "pass1")
        _create_notif_via_request(client)
        resp = client.get("/api/notifications")
        assert resp.status_code == 200
        types = [n["type"] for n in resp.json()]
        assert "request_pending" in types

    def test_list_requires_auth(self, client):
        resp = client.get("/api/notifications")
        assert resp.status_code in (401, 403)


# ---------------------------------------------------------------------------
#  Test: PATCH /{id}/read
# ---------------------------------------------------------------------------

class TestMarkRead:
    def test_mark_read(self, client, market_ntf, two_users):
        _login(client, "notif_user", "pass1")
        _create_notif_via_request(client)
        notif_id = client.get("/api/notifications").json()[0]["id"]
        resp = client.patch(f"/api/notifications/{notif_id}/read")
        assert resp.status_code == 200
        assert resp.json()["is_read"] is True


# ---------------------------------------------------------------------------
#  Test: DELETE /{id}
# ---------------------------------------------------------------------------

class TestDeleteNotification:
    def test_delete_removes_notif(self, client, market_ntf, two_users):
        _login(client, "notif_user", "pass1")
        _create_notif_via_request(client)
        notif_id = client.get("/api/notifications").json()[0]["id"]
        resp = client.delete(f"/api/notifications/{notif_id}")
        assert resp.status_code == 204
        remaining = client.get("/api/notifications").json()
        assert all(n["id"] != notif_id for n in remaining)

    def test_delete_other_user_notif_returns_404(self, client, engine, market_ntf, two_users):
        """Usuario1 crea notificación; usuario2 intenta borrarla → 404."""
        user1, user2 = two_users
        # Crear notificación para user1
        _login(client, "notif_user", "pass1")
        _create_notif_via_request(client)
        notif_id = client.get("/api/notifications").json()[0]["id"]

        # Login como user2 e intentar borrar la notificación de user1
        _login(client, "notif_user2", "pass2")
        resp = client.delete(f"/api/notifications/{notif_id}")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
#  Test: POST /{id}/reply
# ---------------------------------------------------------------------------

class TestReplyNotification:
    def test_reply_creates_catalog_message(self, client, engine, market_ntf, two_users):
        user1, _ = two_users
        _login(client, "notif_user", "pass1")
        req_id = _create_notif_via_request(client)
        notif_id = client.get("/api/notifications").json()[0]["id"]

        resp = client.post(f"/api/notifications/{notif_id}/reply", json={
            "message": "Gracias por la revisión.",
        })
        assert resp.status_code == 204

        # La notificación debe haber sido borrada
        remaining = client.get("/api/notifications").json()
        assert all(n["id"] != notif_id for n in remaining)

        # Debe existir un CatalogMessageRow vinculado a la solicitud
        with Session(engine) as db:
            msg = db.scalars(
                select(CatalogMessageRow).where(
                    CatalogMessageRow.user_id == user1.id,
                    CatalogMessageRow.security_request_id == req_id,
                )
            ).first()
        assert msg is not None
        # El mensaje incluye el texto del usuario + bloque de contexto de la notificación.
        assert "Gracias por la revisión." in msg.message
        assert msg.subject  # subject debe rellenarse con el título de la notificación

    def test_reply_empty_message_rejected(self, client, market_ntf, two_users):
        _login(client, "notif_user", "pass1")
        _create_notif_via_request(client)
        notif_id = client.get("/api/notifications").json()[0]["id"]
        resp = client.post(f"/api/notifications/{notif_id}/reply", json={"message": "   "})
        assert resp.status_code == 422
