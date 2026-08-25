"""
test_force_history.py
=====================
POST /api/admin/force-history-update — el boton de "forzar historico" del
AdminPanel.

Debe lanzar las MISMAS tres tareas que el job nocturno 'daily_update'. Los jobs
reales se mockean (no se toca la red) y se espera a que el hilo en segundo plano
termine haciendo polling del endpoint /status, que es justo lo que hace el
frontend.
"""

import time

import pytest

from app.scheduler import jobs


def _esperar_fin(client, timeout=10.0):
    """Poll de /status hasta que 'running' sea False. Devuelve el estado final."""
    limite = time.time() + timeout
    while time.time() < limite:
        st = client.get("/api/admin/force-history-update/status").json()
        if not st.get("running"):
            return st
        time.sleep(0.05)
    pytest.fail("el job no termino dentro del timeout")


@pytest.fixture
def jobs_mockeados(monkeypatch):
    """Sustituye los tres jobs por trazas, sin tocar red ni BBDD real."""
    llamadas = []
    # update_price_history recibe ahora 'full' como keyword.
    monkeypatch.setattr(jobs, "update_price_history",
                        lambda db, full=False: llamadas.append(f"price_history(full={full})"))
    monkeypatch.setattr(jobs, "update_snapshots", lambda db: llamadas.append("snapshots"))
    monkeypatch.setattr(jobs, "update_ecb_rates", lambda db: llamadas.append("ecb_rates"))
    return llamadas


# ---------------------------------------------------------------------------
#  Regresion: el boton no actualizaba los tipos del BCE
# ---------------------------------------------------------------------------
#
# 'daily_update' ejecuta price_history + snapshots + ecb_rates, pero el boton de
# admin solo hacia las dos primeras. El grafico de evolucion convierte cada
# cierre pasado con el tipo del BCE de ESA fecha; sin la tabla, _history_series
# cae al tipo mas reciente y distorsiona toda la serie de los valores en divisa.
#
# Se manifesto al migrar de servidor: el backup admin no exporta 'price_history'
# ni 'ecb_rates', y al forzar el historico solo se recuperaba la primera. Los
# tipos habia que esperarlos al nocturno de las 6:30, sin ninguna senal de por que.

def test_force_history_update_lanza_los_tres_jobs(admin_client, jobs_mockeados):
    resp = admin_client.post("/api/admin/force-history-update")
    assert resp.status_code == 202

    estado = _esperar_fin(admin_client)
    assert estado["result"] == "ok"
    assert jobs_mockeados == ["price_history(full=False)", "snapshots", "ecb_rates"], (
        "debe ejecutar las mismas tres tareas que el job nocturno, en el mismo orden"
    )


def test_force_history_update_requiere_admin(auth_client):
    assert auth_client.post("/api/admin/force-history-update").status_code == 403


def test_force_history_update_rechaza_concurrencia(admin_client, monkeypatch):
    """Con un job en curso, una segunda peticion devuelve 409."""
    import threading
    soltar = threading.Event()
    monkeypatch.setattr(jobs, "update_price_history", lambda db, full=False: soltar.wait(timeout=5))
    monkeypatch.setattr(jobs, "update_snapshots", lambda db: None)
    monkeypatch.setattr(jobs, "update_ecb_rates", lambda db: None)

    assert admin_client.post("/api/admin/force-history-update").status_code == 202
    try:
        # El primero sigue bloqueado dentro de update_price_history.
        assert admin_client.post("/api/admin/force-history-update").status_code == 409
    finally:
        soltar.set()
        _esperar_fin(admin_client)


def test_status_reporta_error_del_job(admin_client, monkeypatch):
    """Si un job revienta, /status lo refleja en 'result' y running vuelve a False."""
    monkeypatch.setattr(jobs, "update_price_history", lambda db, full=False: None)
    monkeypatch.setattr(jobs, "update_snapshots", lambda db: None)
    def _boom(db):
        raise RuntimeError("Yahoo caido")
    monkeypatch.setattr(jobs, "update_ecb_rates", _boom)

    assert admin_client.post("/api/admin/force-history-update").status_code == 202
    estado = _esperar_fin(admin_client)
    assert "error" in estado["result"] and "Yahoo caido" in estado["result"]


