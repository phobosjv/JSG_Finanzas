"""
test_v1130.py
=============
Tests de integración para las dos features de v1.13.0:

  1. Mensajes con asunto + respuesta del admin (campo subject, pending-count,
     POST /messages/{id}/reply, notificación message_reply).
  2. Campos de moneda nativa en PositionSummary (avg_cost_native, market_value_native,
     unrealized_pnl_native, etc.) para posiciones en USD.

Nota sobre fixtures: auth_client y admin_client comparten el mismo cliente HTTP
(conftest.py, StaticPool). Para tests que necesitan acciones de usuario Y admin
usamos re-login explícito en el mismo client.
"""

import pytest
from decimal import Decimal
from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy import select

from app.models import MarketRow, User, EcbRate, PriceSnapshot
from app.auth.security import hash_password
from app.models.catalog_requests import CatalogMessageRow, UserNotificationRow


def _now_str():
    return datetime.now().isoformat(timespec="seconds")


# ---------------------------------------------------------------------------
#  Fixtures compartidas
# ---------------------------------------------------------------------------

@pytest.fixture()
def ua_pair(engine):
    """Crea un usuario normal y un admin. Devuelve (user, admin)."""
    with Session(engine) as db:
        u = User(username="msg_user", password_hash=hash_password("upass"))
        a = User(username="msg_admin", password_hash=hash_password("apass"), is_admin=True)
        db.add(u); db.add(a)
        db.commit()
        db.refresh(u); db.refresh(a)
        return u, a


def _login(client, username, password):
    client.post("/api/auth/login", json={"username": username, "password": password})


# ===========================================================================
#  Bloque 1 — Mensajes: asunto + respuesta del admin
# ===========================================================================

class TestMessageSubject:
    """El campo subject se guarda y se devuelve correctamente."""

    def test_subject_stored_and_returned(self, client, ua_pair):
        _login(client, "msg_user", "upass")
        resp = client.post("/api/catalog/messages", json={
            "message": "No encuentro el ETF de oro",
            "subject": "Mercados",
        })
        assert resp.status_code == 201, resp.text
        data = resp.json()
        assert data["subject"] == "Mercados"
        assert data["message"] == "No encuentro el ETF de oro"

    def test_subject_defaults_to_empty_string(self, client, ua_pair):
        _login(client, "msg_user", "upass")
        resp = client.post("/api/catalog/messages", json={"message": "Mensaje sin asunto"})
        assert resp.status_code == 201
        assert resp.json()["subject"] == ""

    def test_admin_sees_subject(self, client, ua_pair):
        _login(client, "msg_user", "upass")
        client.post("/api/catalog/messages", json={"message": "Pregunta", "subject": "Portfolio"})
        _login(client, "msg_admin", "apass")
        resp = client.get("/api/admin/catalog/messages")
        assert resp.status_code == 200
        msgs = resp.json()
        assert any(m["subject"] == "Portfolio" for m in msgs)

    def test_subject_max_100_chars(self, client, ua_pair):
        _login(client, "msg_user", "upass")
        resp = client.post("/api/catalog/messages", json={
            "message": "Msg",
            "subject": "A" * 101,
        })
        assert resp.status_code == 422


class TestMessagesPendingCount:
    """GET /api/admin/catalog/messages/pending-count devuelve el nº de no-resueltos."""

    def test_count_zero_when_empty(self, client, ua_pair):
        _login(client, "msg_admin", "apass")
        resp = client.get("/api/admin/catalog/messages/pending-count")
        assert resp.status_code == 200
        assert resp.json()["count"] == 0

    def test_count_increases_with_messages(self, client, ua_pair):
        _login(client, "msg_user", "upass")
        client.post("/api/catalog/messages", json={"message": "Msg 1"})
        client.post("/api/catalog/messages", json={"message": "Msg 2"})
        _login(client, "msg_admin", "apass")
        resp = client.get("/api/admin/catalog/messages/pending-count")
        assert resp.json()["count"] == 2

    def test_count_decreases_after_resolve(self, client, ua_pair):
        _login(client, "msg_user", "upass")
        msg_id = client.post("/api/catalog/messages", json={"message": "Resolver"}).json()["id"]
        _login(client, "msg_admin", "apass")
        assert client.get("/api/admin/catalog/messages/pending-count").json()["count"] == 1
        client.patch(f"/api/admin/catalog/messages/{msg_id}/resolve")
        assert client.get("/api/admin/catalog/messages/pending-count").json()["count"] == 0

    def test_count_requires_admin(self, client, ua_pair):
        _login(client, "msg_user", "upass")
        resp = client.get("/api/admin/catalog/messages/pending-count")
        assert resp.status_code == 403


