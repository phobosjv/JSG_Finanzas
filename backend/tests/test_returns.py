"""
test_returns.py
===============
Tests de la TIR/XIRR (rentabilidad anualizada ponderada por dinero, v1.8.4).
"""

from datetime import date
from decimal import Decimal as D

from sqlalchemy.orm import Session

from app.models import PriceHistory, PriceSnapshot
from app.services.returns import xirr, modified_dietz


# ---------------------------------------------------------------------------
#  XIRR (función pura)
# ---------------------------------------------------------------------------

def test_xirr_un_anio_10pct():
    # -1000 hoy, +1100 al cabo de 1 año → 10 %.
    cf = [(date(2024, 1, 1), -1000.0), (date(2025, 1, 1), 1100.0)]
    r = xirr(cf)
    assert abs(r - 0.10) < 0.005


def test_xirr_seis_meses_se_anualiza():
    # +1100 a los 6 meses sobre 1000 → (1.1)^2 - 1 ≈ 21 %.
    cf = [(date(2024, 1, 1), -1000.0), (date(2024, 7, 1), 1100.0)]
    r = xirr(cf)
    assert abs(r - 0.21) < 0.01


def test_xirr_aportaciones_periodicas():
    # Dos aportaciones de 1000 (ene y jul) y valor final 2100 a fin de año.
    cf = [
        (date(2024, 1, 1), -1000.0),
        (date(2024, 7, 1), -1000.0),
        (date(2025, 1, 1), 2100.0),
    ]
    r = xirr(cf)
    assert r is not None and 0.05 < r < 0.20   # positiva y razonable


def test_xirr_no_resoluble():
    assert xirr([]) is None
    assert xirr([(date(2024, 1, 1), -100.0)]) is None          # un solo flujo
    assert xirr([(date(2024, 1, 1), -100.0), (date(2024, 1, 1), 110.0)]) is None  # mismo día
    assert xirr([(date(2024, 1, 1), -100.0), (date(2025, 1, 1), -50.0)]) is None  # todo negativo


# ---------------------------------------------------------------------------
#  Endpoint /portfolio/xirr
# ---------------------------------------------------------------------------

def test_endpoint_xirr_cartera(admin_client, seed_markets, engine):
    sec = admin_client.post("/api/securities", json={
        "name": "Acc", "yahoo_ticker": "ACC.MC", "market": "ibex35", "currency": "EUR",
    }).json()["id"]
    pos = admin_client.post("/api/portfolio/positions", json={"security_id": sec}).json()["id"]
    # Compra de hace ~2 años: 100 @ 10 = 1000.
    admin_client.post(f"/api/portfolio/{pos}/transactions", json={
        "type": "buy", "date": "2024-06-01", "shares": "100", "price": "10",
        "fee": "0", "currency": "EUR", "exchange_rate": "1",
    })
    with Session(engine) as s:
        s.add(PriceSnapshot(security_id=sec, last_price=D("12"), prev_close=D("12")))
        s.commit()

    data = admin_client.get("/api/portfolio/xirr").json()
    # Invertido 1000, valor 1200 hoy → TIR positiva.
    assert data["xirr_pct"] is not None
    assert data["xirr_pct"] > 0
    assert abs(data["market_value_eur"] - 1200.0) < 0.01


def test_endpoint_xirr_sin_operaciones(admin_client, seed_markets):
    """Sin posiciones → TIR no resoluble (null)."""
    data = admin_client.get("/api/portfolio/xirr").json()
    assert data["xirr_pct"] is None


# ---------------------------------------------------------------------------
#  Modified Dietz (función pura)
# ---------------------------------------------------------------------------

def test_modified_dietz_sin_flujos():
    # 100 → 150 sin aportaciones → +50 %.
    r = modified_dietz(100.0, 150.0, [])
    assert abs(r - 0.50) < 1e-6


def test_modified_dietz_con_aportacion_intermedia():
    # 100 al inicio, aporta 50 a mitad de periodo (peso 0.5), valor final 165.
    # R = (165 - 100 - 50) / (100 + 0.5×50) = 15 / 125 = 0.12.
    r = modified_dietz(100.0, 165.0, [(0.5, 50.0)])
    assert abs(r - 0.12) < 1e-6


def test_modified_dietz_dividendo_es_rentabilidad():
    # 100 → 100 (precio plano) y un dividendo de 5 (retirada) → +5 %.
    r = modified_dietz(100.0, 100.0, [(0.5, -5.0)])
    assert r > 0


def test_modified_dietz_denominador_no_positivo():
    assert modified_dietz(0.0, 10.0, []) is None


def test_endpoint_period_returns(admin_client, seed_markets, engine):
    sec = admin_client.post("/api/securities", json={
        "name": "Acc", "yahoo_ticker": "ACC.MC", "market": "ibex35", "currency": "EUR",
    }).json()["id"]
    pos = admin_client.post("/api/portfolio/positions", json={"security_id": sec}).json()["id"]
    admin_client.post(f"/api/portfolio/{pos}/transactions", json={
        "type": "buy", "date": "2024-01-02", "shares": "100", "price": "10",
        "fee": "0", "currency": "EUR", "exchange_rate": "1",
    })
    # Histórico de precios: de 10 a 12 (la posición vale más).
    with Session(engine) as s:
        s.add_all([
            PriceHistory(security_id=sec, date="2024-01-02", close=D("10")),
            PriceHistory(security_id=sec, date="2025-06-01", close=D("11")),
            PriceHistory(security_id=sec, date=date.today().isoformat(), close=D("12")),
        ])
        s.commit()

    data = admin_client.get("/api/portfolio/period-returns").json()
    # 'total': de 1000 invertido a 1200 → +20 % aprox.
    assert data["total"] is not None
    assert abs(data["total"] - 20.0) < 1.0
