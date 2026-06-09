"""
test_security_requests.py
=========================
Tests de integración para el flujo de solicitudes de catálogo (v1.12.0).

Nota sobre fixtures: auth_client y admin_client comparten el mismo cliente HTTP
(conftest.py, StaticPool). Para tests que necesitan acciones de usuario Y admin
usamos re-login explícito en el mismo client.
"""

import pytest
from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy import select

from app.models import MarketRow, User
from app.auth.security import hash_password
from app.models.catalog_requests import SecurityRequestRow, UserNotificationRow


def _now_str():
    return datetime.now().isoformat(timespec="seconds")


# ---------------------------------------------------------------------------
#  Fixtures de BD directa (sin HTTP) para evitar problemas de sesión
# ---------------------------------------------------------------------------

@pytest.fixture()
def market_test(engine):
    """Inserta un mercado de prueba directo en BD (sin HTTP admin)."""
    with Session(engine) as db:
        db.merge(MarketRow(
            code="test_mkt", name="Test Market",
            currency="EUR", fiscal_window_days=60, market_type="stock",
            created_at=_now_str(),
        ))
        db.commit()
    return "test_mkt"


@pytest.fixture()
def market_pair(engine):
    """Inserta dos mercados de prueba."""
    with Session(engine) as db:
        for code, name in [("mkt_a", "Market A"), ("mkt_b", "Market B")]:
            db.merge(MarketRow(code=code, name=name, currency="EUR",
                               fiscal_window_days=60, market_type="stock",
                               created_at=_now_str()))
        db.commit()
    return "mkt_a", "mkt_b"


@pytest.fixture()
def user_and_admin(engine):
    """Crea usuario normal y admin en BD. Devuelve (user, admin)."""
    with Session(engine) as db:
        u = User(username="req_user", password_hash=hash_password("userpass"))
        a = User(username="req_admin", password_hash=hash_password("adminpass"), is_admin=True)
        db.add(u); db.add(a)
        db.commit()
        db.refresh(u); db.refresh(a)
        return u, a


# ---------------------------------------------------------------------------
#  Test: crear solicitud
# ---------------------------------------------------------------------------

class TestCreateRequest:
    def test_create_returns_201(self, client, market_test, user_and_admin):
        user, _ = user_and_admin
        client.post("/api/auth/login", json={"username": "req_user", "password": "userpass"})
        resp = client.post("/api/catalog/requests", json={
            "ticker": "TSTK", "name": "Test Stock", "market_id": "test_mkt", "isin": "ES1234567890",
        })
        assert resp.status_code == 201, resp.text
        data = resp.json()
        assert data["ticker"] == "TSTK"
        assert data["status"] == "pending"
        assert data["security_id"] is None

    def test_create_notification_pending(self, client, engine, market_test, user_and_admin):
        user, _ = user_and_admin
        client.post("/api/auth/login", json={"username": "req_user", "password": "userpass"})
        resp = client.post("/api/catalog/requests", json={
            "ticker": "NTFK", "name": "Notif Stock", "market_id": "test_mkt",
        })
        assert resp.status_code == 201
        req_id = resp.json()["id"]

        with Session(engine) as db:
            notif = db.scalars(
                select(UserNotificationRow).where(
                    UserNotificationRow.user_id == user.id,
                    UserNotificationRow.type == "request_pending",
                    UserNotificationRow.related_id == req_id,
                )
            ).first()
        assert notif is not None
        assert notif.related_type == "security_request"

    def test_create_requires_auth(self, client, market_test):
        # Sin login → 401/403
        resp = client.post("/api/catalog/requests", json={
            "ticker": "TST", "name": "Test", "market_id": "test_mkt",
        })
        assert resp.status_code in (401, 403)

    def test_create_invalid_market(self, client, user_and_admin):
        user, _ = user_and_admin
        client.post("/api/auth/login", json={"username": "req_user", "password": "userpass"})
        resp = client.post("/api/catalog/requests", json={
            "ticker": "TSTK", "name": "Test", "market_id": "nonexistent",
        })
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
#  Test: admin aprueba solicitud
# ---------------------------------------------------------------------------