# ---------------------------------------------------------------------------
#  Reconstruccion completa (full=true)
# ---------------------------------------------------------------------------
#
# El modo incremental arranca en la ultima fecha guardada de cada valor, asi que
# NUNCA rellena hacia atras: un historico truncado -no vacio, pero que empieza
# despues de la primera compra- se quedaba asi para siempre. Es justo lo que deja
# una migracion de servidor, porque el backup admin no exporta price_history.

def test_force_history_full_propaga_la_reconstruccion(admin_client, jobs_mockeados):
    resp = admin_client.post("/api/admin/force-history-update?full=true")
    assert resp.status_code == 202
    estado = _esperar_fin(admin_client)
    assert estado["result"] == "ok"
    assert jobs_mockeados[0] == "price_history(full=True)"
    # Los otros dos jobs no cambian de comportamiento.
    assert jobs_mockeados[1:] == ["snapshots", "ecb_rates"]


def test_status_indica_si_fue_reconstruccion_completa(admin_client, jobs_mockeados):
    admin_client.post("/api/admin/force-history-update?full=true")
    assert _esperar_fin(admin_client)["full"] is True
    admin_client.post("/api/admin/force-history-update")
    assert _esperar_fin(admin_client)["full"] is False


def test_full_ignora_el_historico_existente(admin_client, seed_markets, engine, monkeypatch):
    """update_price_history(full=True) pide desde hace 5 anos aunque ya haya datos."""
    from datetime import date, timedelta
    from decimal import Decimal as D
    from sqlalchemy.orm import Session
    from app.models import PriceHistory, Security

    r = admin_client.post("/api/securities", json={
        "name": "Trunco", "yahoo_ticker": "TRUNC.MC",
        "market": "ibex35", "currency": "EUR",
    })
    sec_id = r.json()["id"]
    # Historico TRUNCADO: solo una fecha reciente.
    with Session(engine) as s:
        s.add(PriceHistory(security_id=sec_id, date=date.today().isoformat(), close=D("10")))
        s.commit()

    pedidos = []
    def fake_fetch(ticker, desde, hasta):
        pedidos.append((ticker, desde))
        return []
    monkeypatch.setattr(jobs._yahoo, "fetch_history", fake_fetch)

    with Session(engine) as s:
        jobs.update_price_history(s, full=True)
    trunc = [p for p in pedidos if p[0] == "TRUNC.MC"]
    assert trunc, "deberia haber pedido el historico de TRUNC.MC"
    _, desde = trunc[0]
    antiguedad = (date.today() - desde).days
    assert antiguedad > 1800, (
        f"con full=True debe pedir ~5 anos, pidio desde hace {antiguedad} dias"
    )


def test_incremental_no_rellena_hacia_atras(admin_client, seed_markets, engine, monkeypatch):
    """Sin 'full', un historico truncado NO se repara: se documenta el limite."""
    from datetime import date
    from decimal import Decimal as D
    from sqlalchemy.orm import Session
    from app.models import PriceHistory

    r = admin_client.post("/api/securities", json={
        "name": "Trunco2", "yahoo_ticker": "TRUNC2.MC",
        "market": "ibex35", "currency": "EUR",
    })
    sec_id = r.json()["id"]
    with Session(engine) as s:
        s.add(PriceHistory(security_id=sec_id, date=date.today().isoformat(), close=D("10")))
        s.commit()

    pedidos = []
    monkeypatch.setattr(jobs._yahoo, "fetch_history",
                        lambda t, d, h: pedidos.append((t, d)) or [])
    with Session(engine) as s:
        jobs.update_price_history(s)
    trunc = [p for p in pedidos if p[0] == "TRUNC2.MC"]
    assert trunc
    antiguedad = (date.today() - trunc[0][1]).days
    assert antiguedad <= 7, (
        "el modo incremental solo refresca la ventana reciente: es la razon de "
        f"que exista full=True (pidio desde hace {antiguedad} dias)"
    )
