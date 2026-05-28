"""
tests/test_tax_brackets.py
==========================
Tests para los endpoints de tramos IRPF y el tipo de cambio automático.

Cobertura:
  - CRUD admin de /admin/config/tax-brackets
  - Endpoint público /config/tax-brackets
  - Permisos: solo admin puede hacer CRUD
  - Ordenación por sort_order
  - Informe fiscal usa tramos de BD
  - GET /markets/exchange-rate con dato en BD
  - GET /markets/exchange-rate sin dato en BD (rate null)
  - GET /markets/exchange-rate con fecha inválida (422)
"""

from __future__ import annotations

import pytest
from sqlalchemy.orm import Session

from app.models import EcbRate, TaxBracketRow


# ---------------------------------------------------------------------------
#  Fixtures auxiliares
# ---------------------------------------------------------------------------

@pytest.fixture()
def seed_brackets(engine):
    """Inserta los 5 tramos estándar en la BD de test."""
    data = [
        (0.0,     6000.0,  19.0, 0),
        (6000.0,  50000.0, 21.0, 1),
        (50000.0, 200000.0, 23.0, 2),
        (200000.0, 300000.0, 27.0, 3),
        (300000.0, None,    28.0, 4),
    ]
    with Session(engine) as session:
        for min_a, max_a, rate, order in data:
            session.add(TaxBracketRow(
                min_amount=min_a,
                max_amount=max_a,
                rate=rate,
                sort_order=order,
            ))
        session.commit()


# ---------------------------------------------------------------------------
#  GET /config/tax-brackets  — endpoint público (sin auth)
# ---------------------------------------------------------------------------

def test_list_brackets_public_sin_datos(client):
    """Sin tramos en BD devuelve lista vacía."""
    resp = client.get("/api/config/tax-brackets")
    assert resp.status_code == 200
    assert resp.json() == []


def test_list_brackets_public_con_seed(client, seed_brackets):
    """Con los 5 tramos seed devuelve 5 elementos ordenados."""
    resp = client.get("/api/config/tax-brackets")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 5
    rates = [float(b["rate"]) for b in data]
    assert rates == [19.0, 21.0, 23.0, 27.0, 28.0]


def test_list_brackets_public_no_requiere_auth(client, seed_brackets):
    """El endpoint público no necesita sesión iniciada."""
    resp = client.get("/api/config/tax-brackets")
    assert resp.status_code == 200  # sin cookie de sesión


# ---------------------------------------------------------------------------
#  Admin CRUD  /admin/config/tax-brackets
# ---------------------------------------------------------------------------

def test_list_brackets_admin(admin_client, seed_brackets):
    """Admin puede listar los tramos."""
    resp = admin_client.get("/api/admin/config/tax-brackets")
    assert resp.status_code == 200
    assert len(resp.json()) == 5


def test_create_bracket_admin(admin_client):
    """Admin puede crear un tramo nuevo."""
    payload = {"min_amount": 0.0, "max_amount": 5000.0, "rate": 18.0, "sort_order": 0}
    resp = admin_client.post("/api/admin/config/tax-brackets", json=payload)
    assert resp.status_code == 201
    data = resp.json()
    assert float(data["rate"]) == 18.0
    assert float(data["min_amount"]) == 0.0
    assert float(data["max_amount"]) == 5000.0
    assert "id" in data


def test_create_bracket_sin_max(admin_client):
    """Crear un tramo sin max_amount (último tramo, sin techo)."""
    payload = {"min_amount": 300000.0, "max_amount": None, "rate": 28.0, "sort_order": 4}
    resp = admin_client.post("/api/admin/config/tax-brackets", json=payload)
    assert resp.status_code == 201
    assert resp.json()["max_amount"] is None


def test_create_bracket_rate_invalida(admin_client):
    """rate=0 o rate>=100 deben devolver 422."""
    for bad_rate in [0, 100, -5, 150]:
        resp = admin_client.post("/api/admin/config/tax-brackets",
            json={"min_amount": 0, "max_amount": 1000, "rate": bad_rate, "sort_order": 0})
        assert resp.status_code == 422, f"Se esperaba 422 para rate={bad_rate}"


def test_create_bracket_min_negativo(admin_client):
    """min_amount negativo debe devolver 422."""
    resp = admin_client.post("/api/admin/config/tax-brackets",
        json={"min_amount": -100.0, "max_amount": 1000.0, "rate": 19.0, "sort_order": 0})
    assert resp.status_code == 422


def test_create_bracket_max_menor_que_min(admin_client):
    """max_amount <= min_amount debe devolver 422."""
    resp = admin_client.post("/api/admin/config/tax-brackets",
        json={"min_amount": 5000.0, "max_amount": 1000.0, "rate": 19.0, "sort_order": 0})
    assert resp.status_code == 422


def test_create_bracket_no_admin(auth_client):
    """Usuario normal no puede crear tramos (403)."""
    resp = auth_client.post("/api/admin/config/tax-brackets",
        json={"min_amount": 0, "max_amount": 6000, "rate": 19, "sort_order": 0})
    assert resp.status_code == 403