class TestAdminReplyToMessage:
    """POST /api/admin/catalog/messages/{id}/reply guarda la respuesta."""

    def test_reply_stored_and_returned(self, client, ua_pair):
        _login(client, "msg_user", "upass")
        msg_id = client.post("/api/catalog/messages", json={
            "message": "¿Dónde está el fondo Vanguard?",
        }).json()["id"]

        _login(client, "msg_admin", "apass")
        resp = client.post(f"/api/admin/catalog/messages/{msg_id}/reply", json={
            "reply": "Lo añadiremos la próxima semana.",
        })
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["admin_reply"] == "Lo añadiremos la próxima semana."
        assert data["admin_reply_at"] is not None
        # La respuesta marca el mensaje como resuelto
        assert data["is_resolved"] is True

    def test_reply_empty_rejected(self, client, ua_pair):
        _login(client, "msg_user", "upass")
        msg_id = client.post("/api/catalog/messages", json={"message": "Pregunta"}).json()["id"]
        _login(client, "msg_admin", "apass")
        resp = client.post(f"/api/admin/catalog/messages/{msg_id}/reply", json={"reply": ""})
        assert resp.status_code == 422

    def test_reply_twice_returns_409(self, client, ua_pair):
        _login(client, "msg_user", "upass")
        msg_id = client.post("/api/catalog/messages", json={"message": "Doble respuesta"}).json()["id"]
        _login(client, "msg_admin", "apass")
        client.post(f"/api/admin/catalog/messages/{msg_id}/reply", json={"reply": "Primera"})
        resp = client.post(f"/api/admin/catalog/messages/{msg_id}/reply", json={"reply": "Segunda"})
        assert resp.status_code == 409

    def test_reply_creates_message_reply_notification(self, client, ua_pair, engine):
        """Responder a un mensaje genera una notificación message_reply al usuario."""
        user, _ = ua_pair

        _login(client, "msg_user", "upass")
        msg_id = client.post("/api/catalog/messages", json={
            "message": "Tengo una duda",
            "subject": "Mercados",
        }).json()["id"]

        _login(client, "msg_admin", "apass")
        client.post(f"/api/admin/catalog/messages/{msg_id}/reply", json={
            "reply": "Aquí tienes la respuesta.",
        })

        with Session(engine) as db:
            notif = db.execute(
                select(UserNotificationRow).where(
                    UserNotificationRow.user_id == user.id,
                    UserNotificationRow.type == "message_reply",
                )
            ).scalar_one_or_none()

        assert notif is not None
        assert notif.related_id == msg_id
        assert notif.related_type == "catalog_message"

    def test_reply_count_decremented_after_reply(self, client, ua_pair):
        """Una respuesta resuelve el mensaje → pending-count baja."""
        _login(client, "msg_user", "upass")
        msg_id = client.post("/api/catalog/messages", json={"message": "Consulta"}).json()["id"]
        _login(client, "msg_admin", "apass")
        assert client.get("/api/admin/catalog/messages/pending-count").json()["count"] == 1
        client.post(f"/api/admin/catalog/messages/{msg_id}/reply", json={"reply": "Hecho."})
        assert client.get("/api/admin/catalog/messages/pending-count").json()["count"] == 0

    def test_user_cannot_reply(self, client, ua_pair):
        _login(client, "msg_user", "upass")
        msg_id = client.post("/api/catalog/messages", json={"message": "Consulta"}).json()["id"]
        resp = client.post(f"/api/admin/catalog/messages/{msg_id}/reply", json={"reply": "..."})
        assert resp.status_code == 403