class TestApproveRequest:
    def _create_request(self, client, market_id="test_mkt"):
        """Login como usuario y crea solicitud. Devuelve request_id."""
        client.post("/api/auth/login", json={"username": "req_user", "password": "userpass"})
        resp = client.post("/api/catalog/requests", json={
            "ticker": "APVK", "name": "Approve Stock", "market_id": market_id,
        })
        assert resp.status_code == 201
        return resp.json()["id"]

    def test_approve_creates_security(self, client, engine, market_test, user_and_admin):
        _, admin = user_and_admin
        req_id = self._create_request(client)

        # Re-login como admin
        client.post("/api/auth/login", json={"username": "req_admin", "password": "adminpass"})
        resp = client.patch(f"/api/admin/catalog/requests/{req_id}/approve", json={"market_id": "test_mkt"})
        assert resp.status_code == 200, resp.text
        assert resp.json()["status"] == "approved"
        assert resp.json()["security_id"] is not None

    def test_approve_swaps_notifications(self, client, engine, market_test, user_and_admin):
        user, _ = user_and_admin
        req_id = self._create_request(client)

        client.post("/api/auth/login", json={"username": "req_admin", "password": "adminpass"})
        client.patch(f"/api/admin/catalog/requests/{req_id}/approve", json={"market_id": "test_mkt"})

        with Session(engine) as db:
            notifs = db.scalars(
                select(UserNotificationRow).where(
                    UserNotificationRow.user_id == user.id,
                    UserNotificationRow.related_id == req_id,
                )
            ).all()
        types = [n.type for n in notifs]
        assert "request_approved" in types
        assert "request_pending" not in types

    def test_approve_can_change_market(self, client, engine, market_pair, user_and_admin):
        user, _ = user_and_admin
        mkt_a, mkt_b = market_pair
        client.post("/api/auth/login", json={"username": "req_user", "password": "userpass"})
        req_id = client.post("/api/catalog/requests", json={
            "ticker": "MKTCHG", "name": "Mkt Change", "market_id": mkt_a,
        }).json()["id"]

        client.post("/api/auth/login", json={"username": "req_admin", "password": "adminpass"})
        resp = client.patch(f"/api/admin/catalog/requests/{req_id}/approve", json={"market_id": mkt_b})
        assert resp.status_code == 200
        assert resp.json()["market_id"] == mkt_b

    def test_approve_requires_admin(self, client, market_test, user_and_admin):
        user, _ = user_and_admin
        req_id = self._create_request(client)
        # El client está como req_user (no admin)
        client.post("/api/auth/login", json={"username": "req_user", "password": "userpass"})
        resp = client.patch(f"/api/admin/catalog/requests/{req_id}/approve", json={"market_id": "test_mkt"})
        assert resp.status_code == 403

    def test_double_approve_conflicts(self, client, market_test, user_and_admin):
        req_id = self._create_request(client)
        client.post("/api/auth/login", json={"username": "req_admin", "password": "adminpass"})
        client.patch(f"/api/admin/catalog/requests/{req_id}/approve", json={"market_id": "test_mkt"})
        resp = client.patch(f"/api/admin/catalog/requests/{req_id}/approve", json={"market_id": "test_mkt"})
        assert resp.status_code == 409


# ---------------------------------------------------------------------------
#  Test: admin rechaza solicitud
# ---------------------------------------------------------------------------

class TestRejectRequest:
    def _create_request(self, client, market_id="test_mkt"):
        client.post("/api/auth/login", json={"username": "req_user", "password": "userpass"})
        resp = client.post("/api/catalog/requests", json={
            "ticker": "RJCK", "name": "Reject Stock", "market_id": market_id,
        })
        assert resp.status_code == 201
        return resp.json()["id"]

    def test_reject_changes_status(self, client, market_test, user_and_admin):
        req_id = self._create_request(client)
        client.post("/api/auth/login", json={"username": "req_admin", "password": "adminpass"})
        resp = client.patch(f"/api/admin/catalog/requests/{req_id}/reject", json={"notes": "No cumple"})
        assert resp.status_code == 200
        assert resp.json()["status"] == "rejected"
        assert resp.json()["notes"] == "No cumple"

    def test_reject_swaps_notifications(self, client, engine, market_test, user_and_admin):
        user, _ = user_and_admin
        req_id = self._create_request(client)
        client.post("/api/auth/login", json={"username": "req_admin", "password": "adminpass"})
        client.patch(f"/api/admin/catalog/requests/{req_id}/reject", json={})

        with Session(engine) as db:
            notifs = db.scalars(
                select(UserNotificationRow).where(
                    UserNotificationRow.user_id == user.id,
                    UserNotificationRow.related_id == req_id,
                )
            ).all()
        types = [n.type for n in notifs]
        assert "request_rejected" in types
        assert "request_pending" not in types


