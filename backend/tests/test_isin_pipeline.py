"""
test_isin_pipeline.py
=====================
Tests del pipeline admin que rellena ISINs vacíos desde Yahoo
(POST /api/admin/securities/fill-isins) y de la normalización de ISIN
del proveedor Yahoo.

La llamada a Yahoo se mockea (monkeypatch sobre YahooProvider.fetch_isin)
para no hacer red.
"""

import pytest

from app.providers.yahoo import _normalize_isin


# ---------------------------------------------------------------------------
#  Normalización de ISIN
# ---------------------------------------------------------------------------

def test_normalize_isin_valido():
    assert _normalize_isin("ES0144580Y14") == "ES0144580Y14"
    # minúsculas / espacios se sanean
    assert _normalize_isin(" us0378331005 ") == "US0378331005"


def test_normalize_isin_rechaza_basura():
    assert _normalize_isin("-") is None       # Yahoo cuando no lo conoce
    assert _normalize_isin("") is None
    assert _normalize_isin(None) is None
    assert _normalize_isin("ES123") is None    # demasiado corto
    assert _normalize_isin("0044580Y14XY") is None  # no empieza por 2 letras
    assert _normalize_isin(12345) is None      # no es str


# ---------------------------------------------------------------------------
#  Worker _fill_isins_worker (lógica síncrona, mockeando el proveedor)
# ---------------------------------------------------------------------------
#
# El endpoint real lanza este worker en un hilo en segundo plano (con su propia
# Session sobre la BD real). Por eso la lógica se prueba directamente sobre el
# worker con la sesión de test y un proveedor falso, y el endpoint se prueba
# aparte (lanza el job / 403 / 409).

import pytest

from app.api.admin import _fill_isins_worker
from app.models import Security
from sqlalchemy import select


def _crear_sec(client, name, ticker, isin=None):
    body = {"name": name, "yahoo_ticker": ticker, "market": "ibex35", "currency": "EUR"}
    if isin:
        body["isin"] = isin
    r = client.post("/api/securities", json=body)
    assert r.status_code == 201, r.text
    return r.json()["id"]


class _FakeProvider:
    """Proveedor falso: devuelve el ISIN del dict, o None si no está."""
    def __init__(self, mapping):
        self.mapping = mapping

    def fetch_isin(self, ticker):
        val = self.mapping.get(ticker, None)
        if isinstance(val, Exception):
            raise val
        return val


def test_worker_rellena_solo_los_vacios(admin_client, seed_markets, db):
    """Rellena solo los valores sin ISIN; los no resueltos van a not_found."""
    _crear_sec(admin_client, "Con ISIN", "SAN.MC", isin="ES0113900J37")
    _crear_sec(admin_client, "Sin ISIN A", "ITX.MC")
    _crear_sec(admin_client, "Sin ISIN B", "DESCONOCIDO.MC")

    provider = _FakeProvider({"ITX.MC": "ES0148396007", "DESCONOCIDO.MC": None})
    res = _fill_isins_worker(db, provider)

    assert res["checked"] == 2          # solo los dos sin ISIN
    assert res["updated"] == 1          # ITX resuelto
    assert res["not_found"] == ["DESCONOCIDO.MC"]
    # Persistido y sin tocar el que ya tenía ISIN
    db.expire_all()
    itx = db.scalar(select(Security).where(Security.yahoo_ticker == "ITX.MC"))
    san = db.scalar(select(Security).where(Security.yahoo_ticker == "SAN.MC"))
    assert itx.isin == "ES0148396007"
    assert san.isin == "ES0113900J37"


def test_worker_no_resobrescribe_segunda_pasada(admin_client, seed_markets, db):
    """Tras rellenar, el valor deja de estar pendiente en la siguiente pasada."""
    _crear_sec(admin_client, "Sin ISIN", "ITX.MC")
    _fill_isins_worker(db, _FakeProvider({"ITX.MC": "ES0148396007"}))
    # Segunda pasada: ya no hay pendientes (aunque el mock devolviera otro ISIN)
    res2 = _fill_isins_worker(db, _FakeProvider({"ITX.MC": "XX0000000000"}))
    assert res2["checked"] == 0
    assert res2["updated"] == 0
    db.expire_all()
    itx = db.scalar(select(Security).where(Security.yahoo_ticker == "ITX.MC"))
    assert itx.isin == "ES0148396007"   # intacto


def test_worker_commit_incremental_persiste_lo_hecho_ante_fallo(admin_client, seed_markets, db):
    """
    Si falla a mitad (p. ej. la red se cae en un valor), lo ya rellenado debe
    quedar PERSISTIDO gracias al commit incremental. Es justo lo que permite que
    el estado informe 'cuántos se rellenaron antes de fallar'.
    """
    _crear_sec(admin_client, "Primero", "ITX.MC")     # se rellena ok
    _crear_sec(admin_client, "Segundo", "BOOM.MC")    # revienta

    provider = _FakeProvider({"ITX.MC": "ES0148396007", "BOOM.MC": RuntimeError("red caída")})
    with pytest.raises(RuntimeError):
        _fill_isins_worker(db, provider)

    db.expire_all()
    itx = db.scalar(select(Security).where(Security.yahoo_ticker == "ITX.MC"))
    assert itx.isin == "ES0148396007"   # el primero quedó guardado pese al fallo del segundo


def test_progreso_se_reporta_por_item(admin_client, seed_markets, db):
    """El callback on_item se invoca tras cada valor con (checked, updated, not_found)."""
    _crear_sec(admin_client, "A", "ITX.MC")
    _crear_sec(admin_client, "B", "NOPE.MC")
    eventos = []
    _fill_isins_worker(
        db,
        _FakeProvider({"ITX.MC": "ES0148396007", "NOPE.MC": None}),
        on_item=lambda c, u, nf: eventos.append((c, u, list(nf))),
    )
    assert eventos[-1] == (2, 1, ["NOPE.MC"])


# ---------------------------------------------------------------------------
#  Endpoint POST /admin/securities/fill-isins (lanza el job en segundo plano)
# ---------------------------------------------------------------------------

def test_endpoint_lanza_job_y_expone_estado(admin_client, seed_markets, monkeypatch):
    """El endpoint responde 202 y el estado es consultable. El worker se mockea
    para no tocar la red ni la BD real desde el hilo."""
    monkeypatch.setattr(
        "app.api.admin._fill_isins_worker",
        lambda db, provider, on_item=None: {"checked": 0, "updated": 0, "not_found": []},
    )
    r = admin_client.post("/api/admin/securities/fill-isins")
    assert r.status_code == 202

    s = admin_client.get("/api/admin/securities/fill-isins/status")
    assert s.status_code == 200
    body = s.json()
    assert "running" in body and "updated" in body and "not_found" in body


def test_fill_isins_no_admin(auth_client, seed_markets):
    assert auth_client.post("/api/admin/securities/fill-isins").status_code == 403
    assert auth_client.get("/api/admin/securities/fill-isins/status").status_code == 403