# ===========================================================================
#  Bloque 2 — Moneda nativa en PositionSummary
# ===========================================================================

@pytest.fixture()
def nasdaq_market(engine):
    """Inserta el mercado Nasdaq en USD."""
    with Session(engine) as db:
        db.merge(MarketRow(
            code="nasdaq", name="Nasdaq",
            currency="USD", fiscal_window_days=60, market_type="stock",
            created_at=_now_str(),
        ))
        db.commit()
    return "nasdaq"


@pytest.fixture()
def usd_position(admin_client, engine, nasdaq_market):
    """
    Crea un valor USD, inserta snapshot (last_price=200 USD) y tipo BCE 1.10,
    y abre una posición con una compra de 5 acc × 100 USD.

    Aritmética:
      - avg_cost_native     = 100 USD
      - cost_native         = 5 × 100 = 500 USD
      - market_value_native = 5 × 200 = 1 000 USD
      - unrealized_pnl_native = 1 000 - 500 = 500 USD
      - market_value_eur    = 1 000 / 1.10 ≈ 909.09 EUR
    """
    r = admin_client.post("/api/securities", json={
        "name": "MicroStrategy", "yahoo_ticker": "MSTR",
        "market": "nasdaq", "currency": "USD",
    })
    sec_id = r.json()["id"]

    with Session(engine) as db:
        db.add(EcbRate(date="2025-01-15", rate=Decimal("1.10")))
        db.add(PriceSnapshot(
            security_id=sec_id,
            last_price=Decimal("200"),
            prev_close=None,
            daily_change_pct=None,
            min_1y=None, min_2y=None, min_5y=None, max_1y=None,
            last_dividend=None,
        ))
        db.commit()

    pos = admin_client.post("/api/portfolio/positions", json={"security_id": sec_id}).json()
    pos_id = pos["id"]
    admin_client.post(f"/api/portfolio/{pos_id}/transactions", json={
        "type": "buy", "date": "2025-01-15",
        "shares": "5", "price": "100.00",
        "currency": "USD", "exchange_rate": "1.10", "fee": "0",
    })
    return pos_id, sec_id


class TestNativeCurrencyFields:
    """Los campos *_native de PositionSummary reflejan el valor en moneda original."""

    def test_open_position_native_fields_present(self, admin_client, usd_position):
        """GET /api/portfolio devuelve todos los campos *_native."""
        resp = admin_client.get("/api/portfolio")
        assert resp.status_code == 200
        pos = resp.json()[0]

        for field in ("avg_cost_native", "cost_native", "market_value_native",
                      "unrealized_pnl_native", "dividends_native",
                      "realized_pnl_native", "total_profit_native", "fees_native"):
            assert field in pos, f"Falta campo {field}"

    def test_open_position_native_values(self, admin_client, usd_position):
        """
        5 acc × 100 USD compradas, precio actual 200 USD:
          avg_cost_native     = 100
          cost_native         = 500
          market_value_native = 1 000
          unrealized_pnl_native = 500
        """
        resp = admin_client.get("/api/portfolio")
        pos = resp.json()[0]

        assert float(pos["avg_cost_native"]) == pytest.approx(100.0)
        assert float(pos["cost_native"])     == pytest.approx(500.0)
        assert float(pos["market_value_native"]) == pytest.approx(1000.0)
        assert float(pos["unrealized_pnl_native"]) == pytest.approx(500.0)
        assert float(pos["fees_native"]) == pytest.approx(0.0)

    def test_open_position_eur_fields_still_correct(self, admin_client, usd_position):
        """Los campos _eur siguen calculándose correctamente (no se rompen)."""
        resp = admin_client.get("/api/portfolio")
        pos = resp.json()[0]
        # market_value_eur = 1 000 USD / 1.10 ≈ 909.09
        assert float(pos["market_value_eur"]) == pytest.approx(1000 / 1.10, rel=1e-4)

    def test_currency_field_is_usd(self, admin_client, usd_position):
        """El campo currency del resumen debe ser 'USD'."""
        resp = admin_client.get("/api/portfolio")
        pos = resp.json()[0]
        assert pos["currency"] == "USD"

    def test_eur_position_native_equals_eur(self, admin_client, engine):
        """
        Para una posición EUR, los campos *_native deben coincidir con los *_eur
        (o estar en EUR: la moneda nativa de EUR es EUR mismo).
        """
        with Session(engine) as db:
            db.merge(MarketRow(
                code="ibex35", name="IBEX 35",
                currency="EUR", fiscal_window_days=365, market_type="stock",
                created_at=_now_str(),
            ))
            db.commit()

        r = admin_client.post("/api/securities", json={
            "name": "Banco Santander", "yahoo_ticker": "SAN.MC",
            "market": "ibex35", "currency": "EUR",
        })
        sec_id = r.json()["id"]

        with Session(engine) as db:
            db.add(PriceSnapshot(
                security_id=sec_id,
                last_price=Decimal("4.50"),
                prev_close=None, daily_change_pct=None,
                min_1y=None, min_2y=None, min_5y=None, max_1y=None,
                last_dividend=None,
            ))
            db.commit()

        pos_id = admin_client.post(
            "/api/portfolio/positions", json={"security_id": sec_id}
        ).json()["id"]
        admin_client.post(f"/api/portfolio/{pos_id}/transactions", json={
            "type": "buy", "date": "2025-01-15",
            "shares": "10", "price": "4.00",
            "currency": "EUR", "exchange_rate": "1", "fee": "0",
        })

        resp = admin_client.get("/api/portfolio")
        pos = next(p for p in resp.json() if p["security_id"] == sec_id)

        # EUR: native ≡ EUR
        assert float(pos["cost_native"]) == pytest.approx(float(pos["cost_eur"]), rel=1e-4)
        assert float(pos["market_value_native"]) == pytest.approx(float(pos["market_value_eur"]), rel=1e-4)


