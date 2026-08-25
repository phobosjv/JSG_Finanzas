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


# ---------------------------------------------------------------------------
#  Cobertura PARCIAL: el hueco que el aviso no veia (v1.24.2)
# ---------------------------------------------------------------------------
#
# El criterio original era "existe alguna cotizacion posterior a la primera
# compra". Con compra en 2022 y cotizaciones desde 2026 la respuesta es SI, asi
# que la posicion no se marcaba: entraba en el grafico aportando valor solo desde
# 2026, y el tramo 2022-2025 quedaba hundido SIN NINGUN AVISO. Es exactamente lo
# que deja una migracion de servidor, y el boton de forzar historico en modo
# incremental no lo repara (arranca en la ultima fecha guardada, nunca rellena
# hacia atras): para eso existe full=true.

def test_coverage_detecta_historico_truncado(admin_client, seed_markets, engine):
    sec = _crear_security(admin_client, "TRUNC.MC")
    _posicion_con_compra(admin_client, sec, d="2022-03-01")
    with Session(engine) as s:
        # Cotizaciones que empiezan MUCHO despues de la compra.
        s.add_all([
            PriceHistory(security_id=sec, date="2026-06-01", close=D("100")),
            PriceHistory(security_id=sec, date="2026-06-02", close=D("101")),
        ])
        s.commit()

    data = admin_client.get("/api/portfolio/history/coverage").json()
    assert data["ok"] is False
    assert data["missing_history"] == [], "hay cotizaciones: no es una exclusion total"
    assert len(data["partial_history"]) == 1
    p = data["partial_history"][0]
    assert p["ticker"] == "TRUNC.MC"
    assert p["since"] == "2022-03-01"      # primera compra
    assert p["from"] == "2026-06-01"       # primera cotizacion disponible


def test_coverage_no_marca_parcial_si_cubre_desde_la_compra(admin_client, seed_markets, engine):
    """Cotizaciones desde antes (o el mismo dia) de la compra: cobertura completa."""
    sec = _crear_security(admin_client, "OKFULL.MC")
    _posicion_con_compra(admin_client, sec, d="2024-01-10")
    with Session(engine) as s:
        s.add_all([
            PriceHistory(security_id=sec, date="2024-01-09", close=D("99")),
            PriceHistory(security_id=sec, date="2024-01-11", close=D("100")),
        ])
        s.commit()

    data = admin_client.get("/api/portfolio/history/coverage").json()
    assert data["partial_history"] == []
    assert data["ok"] is True


def test_truncado_y_ausente_se_distinguen(admin_client, seed_markets, engine):
    """Son dos problemas distintos y se reportan por separado."""
    trunc = _crear_security(admin_client, "PARC.MC")
    vacio = _crear_security(admin_client, "NADA.MC")
    _posicion_con_compra(admin_client, trunc, d="2022-01-05")
    _posicion_con_compra(admin_client, vacio, d="2022-01-05")
    with Session(engine) as s:
        s.add(PriceHistory(security_id=trunc, date="2026-01-05", close=D("50")))
        s.commit()

    data = admin_client.get("/api/portfolio/history/coverage").json()
    assert [m["ticker"] for m in data["missing_history"]] == ["NADA.MC"]
    assert [m["ticker"] for m in data["partial_history"]] == ["PARC.MC"]


def test_tolerancia_de_calendario_no_marca_huecos_normales(admin_client, seed_markets, engine):
    """Un desfase de pocos dias es ruido de calendario, no un historico truncado.

    Compras el viernes y la siguiente sesion es el lunes; o el historico se
    descargo un dia despues. Marcar eso convertiria el aviso en ruido constante
    y dejaria de leerse, que es peor que no tenerlo.
    """
    sec = _crear_security(admin_client, "FINDE.MC")
    _posicion_con_compra(admin_client, sec, d="2024-01-10")
    with Session(engine) as s:
        # 6 dias despues: dentro de la tolerancia (7).
        s.add(PriceHistory(security_id=sec, date="2024-01-16", close=D("100")))
        s.commit()
    data = admin_client.get("/api/portfolio/history/coverage").json()
    assert data["partial_history"] == []


def test_hueco_mayor_que_la_tolerancia_si_se_marca(admin_client, seed_markets, engine):
    sec = _crear_security(admin_client, "HUECO.MC")
    _posicion_con_compra(admin_client, sec, d="2024-01-10")
    with Session(engine) as s:
        # 21 dias: ya no es calendario, es un hueco real.
        s.add(PriceHistory(security_id=sec, date="2024-01-31", close=D("100")))
        s.commit()
    data = admin_client.get("/api/portfolio/history/coverage").json()
    assert [p["ticker"] for p in data["partial_history"]] == ["HUECO.MC"]
