"""
test_history_coverage.py
========================
GET /api/portfolio/history/coverage — que le falta al grafico de evolucion
para ser fiable.

Contexto (incidente real, 2026-08): tras migrar la app a otro servidor, el
grafico salio con "errores y discrepancias grandes". Causa: el backup admin NO
exporta 'price_history' ni 'ecb_rates', asi que hasta que el job nocturno las
rellena el grafico se dibuja con datos incompletos. Y lo hacia EN SILENCIO: una
curva incompleta es indistinguible de una correcta.

Los dos modos de fallo son distintos:
  - Sin cotizaciones, la posicion NO se valora en cero: desaparece del total
    (el 'continue' de _history_inputs), asi que la curva queda POR DEBAJO.
  - Sin tipos del BCE, no se excluye nada, pero toda la serie se convierte con
    el tipo mas reciente en vez del de cada fecha.
"""

from datetime import date
from decimal import Decimal as D

from sqlalchemy.orm import Session

from app.models import EcbRate, PriceHistory


def _crear_security(client, ticker, market="ibex35", currency="EUR"):
    r = client.post("/api/securities", json={
        "name": f"Test {ticker}", "yahoo_ticker": ticker,
        "market": market, "currency": currency,
    })
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _posicion_con_compra(client, sec_id, d="2024-01-10", currency="EUR", rate="1"):
    r = client.post("/api/portfolio/positions", json={"security_id": sec_id})
    pos_id = r.json()["id"]
    r = client.post(f"/api/portfolio/{pos_id}/transactions", json={
        "type": "buy", "date": d, "shares": "10", "price": "100",
        "fee": "0", "currency": currency, "exchange_rate": rate,
    })
    assert r.status_code in (200, 201), r.text
    return pos_id


def test_coverage_ok_cuando_no_falta_nada(admin_client, seed_markets, engine):
    sec = _crear_security(admin_client, "OKI.MC")
    _posicion_con_compra(admin_client, sec)
    with Session(engine) as s:
        s.add(PriceHistory(security_id=sec, date="2024-01-11", close=D("100")))
        s.commit()

    data = admin_client.get("/api/portfolio/history/coverage").json()
    assert data["ok"] is True
    assert data["missing_history"] == []
    assert data["missing_rates"] == []


def test_coverage_detecta_posicion_sin_cotizaciones(admin_client, seed_markets, engine):
    """Una posicion sin price_history desaparece del grafico: hay que avisar."""
    con_precio = _crear_security(admin_client, "CONP.MC")
    sin_precio = _crear_security(admin_client, "SINP.MC")
    _posicion_con_compra(admin_client, con_precio)
    _posicion_con_compra(admin_client, sin_precio)
    with Session(engine) as s:
        s.add(PriceHistory(security_id=con_precio, date="2024-01-11", close=D("100")))
        s.commit()

    data = admin_client.get("/api/portfolio/history/coverage").json()
    assert data["ok"] is False
    tickers = [m["ticker"] for m in data["missing_history"]]
    assert tickers == ["SINP.MC"], "solo la que no tiene cotizaciones"
    assert data["missing_history"][0]["since"] == "2024-01-10"
    assert data["missing_history"][0]["name"] == "Test SINP.MC"

    # Y el grafico, efectivamente, la ha dejado fuera: la curva vale solo lo del
    # otro valor (10 x 100 = 1000), no los 2000 que suman las dos posiciones.
    serie = admin_client.get("/api/portfolio/history").json()
    assert serie and serie[-1]["value"] == 1000.0


def test_coverage_detecta_divisa_sin_tipos_del_bce(admin_client, seed_markets, engine):
    """Un valor en USD sin ecb_rates deforma la serie: hay que avisar."""
    sec = _crear_security(admin_client, "USDX", market="nasdaq", currency="USD")
    _posicion_con_compra(admin_client, sec, currency="USD", rate="1.10")
    with Session(engine) as s:
        s.add(PriceHistory(security_id=sec, date="2024-01-11", close=D("100")))
        s.commit()

    data = admin_client.get("/api/portfolio/history/coverage").json()
    assert data["missing_rates"] == ["USD"]
    assert data["ok"] is False

    # Con tipos cargados deja de avisar.
    with Session(engine) as s:
        s.add(EcbRate(date="2024-01-11", currency="USD", rate=D("1.09")))
        s.commit()
    data2 = admin_client.get("/api/portfolio/history/coverage").json()
    assert data2["missing_rates"] == []
    assert data2["ok"] is True


def test_coverage_ignora_posiciones_sin_transacciones(admin_client, seed_markets):
    """Una posicion vacia no es un dato de mercado que falte: no se reporta."""
    sec = _crear_security(admin_client, "VACIA.MC")
    admin_client.post("/api/portfolio/positions", json={"security_id": sec})

    data = admin_client.get("/api/portfolio/history/coverage").json()
    assert data["missing_history"] == []
    assert data["ok"] is True


def test_coverage_respeta_el_filtro_de_posiciones(admin_client, seed_markets, engine):
    """El aviso debe referirse a lo que el usuario esta viendo, no a toda la cartera."""
    a = _crear_security(admin_client, "AAA.MC")
    b = _crear_security(admin_client, "BBB.MC")
    pos_a = _posicion_con_compra(admin_client, a)
    _posicion_con_compra(admin_client, b)          # esta es la que no tiene precios
    with Session(engine) as s:
        s.add(PriceHistory(security_id=a, date="2024-01-11", close=D("100")))
        s.commit()

    # Mirando solo la posicion A (que si tiene precios) no debe avisar de B.
    data = admin_client.get(f"/api/portfolio/history/coverage?position_ids={pos_a}").json()
    assert data["missing_history"] == []
    assert data["ok"] is True


def test_coverage_requiere_autenticacion(client):
    assert client.get("/api/portfolio/history/coverage").status_code == 401