# ===========================================================================
#  Bloque 3 — Notificaciones personalizadas del administrador
# ===========================================================================

@pytest.fixture()
def notif_users(engine):
    """Crea dos usuarios normales y un admin. Devuelve (user1, user2, admin)."""
    with Session(engine) as db:
        u1 = User(username="notif_u1", password_hash=hash_password("p1"), is_enabled=True)
        u2 = User(username="notif_u2", password_hash=hash_password("p2"), is_enabled=True)
        a  = User(username="notif_adm", password_hash=hash_password("ap"), is_admin=True, is_enabled=True)
        db.add(u1); db.add(u2); db.add(a)
        db.commit()
        db.refresh(u1); db.refresh(u2); db.refresh(a)
        return u1, u2, a


class TestAdminSendNotification:
    """POST /api/admin/notifications/send — notificaciones personalizadas del admin."""

    def test_send_to_single_user(self, client, notif_users, engine):
        """El admin puede enviar una notificación a un usuario concreto."""
        user1, _, admin = notif_users
        client.post("/api/auth/login", json={"username": "notif_adm", "password": "ap"})

        resp = client.post("/api/admin/notifications/send", json={
            "user_id": user1.id,
            "title": "Hola",
            "body": "Tienes un mensaje importante.",
        })
        assert resp.status_code == 200, resp.text
        assert resp.json()["sent"] == 1

        with Session(engine) as db:
            notif = db.execute(
                select(UserNotificationRow).where(UserNotificationRow.user_id == user1.id)
            ).scalar_one_or_none()

        assert notif is not None
        assert notif.type == "admin_message"
        assert notif.title == "Hola"
        assert notif.body == "Tienes un mensaje importante."

    def test_send_only_reaches_target_user(self, client, notif_users, engine):
        """La notificación individual no llega al resto de usuarios."""
        user1, user2, _ = notif_users
        client.post("/api/auth/login", json={"username": "notif_adm", "password": "ap"})
        client.post("/api/admin/notifications/send", json={
            "user_id": user1.id,
            "title": "Solo para user1",
            "body": "Msg",
        })

        with Session(engine) as db:
            for uid in [user2.id]:
                n = db.execute(
                    select(UserNotificationRow).where(UserNotificationRow.user_id == uid)
                ).scalar_one_or_none()
                assert n is None, f"user_id={uid} no debería tener notificación"

    def test_broadcast_reaches_all_enabled_users(self, client, notif_users, engine):
        """Broadcast (user_id=null) llega a todos los usuarios activos."""
        user1, user2, admin = notif_users
        client.post("/api/auth/login", json={"username": "notif_adm", "password": "ap"})

        resp = client.post("/api/admin/notifications/send", json={
            "user_id": None,
            "title": "Mantenimiento programado",
            "body": "El sistema estará en mantenimiento mañana a las 03:00.",
        })
        assert resp.status_code == 200
        # Hay 3 usuarios activos (user1, user2, admin)
        assert resp.json()["sent"] == 3

        with Session(engine) as db:
            count = db.execute(
                select(UserNotificationRow).where(
                    UserNotificationRow.type == "admin_message",
                    UserNotificationRow.title == "Mantenimiento programado",
                )
            ).scalars().all()
        assert len(count) == 3

    def test_broadcast_empty_users(self, client, engine):
        """Broadcast con 0 usuarios activos devuelve {sent: 0} sin error.

        Nota: en este test no se crean fixtures de usuarios activos, pero el
        admin que hace login también es is_enabled=True, así que se espera 1
        (el propio admin). Verificamos solo que no hay error.
        """
        with Session(engine) as db:
            a = User(username="lone_admin", password_hash=hash_password("ap2"), is_admin=True, is_enabled=True)
            db.add(a); db.commit()

        client.post("/api/auth/login", json={"username": "lone_admin", "password": "ap2"})
        resp = client.post("/api/admin/notifications/send", json={
            "user_id": None, "title": "T", "body": "B",
        })
        assert resp.status_code == 200
        assert resp.json()["sent"] >= 1

    def test_send_to_nonexistent_user_returns_404(self, client, notif_users):
        """Enviar a un user_id que no existe devuelve 404."""
        client.post("/api/auth/login", json={"username": "notif_adm", "password": "ap"})
        resp = client.post("/api/admin/notifications/send", json={
            "user_id": 99999,
            "title": "Test",
            "body": "Cuerpo",
        })
        assert resp.status_code == 404

    def test_non_admin_cannot_send(self, client, notif_users):
        """Un usuario normal recibe 403."""
        client.post("/api/auth/login", json={"username": "notif_u1", "password": "p1"})
        resp = client.post("/api/admin/notifications/send", json={
            "user_id": None, "title": "T", "body": "B",
        })
        assert resp.status_code == 403

    def test_unauthenticated_returns_401(self, client, notif_users):
        """Sin sesión devuelve 401."""
        client.post("/api/auth/logout")
        resp = client.post("/api/admin/notifications/send", json={
            "user_id": None, "title": "T", "body": "B",
        })
        assert resp.status_code == 401

    def test_user_sees_admin_notification_in_bell(self, client, notif_users):
        """La notificación admin_message aparece en GET /notifications del usuario."""
        user1, _, _ = notif_users
        client.post("/api/auth/login", json={"username": "notif_adm", "password": "ap"})
        client.post("/api/admin/notifications/send", json={
            "user_id": user1.id,
            "title": "Bienvenido",
            "body": "Tu cuenta está activa.",
        })

        client.post("/api/auth/login", json={"username": "notif_u1", "password": "p1"})
        resp = client.get("/api/notifications")
        assert resp.status_code == 200
        notifs = resp.json()
        assert any(n["type"] == "admin_message" and n["title"] == "Bienvenido" for n in notifs)

    def test_empty_title_rejected(self, client, notif_users):
        """Un título vacío devuelve 422."""
        client.post("/api/auth/login", json={"username": "notif_adm", "password": "ap"})
        resp = client.post("/api/admin/notifications/send", json={
            "user_id": None, "title": "", "body": "Msg",
        })
        assert resp.status_code == 422

    def test_empty_body_rejected(self, client, notif_users):
        """Un cuerpo vacío devuelve 422."""
        client.post("/api/auth/login", json={"username": "notif_adm", "password": "ap"})
        resp = client.post("/api/admin/notifications/send", json={
            "user_id": None, "title": "T", "body": "",
        })
        assert resp.status_code == 422