# ---------------------------------------------------------------------------
#  Test: listado y count
# ---------------------------------------------------------------------------

class TestListRequests:
    def test_list_pending(self, client, market_test, user_and_admin):
        client.post("/api/auth/login", json={"username": "req_user", "password": "userpass"})
        client.post("/api/catalog/requests", json={"ticker": "LST", "name": "List", "market_id": "test_mkt"})
        client.post("/api/auth/login", json={"username": "req_admin", "password": "adminpass"})
        resp = client.get("/api/admin/catalog/requests?req_status=pending")
        assert resp.status_code == 200
        assert len(resp.json()) >= 1

    def test_pending_count(self, client, market_test, user_and_admin):
        client.post("/api/auth/login", json={"username": "req_user", "password": "userpass"})
        client.post("/api/catalog/requests", json={"ticker": "CNT", "name": "Count", "market_id": "test_mkt"})
        client.post("/api/auth/login", json={"username": "req_admin", "password": "adminpass"})
        resp = client.get("/api/admin/catalog/requests/pending-count")
        assert resp.status_code == 200
        assert resp.json()["count"] >= 1

    def test_pending_count_decreases_after_approval(self, client, market_test, user_and_admin):
        client.post("/api/auth/login", json={"username": "req_user", "password": "userpass"})
        req_id = client.post("/api/catalog/requests", json={
            "ticker": "DEC", "name": "Decrease", "market_id": "test_mkt",
        }).json()["id"]
        client.post("/api/auth/login", json={"username": "req_admin", "password": "adminpass"})
        before = client.get("/api/admin/catalog/requests/pending-count").json()["count"]
        client.patch(f"/api/admin/catalog/requests/{req_id}/approve", json={"market_id": "test_mkt"})
        after = client.get("/api/admin/catalog/requests/pending-count").json()["count"]
        assert after == before - 1


# ---------------------------------------------------------------------------
#  Test: mensajes libres
# ---------------------------------------------------------------------------

class TestCatalogMessages:
    def test_user_sends_message(self, client, user_and_admin):
        client.post("/api/auth/login", json={"username": "req_user", "password": "userpass"})
        resp = client.post("/api/catalog/messages", json={"message": "Querría añadir el fondo XYZ"})
        assert resp.status_code == 201
        assert resp.json()["message"] == "Querría añadir el fondo XYZ"

    def test_admin_sees_message(self, client, user_and_admin):
        client.post("/api/auth/login", json={"username": "req_user", "password": "userpass"})
        client.post("/api/catalog/messages", json={"message": "Ver mensaje admin"})
        client.post("/api/auth/login", json={"username": "req_admin", "password": "adminpass"})
        resp = client.get("/api/admin/catalog/messages")
        assert resp.status_code == 200
        bodies = [m["message"] for m in resp.json()]
        assert "Ver mensaje admin" in bodies

    def test_admin_resolves_message(self, client, user_and_admin):
        client.post("/api/auth/login", json={"username": "req_user", "password": "userpass"})
        msg_id = client.post("/api/catalog/messages", json={"message": "Resolver esto"}).json()["id"]
        client.post("/api/auth/login", json={"username": "req_admin", "password": "adminpass"})
        resp = client.patch(f"/api/admin/catalog/messages/{msg_id}/resolve")
        assert resp.status_code == 204

    def test_user_cannot_list_admin_messages(self, client, user_and_admin):
        client.post("/api/auth/login", json={"username": "req_user", "password": "userpass"})
        resp = client.get("/api/admin/catalog/messages")
        assert resp.status_code == 403
