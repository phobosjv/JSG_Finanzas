"""
test_push.py
============
Tests de las notificaciones push (Web Push, v1.10.0).

Cubre:
  * Generación y persistencia de las claves VAPID.
  * Endpoints subscribe / unsubscribe / vapid-key.
  * Cálculo de alertas activas por usuario (compra desde favorites,
    venta desde positions).
  * check_push_alerts: solo notifica alertas NUEVAS (deduplicación por
    last_notified_keys).
"""
from decimal import Decimal as D

from sqlalchemy.orm import Session

from app.models import (
    AppConfig, Favorite, Position, PriceSnapshot, PushSubscription,
)


# ---------------------------------------------------------------------------
#  VAPID
# ---------------------------------------------------------------------------

def test_vapid_keys_se_generan(db):
    """ensure_vapid_keys genera y persiste un par de claves la primera vez."""
    from app.api.push import ensure_vapid_keys, get_vapid_public_key, get_vapid_private_key

    assert get_vapid_public_key(db) is None
    ensure_vapid_keys(db)
    pub = get_vapid_public_key(db)
    priv = get_vapid_private_key(db)
    assert pub and len(pub) > 20
    assert priv and "PRIVATE KEY" in priv


def test_vapid_keys_no_se_regeneran(db):
    """Una segunda llamada a ensure_vapid_keys no cambia las claves existentes."""
    from app.api.push import ensure_vapid_keys, get_vapid_public_key

    ensure_vapid_keys(db)
    pub1 = get_vapid_public_key(db)
    ensure_vapid_keys(db)
    pub2 = get_vapid_public_key(db)
    assert pub1 == pub2


def test_vapid_key_endpoint_publico(client, db):
    """GET /api/push/vapid-key devuelve la clave pública sin requerir auth."""
    from app.api.push import ensure_vapid_keys
    ensure_vapid_keys(db)
    db.commit()

    resp = client.get("/api/push/vapid-key")
    assert resp.status_code == 200
    assert "public_key" in resp.json()


# ---------------------------------------------------------------------------
#  Subscribe / Unsubscribe
# ---------------------------------------------------------------------------

_SUB = {
    "endpoint": "https://push.example.com/abc123",
    "keys": {"p256dh": "BPdummykeyp256dh", "auth": "authsecret"},
}


def test_subscribe_registra_suscripcion(auth_client, engine):
    """POST /api/push/subscribe guarda la suscripción del dispositivo."""
    resp = auth_client.post("/api/push/subscribe", json=_SUB)
    assert resp.status_code == 204

    with Session(engine) as s:
        subs = s.query(PushSubscription).all()
        assert len(subs) == 1
        assert subs[0].endpoint == _SUB["endpoint"]
        assert subs[0].p256dh == "BPdummykeyp256dh"


def test_subscribe_idempotente(auth_client, engine):
    """Re-suscribir el mismo endpoint actualiza, no duplica."""
    auth_client.post("/api/push/subscribe", json=_SUB)
    auth_client.post("/api/push/subscribe", json=_SUB)
    with Session(engine) as s:
        assert s.query(PushSubscription).count() == 1


def test_subscribe_requiere_auth(client):
    """POST /api/push/subscribe sin sesión devuelve 401."""
    resp = client.post("/api/push/subscribe", json=_SUB)
    assert resp.status_code == 401


def test_unsubscribe_elimina(auth_client, engine):
    """DELETE /api/push/subscribe elimina la suscripción del dispositivo."""
    auth_client.post("/api/push/subscribe", json=_SUB)
    resp = auth_client.request("DELETE", "/api/push/subscribe", json={"endpoint": _SUB["endpoint"]})
    assert resp.status_code == 204
    with Session(engine) as s:
        assert s.query(PushSubscription).count() == 0


# ---------------------------------------------------------------------------
#  Cálculo de alertas activas
# ---------------------------------------------------------------------------

def _snap(db, sec_id, price):
    db.merge(PriceSnapshot(security_id=sec_id, last_price=D(str(price))))
    db.commit()


