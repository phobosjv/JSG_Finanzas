"""
test_user_expiry.py
===================
Tests de integración para v1.15.0: notificaciones por caducidad de cuenta.

Cubre:
  1. Login con cuenta caducada → detail='account_expired' + notificación a admins.
  2. Login con cuenta deshabilitada manualmente → detail genérico (sin cambio).
  3. Endpoint POST /auth/request-renewal → notificación in-app + email a admins.
  4. Job check_expired_users → detecta, desactiva, notifica.
  5. Casos límite: admin caducado, usuario ya deshabilitado, futuro.
"""

from __future__ import annotations

import json
import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from sqlalchemy.orm import Session
from sqlalchemy import select

from app.models import User, UserStatusLog, UserNotificationRow
from app.auth.security import hash_password
from app.models.catalog_requests import CatalogMessageRow
from app.models.config import AppConfig
from app.services.email_notifications import EMAIL_CONFIG_KEY


# ---------------------------------------------------------------------------
#  Helpers
# ---------------------------------------------------------------------------

def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _make_user(
    engine,
    username: str,
    password: str = "pass123456",
    is_admin: bool = False,
    email: str | None = None,
    expires_at: datetime | None = None,
    is_enabled: bool = True,
) -> User:
    with Session(engine) as db:
        u = User(
            username=username,
            password_hash=hash_password(password),
            is_admin=is_admin,
            email=email,
            expires_at=expires_at,
            is_enabled=is_enabled,
        )
        db.add(u)
        db.commit()
        db.refresh(u)
        return u


def _login(client, username: str, password: str = "pass123456"):
    return client.post("/api/auth/login", json={"username": username, "password": password})


def _admin_notifs(engine, admin_id: int) -> list:
    with Session(engine) as db:
        return db.scalars(
            select(UserNotificationRow).where(UserNotificationRow.user_id == admin_id)
        ).all()


# ===========================================================================
#  Bloque 1 — Login con cuenta caducada
# ===========================================================================

class TestLoginExpiredAccount:
    """El login detecta caducidad, desactiva la cuenta y notifica a los admins."""

    def test_login_expired_returns_account_expired(self, client, engine):
        # 403 con detail distinguible para que el frontend muestre el botón de renovación
        _make_user(engine, "exp1", expires_at=_now() - timedelta(days=1))
        resp = _login(client, "exp1")
        assert resp.status_code == 403
        assert resp.json()["detail"] == "account_expired"

    def test_login_expired_disables_user(self, client, engine):
        # Tras el intento de login la cuenta queda deshabilitada en BD
        _make_user(engine, "exp2", expires_at=_now() - timedelta(days=1))
        _login(client, "exp2")
        with Session(engine) as db:
            u = db.scalar(select(User).where(User.username == "exp2"))
            assert u.is_enabled is False

    def test_login_expired_logs_status(self, client, engine):
        _make_user(engine, "exp3", expires_at=_now() - timedelta(days=1))
        _login(client, "exp3")
        with Session(engine) as db:
            u = db.scalar(select(User).where(User.username == "exp3"))
            logs = db.scalars(
                select(UserStatusLog).where(UserStatusLog.user_id == u.id)
            ).all()
        assert any(l.status == "expired" for l in logs)

    def test_login_expired_notifies_admins_inapp(self, client, engine):
        # La notificación in-app llega a todos los admins activos
        admin = _make_user(engine, "exp_admin", is_admin=True)
        _make_user(engine, "exp4", expires_at=_now() - timedelta(days=1))

        _login(client, "exp4")

        notifs = _admin_notifs(engine, admin.id)
        assert len(notifs) == 1
        assert notifs[0].type == "user_expired"
        assert "exp4" in notifs[0].title

    def test_login_expired_calls_email_notify(self, client, engine):
        # Con notify_admins mockeado, verificamos que se llama con el username del usuario
        _make_user(engine, "exp_email_admin", is_admin=True, email="a@test.com")
        _make_user(engine, "exp5", expires_at=_now() - timedelta(days=1))

        with patch("app.api.auth.notify_admins") as mock_email:
            _login(client, "exp5")
            assert mock_email.called
            assert "exp5" in str(mock_email.call_args)

    def test_login_disabled_manually_returns_generic_message(self, client, engine):
        # Usuario deshabilitado por admin (sin expires_at) → mensaje genérico, no account_expired
        _make_user(engine, "manual_dis", is_enabled=False)
        resp = _login(client, "manual_dis")
        assert resp.status_code == 403
        assert resp.json()["detail"] == "Contactar con el administrador"

    def test_login_not_expired_succeeds(self, client, engine):
        # expires_at en el futuro → login OK
        _make_user(engine, "future_ok", expires_at=_now() + timedelta(days=30))
        resp = _login(client, "future_ok")
        assert resp.status_code == 200

    def test_login_second_attempt_no_duplicate_notif(self, client, engine):
        # El segundo intento de login (ya deshabilitado) no crea otra notificación
        admin = _make_user(engine, "dup_admin", is_admin=True)
        _make_user(engine, "dup_user", expires_at=_now() - timedelta(days=1))

        _login(client, "dup_user")  # primer intento: desactiva y notifica
        _login(client, "dup_user")  # segundo intento: ya is_enabled=False

        notifs = _admin_notifs(engine, admin.id)
        # Solo una notificación (el segundo login llega al bloque is_enabled=False genérico)
        assert len(notifs) == 1


