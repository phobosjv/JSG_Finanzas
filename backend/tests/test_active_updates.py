"""
test_active_updates.py
======================
Tests de la actualización por "conjunto activo" (v1.7.7): solo se actualizan en
vivo los valores en uso (poseídos o favoritos); el resto va por el barrido
nocturno o el refresco perezoso/bajo demanda.

No se hacen llamadas reales a Yahoo: se prueban las rutas que NO disparan red
(conjunto activo, anti-rebote, throttle, mercado vacío).
"""

import time

from sqlalchemy.orm import Session

from app.api import markets as markets_api
from app.scheduler.jobs import _active_security_ids


def _sec(admin_client, ticker, market="ibex35"):
    return admin_client.post("/api/securities", json={
        "name": ticker, "yahoo_ticker": ticker, "market": market, "currency": "EUR",
    }).json()["id"]


# ---------------------------------------------------------------------------
#  Conjunto activo = posiciones ∪ favoritos
# ---------------------------------------------------------------------------

def test_conjunto_activo_posiciones_y_favoritos(admin_client, seed_markets, engine):
    sec_held = _sec(admin_client, "HELD.MC")
    sec_fav  = _sec(admin_client, "FAV.MC")
    sec_idle = _sec(admin_client, "IDLE.MC")

    admin_client.post("/api/portfolio/positions", json={"security_id": sec_held})
    admin_client.post(f"/api/favorites/{sec_fav}")

    with Session(engine) as s:
        active = _active_security_ids(s)

    assert sec_held in active
    assert sec_fav in active
    assert sec_idle not in active


# ---------------------------------------------------------------------------
#  Refresco perezoso (refresh-if-stale)
# ---------------------------------------------------------------------------

def test_refresh_if_stale_valor_activo_no_refresca(admin_client, seed_markets, engine):
    """Un valor en uso ya lo cubre el job en vivo → no refresca bajo demanda."""
    sec = _sec(admin_client, "ACT.MC")
    admin_client.post("/api/portfolio/positions", json={"security_id": sec})
    r = admin_client.post(f"/api/markets/{sec}/refresh-if-stale")
    assert r.status_code == 200
    assert r.json() == {"refreshed": False, "reason": "active"}


def test_refresh_if_stale_antirebote(admin_client, seed_markets, engine):
    """Si se refrescó hace poco (anti-rebote), no vuelve a pedir (sin red)."""
    sec = _sec(admin_client, "IDLE2.MC")   # no poseído ni favorito
    markets_api._LAST_LAZY_REFRESH[sec] = time.monotonic()
    r = admin_client.post(f"/api/markets/{sec}/refresh-if-stale")
    assert r.status_code == 200
    assert r.json() == {"refreshed": False, "reason": "recent"}


# ---------------------------------------------------------------------------
#  Refresco de movers bajo demanda (throttle / tamaño)
# ---------------------------------------------------------------------------

def test_refresh_movers_throttled(admin_client, seed_markets):
    """Llamada dentro de la ventana de throttle → no programa (sin red)."""
    markets_api._LAST_MOVERS_REFRESH["ibex35"] = time.monotonic()
    r = admin_client.post("/api/markets/ibex35/refresh-movers")
    assert r.status_code == 202
    assert r.json()["scheduled"] is False
    assert r.json()["reason"] == "throttled"


def test_refresh_movers_mercado_vacio(admin_client, seed_markets):
    """Un mercado sin valores no programa nada."""
    markets_api._LAST_MOVERS_REFRESH.pop("continuo", None)
    r = admin_client.post("/api/markets/continuo/refresh-movers")
    assert r.status_code == 202
    assert r.json()["scheduled"] is False
    assert r.json()["reason"] == "empty"