def test_alert_keys_compra_desde_favorites(admin_client, seed_markets, engine, test_admin):
    """
    _compute_user_alert_keys detecta alerta de COMPRA cuando
    last_price <= favorites.target_buy_price.
    """
    from app.scheduler.jobs import _compute_user_alert_keys

    # Crear security + favorito con target_buy
    sec = admin_client.post("/api/securities", json={
        "name": "BuyCo", "yahoo_ticker": "BUY.MC", "market": "ibex35", "currency": "EUR",
    }).json()["id"]
    admin_client.post(f"/api/favorites/{sec}")
    admin_client.patch(f"/api/favorites/{sec}", json={"target_buy_price": "10"})

    with Session(engine) as s:
        _snap(s, sec, 9)  # precio por debajo del objetivo → alerta
        keys = _compute_user_alert_keys(s, test_admin.id)
    assert f"buy:{sec}" in keys


def test_alert_keys_venta_desde_positions(admin_client, seed_markets, engine, test_admin):
    """
    _compute_user_alert_keys detecta alerta de VENTA cuando
    last_price >= positions.target_sell_price.
    """
    from app.scheduler.jobs import _compute_user_alert_keys

    sec = admin_client.post("/api/securities", json={
        "name": "SellCo", "yahoo_ticker": "SELL.MC", "market": "ibex35", "currency": "EUR",
    }).json()["id"]
    pos = admin_client.post("/api/portfolio/positions", json={"security_id": sec}).json()["id"]
    admin_client.post(f"/api/portfolio/{pos}/transactions", json={
        "type": "buy", "date": "2024-01-02", "shares": "10", "price": "5",
        "fee": "0", "currency": "EUR", "exchange_rate": "1",
    })
    admin_client.patch(f"/api/portfolio/{pos}/target-sell", json={"target_sell_price": "20"})

    with Session(engine) as s:
        _snap(s, sec, 25)  # precio por encima del objetivo → alerta
        keys = _compute_user_alert_keys(s, test_admin.id)
    assert f"sell:{sec}" in keys


def test_alert_keys_sin_alerta(admin_client, seed_markets, engine, test_admin):
    """Sin objetivos alcanzados, no hay claves de alerta."""
    from app.scheduler.jobs import _compute_user_alert_keys

    sec = admin_client.post("/api/securities", json={
        "name": "NoneCo", "yahoo_ticker": "NONE.MC", "market": "ibex35", "currency": "EUR",
    }).json()["id"]
    admin_client.post(f"/api/favorites/{sec}")
    admin_client.patch(f"/api/favorites/{sec}", json={"target_buy_price": "10"})

    with Session(engine) as s:
        _snap(s, sec, 15)  # precio POR ENCIMA del objetivo de compra → sin alerta
        keys = _compute_user_alert_keys(s, test_admin.id)
    assert keys == []


# ---------------------------------------------------------------------------
#  check_push_alerts — deduplicación
# ---------------------------------------------------------------------------

def test_check_push_alerts_solo_notifica_nuevas(admin_client, seed_markets, engine, test_admin, monkeypatch):
    """
    check_push_alerts envía push solo cuando aparecen alertas NUEVAS.
    Si las alertas ya estaban en last_notified_keys, no se reenvía.
    """
    import app.scheduler.jobs as jobs

    sent = []

    def _fake_webpush(**kwargs):
        sent.append(kwargs)

    # Parchear pywebpush.webpush (importado dentro de la función)
    import pywebpush
    monkeypatch.setattr(pywebpush, "webpush", _fake_webpush)

    # Setup: favorito con objetivo de compra alcanzado + VAPID + suscripción
    sec = admin_client.post("/api/securities", json={
        "name": "PushCo", "yahoo_ticker": "PUSH.MC", "market": "ibex35", "currency": "EUR",
    }).json()["id"]
    admin_client.post(f"/api/favorites/{sec}")
    admin_client.patch(f"/api/favorites/{sec}", json={"target_buy_price": "10"})
    admin_client.post("/api/push/subscribe", json=_SUB)

    with Session(engine) as s:
        from app.api.push import ensure_vapid_keys
        ensure_vapid_keys(s)
        _snap(s, sec, 9)  # alerta activa

        # Primera pasada → debe enviar 1 push
        jobs.check_push_alerts(s)
        assert len(sent) == 1, "La primera alerta nueva debe enviarse"

        # Segunda pasada sin cambios → no reenvía
        jobs.check_push_alerts(s)
        assert len(sent) == 1, "Una alerta ya notificada no debe reenviarse"