# ===========================================================================
#  Bloque 2 — POST /auth/request-renewal
# ===========================================================================

class TestRequestRenewal:
    """Usuario caducado puede solicitar renovación sin estar autenticado."""

    def test_renewal_notifies_admins(self, client, engine):
        past = _now() - timedelta(days=3)
        admin = _make_user(engine, "ren_admin", is_admin=True)
        _make_user(engine, "ren_user", expires_at=past, is_enabled=False)

        resp = client.post("/api/auth/request-renewal", json={"username": "ren_user"})

        assert resp.status_code == 200
        assert resp.json()["ok"] is True
        notifs = _admin_notifs(engine, admin.id)
        assert len(notifs) == 1
        assert notifs[0].type == "renewal_request"
        assert "ren_user" in notifs[0].title

    def test_renewal_works_while_still_enabled(self, client, engine):
        # Usuario caducado que aún no intentó login (is_enabled=True)
        past = _now() - timedelta(days=1)
        admin = _make_user(engine, "ren2_admin", is_admin=True)
        _make_user(engine, "ren2_user", expires_at=past)  # is_enabled=True

        resp = client.post("/api/auth/request-renewal", json={"username": "ren2_user"})

        assert resp.status_code == 200
        notifs = _admin_notifs(engine, admin.id)
        assert any(n.type == "renewal_request" for n in notifs)

    def test_renewal_unknown_user_returns_ok(self, client, engine):
        # Siempre 200 — no revelar si el usuario existe (anti-enumeración)
        resp = client.post("/api/auth/request-renewal", json={"username": "nobody"})
        assert resp.status_code == 200
        assert resp.json()["ok"] is True

    def test_renewal_active_user_no_notif(self, client, engine):
        # Usuario activo sin expires_at → no genera notificación
        admin = _make_user(engine, "ren3_admin", is_admin=True)
        _make_user(engine, "ren3_user")  # sin expires_at

        client.post("/api/auth/request-renewal", json={"username": "ren3_user"})

        assert len(_admin_notifs(engine, admin.id)) == 0

    def test_renewal_admin_account_no_notif(self, client, engine):
        # Un admin caducado no puede solicitar renovación a través de este endpoint
        past = _now() - timedelta(days=1)
        admin = _make_user(engine, "ren4_admin", is_admin=True, expires_at=past)

        client.post("/api/auth/request-renewal", json={"username": "ren4_admin"})

        # No se generan notificaciones de renewal_request
        notifs = _admin_notifs(engine, admin.id)
        assert not any(n.type == "renewal_request" for n in notifs)

    def test_renewal_calls_email_notify(self, client, engine):
        # Con notify_admins mockeado se verifica que se llama
        past = _now() - timedelta(days=1)
        _make_user(engine, "ren5_admin", is_admin=True, email="a@test.com")
        _make_user(engine, "ren5_user", expires_at=past)

        with patch("app.api.auth.notify_admins") as mock_email:
            client.post("/api/auth/request-renewal", json={"username": "ren5_user"})
            assert mock_email.called
            assert "ren5_user" in str(mock_email.call_args)

    def test_renewal_multiple_admins_all_notified(self, client, engine):
        past = _now() - timedelta(days=1)
        admin1 = _make_user(engine, "multi_a1", is_admin=True)
        admin2 = _make_user(engine, "multi_a2", is_admin=True)
        _make_user(engine, "multi_user", expires_at=past)

        client.post("/api/auth/request-renewal", json={"username": "multi_user"})

        assert len(_admin_notifs(engine, admin1.id)) == 1
        assert len(_admin_notifs(engine, admin2.id)) == 1

    def test_renewal_creates_catalog_message(self, client, engine):
        # La solicitud debe aparecer en "Mensajes de usuarios" del AdminPanel
        past = _now() - timedelta(days=2)
        user = _make_user(engine, "msg_user", expires_at=past)

        client.post("/api/auth/request-renewal", json={"username": "msg_user"})

        with Session(engine) as s:
            msgs = s.scalars(
                select(CatalogMessageRow).where(CatalogMessageRow.user_id == user.id)
            ).all()
        assert len(msgs) == 1
        assert "renovación" in msgs[0].subject.lower()
        assert "msg_user" in msgs[0].message


# ===========================================================================
#  Bloque 3 — Job nocturno check_expired_users
# ===========================================================================

