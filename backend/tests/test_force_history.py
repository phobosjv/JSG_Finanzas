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
    monkeypatch.setattr(jobs, "update_price_history", lambda db: llamadas.append("price_history"))
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
    assert jobs_mockeados == ["price_history", "snapshots", "ecb_rates"], (
        "debe ejecutar las mismas tres tareas que el job nocturno, en el mismo orden"
    )


def test_force_history_update_requiere_admin(auth_client):
    assert auth_client.post("/api/admin/force-history-update").status_code == 403


def test_force_history_update_rechaza_concurrencia(admin_client, monkeypatch):
    """Con un job en curso, una segunda peticion devuelve 409."""
    import threading
    soltar = threading.Event()
    monkeypatch.setattr(jobs, "update_price_history", lambda db: soltar.wait(timeout=5))
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
    monkeypatch.setattr(jobs, "update_price_history", lambda db: None)
    monkeypatch.setattr(jobs, "update_snapshots", lambda db: None)
    def _boom(db):
        raise RuntimeError("Yahoo caido")
    monkeypatch.setattr(jobs, "update_ecb_rates", _boom)

    assert admin_client.post("/api/admin/force-history-update").status_code == 202
    estado = _esperar_fin(admin_client)
    assert "error" in estado["result"] and "Yahoo caido" in estado["result"]