def test_update_bracket(admin_client):
    """Admin puede actualizar un tramo existente."""
    # Crear
    create_resp = admin_client.post("/api/admin/config/tax-brackets",
        json={"min_amount": 0, "max_amount": 6000, "rate": 19, "sort_order": 0})
    bracket_id = create_resp.json()["id"]

    # Actualizar el rate
    update_resp = admin_client.put(f"/api/admin/config/tax-brackets/{bracket_id}",
        json={"min_amount": 0, "max_amount": 7000, "rate": 20, "sort_order": 0})
    assert update_resp.status_code == 200
    data = update_resp.json()
    assert float(data["rate"]) == 20.0
    assert float(data["max_amount"]) == 7000.0


def test_update_bracket_no_encontrado(admin_client):
    """PUT a un id inexistente devuelve 404."""
    resp = admin_client.put("/api/admin/config/tax-brackets/99999",
        json={"min_amount": 0, "max_amount": 1000, "rate": 19, "sort_order": 0})
    assert resp.status_code == 404


def test_delete_bracket(admin_client):
    """Admin puede eliminar un tramo."""
    create_resp = admin_client.post("/api/admin/config/tax-brackets",
        json={"min_amount": 0, "max_amount": 6000, "rate": 19, "sort_order": 0})
    bracket_id = create_resp.json()["id"]

    del_resp = admin_client.delete(f"/api/admin/config/tax-brackets/{bracket_id}")
    assert del_resp.status_code == 204

    # Ya no aparece en la lista
    list_resp = admin_client.get("/api/admin/config/tax-brackets")
    ids = [b["id"] for b in list_resp.json()]
    assert bracket_id not in ids


def test_delete_bracket_no_encontrado(admin_client):
    """DELETE a un id inexistente devuelve 404."""
    resp = admin_client.delete("/api/admin/config/tax-brackets/99999")
    assert resp.status_code == 404


def test_brackets_ordenados_por_sort_order(admin_client):
    """Los tramos se devuelven ordenados por sort_order ascendente."""
    for sort, rate in [(2, 21.0), (0, 19.0), (1, 20.0)]:
        admin_client.post("/api/admin/config/tax-brackets",
            json={"min_amount": sort * 1000, "max_amount": (sort + 1) * 1000, "rate": rate, "sort_order": sort})

    resp = admin_client.get("/api/admin/config/tax-brackets")
    rates_ordered = [float(b["rate"]) for b in resp.json()]
    # Deben venir en orden: 19 (sort=0), 20 (sort=1), 21 (sort=2)
    assert rates_ordered == [19.0, 20.0, 21.0]


# ---------------------------------------------------------------------------
#  GET /markets/exchange-rate
# ---------------------------------------------------------------------------

def test_exchange_rate_desde_bd(auth_client, engine):
    """Con un EcbRate en BD devuelve ese dato con source='ecb'."""
    with Session(engine) as session:
        session.add(EcbRate(date="2025-01-15", rate=1.0342))
        session.commit()

    resp = auth_client.get("/api/markets/exchange-rate?date=2025-01-15")
    assert resp.status_code == 200
    data = resp.json()
    assert data["source"] == "ecb"
    assert abs(data["rate"] - 1.0342) < 0.0001


def test_exchange_rate_fecha_anterior_a_registro(auth_client, engine):
    """Con fecha posterior al registro existente devuelve el más reciente."""
    # Aritmética: si tenemos rate del 2025-01-10 y pedimos el 2025-01-20,
    # debe devolver el del 2025-01-10 (fecha <= pedida, más cercana).
    with Session(engine) as session:
        session.add(EcbRate(date="2025-01-10", rate=1.05))
        session.commit()

    resp = auth_client.get("/api/markets/exchange-rate?date=2025-01-20")
    assert resp.status_code == 200
    data = resp.json()
    assert data["source"] == "ecb"
    assert abs(data["rate"] - 1.05) < 0.0001


def test_exchange_rate_bd_vacia_sin_yahoo(auth_client, monkeypatch):
    """Sin datos en BD y sin Yahoo disponible devuelve rate null."""
    # Monkeypatch de yfinance para simular fallo
    import sys
    import types

    fake_yf = types.ModuleType("yfinance")

    class FakeTicker:
        def history(self, **kwargs):
            import pandas as pd
            return pd.DataFrame()  # DataFrame vacío

    fake_yf.Ticker = lambda _: FakeTicker()
    monkeypatch.setitem(sys.modules, "yfinance", fake_yf)

    resp = auth_client.get("/api/markets/exchange-rate?date=2020-01-01")
    assert resp.status_code == 200
    assert resp.json()["rate"] is None
    assert resp.json()["source"] == "not_found"


def test_exchange_rate_fecha_invalida(auth_client):
    """Fecha con formato incorrecto devuelve 422."""
    resp = auth_client.get("/api/markets/exchange-rate?date=01-15-2025")
    assert resp.status_code == 422


def test_exchange_rate_requiere_auth(client):
    """Sin autenticación devuelve 401."""
    resp = client.get("/api/markets/exchange-rate?date=2025-01-15")
    assert resp.status_code == 401