class TestCheckExpiredUsers:
    """El job nocturno detecta caducados, los desactiva y notifica a los admins."""

    def test_job_disables_expired(self, engine):
        from app.scheduler.jobs import check_expired_users
        past = _now() - timedelta(days=1)
        with Session(engine) as s:
            u = User(username="job1", password_hash=hash_password("p123456789"),
                     expires_at=past, is_enabled=True)
            s.add(u)
            s.commit()
            uid = u.id
        with Session(engine) as s:
            check_expired_users(s)
        with Session(engine) as s:
            assert s.get(User, uid).is_enabled is False

    def test_job_logs_expired_status(self, engine):
        from app.scheduler.jobs import check_expired_users
        past = _now() - timedelta(days=1)
        with Session(engine) as s:
            u = User(username="job2", password_hash=hash_password("p123456789"),
                     expires_at=past, is_enabled=True)
            s.add(u)
            s.commit()
            uid = u.id
        with Session(engine) as s:
            check_expired_users(s)
        with Session(engine) as s:
            logs = s.scalars(
                select(UserStatusLog).where(UserStatusLog.user_id == uid)
            ).all()
        assert any(l.status == "expired" for l in logs)

    def test_job_notifies_admins_inapp(self, engine):
        from app.scheduler.jobs import check_expired_users
        past = _now() - timedelta(days=1)
        with Session(engine) as s:
            admin = User(username="job_admin", password_hash=hash_password("p123456789"),
                         is_admin=True, is_enabled=True)
            user = User(username="job3", password_hash=hash_password("p123456789"),
                        expires_at=past, is_enabled=True)
            s.add_all([admin, user])
            s.commit()
            admin_id = admin.id
        with Session(engine) as s:
            check_expired_users(s)
        with Session(engine) as s:
            notifs = s.scalars(
                select(UserNotificationRow).where(UserNotificationRow.user_id == admin_id)
            ).all()
        assert len(notifs) == 1
        assert notifs[0].type == "user_expired"
        assert "job3" in notifs[0].title

    def test_job_skips_already_disabled(self, engine):
        # Ya deshabilitado (is_enabled=False) → el job no lo reprocesa
        from app.scheduler.jobs import check_expired_users
        past = _now() - timedelta(days=1)
        with Session(engine) as s:
            admin = User(username="job_skip_admin", password_hash=hash_password("p123456789"),
                         is_admin=True, is_enabled=True)
            user = User(username="job_skip", password_hash=hash_password("p123456789"),
                        expires_at=past, is_enabled=False)  # ya deshabilitado
            s.add_all([admin, user])
            s.commit()
            admin_id = admin.id
        with Session(engine) as s:
            count = check_expired_users(s)
        assert count == 0
        with Session(engine) as s:
            notifs = s.scalars(
                select(UserNotificationRow).where(UserNotificationRow.user_id == admin_id)
            ).all()
        assert len(notifs) == 0

    def test_job_skips_admin_users(self, engine):
        # Admins caducados no son procesados por el job
        from app.scheduler.jobs import check_expired_users
        past = _now() - timedelta(days=1)
        with Session(engine) as s:
            admin = User(username="job_exp_admin", password_hash=hash_password("p123456789"),
                         is_admin=True, expires_at=past, is_enabled=True)
            s.add(admin)
            s.commit()
            uid = admin.id
        with Session(engine) as s:
            count = check_expired_users(s)
        assert count == 0
        with Session(engine) as s:
            assert s.get(User, uid).is_enabled is True

    def test_job_skips_future_expiry(self, engine):
        # expires_at en el futuro → no procesado
        from app.scheduler.jobs import check_expired_users
        future = _now() + timedelta(days=30)
        with Session(engine) as s:
            u = User(username="job_future", password_hash=hash_password("p123456789"),
                     expires_at=future, is_enabled=True)
            s.add(u)
            s.commit()
            uid = u.id
        with Session(engine) as s:
            count = check_expired_users(s)
        assert count == 0
        with Session(engine) as s:
            assert s.get(User, uid).is_enabled is True

    def test_job_returns_count(self, engine):
        from app.scheduler.jobs import check_expired_users
        past = _now() - timedelta(days=1)
        with Session(engine) as s:
            for i in range(3):
                s.add(User(username=f"jcount{i}", password_hash=hash_password("p123456789"),
                           expires_at=past, is_enabled=True))
            s.commit()
        with Session(engine) as s:
            count = check_expired_users(s)
        assert count == 3

    def test_job_multiple_users_multiple_notifs(self, engine):
        # Con varios caducados, el admin recibe una notificación por cada usuario
        from app.scheduler.jobs import check_expired_users
        past = _now() - timedelta(days=1)
        with Session(engine) as s:
            admin = User(username="multi_job_admin", password_hash=hash_password("p123456789"),
                         is_admin=True, is_enabled=True)
            s.add(admin)
            for i in range(2):
                s.add(User(username=f"multi_exp{i}", password_hash=hash_password("p123456789"),
                           expires_at=past, is_enabled=True))
            s.commit()
            admin_id = admin.id
        with Session(engine) as s:
            check_expired_users(s)
        with Session(engine) as s:
            notifs = s.scalars(
                select(UserNotificationRow).where(UserNotificationRow.user_id == admin_id)
            ).all()
        assert len(notifs) == 2
