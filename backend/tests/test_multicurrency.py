"""
test_multicurrency.py
=====================
Tests del soporte multi-divisa (v1.8.0): tipos del BCE por divisa, valoración en
euros usando el tipo de la divisa del valor, y validación de divisas soportadas.
"""

from datetime import date
from decimal import Decimal as D

from sqlalchemy.orm import Session

from app.models import EcbRate, PriceSnapshot
from app.providers.ecb import _parse_csv_multi


# ---------------------------------------------------------------------------
#  Parseo del CSV multi-divisa del BCE
# ---------------------------------------------------------------------------

def test_parse_csv_multi_divisas():
    csv = (
        "KEY,FREQ,CURRENCY,CURRENCY_DENOM,TIME_PERIOD,OBS_VALUE\n"
        "EXR.D.USD.EUR.SP00.A,D,USD,EUR,2024-01-10,1.1000\n"
        "EXR.D.GBP.EUR.SP00.A,D,GBP,EUR,2024-01-10,0.8600\n"
        "EXR.D.JPY.EUR.SP00.A,D,JPY,EUR,2024-01-10,160.50\n"
        "EXR.D.EUR.EUR.SP00.A,D,EUR,EUR,2024-01-10,1.0000\n"  # EUR base → se ignora
    )
    rates = _parse_csv_multi(csv)
    assert rates[("2024-01-10", "USD")] == D("1.1000")
    assert rates[("2024-01-10", "GBP")] == D("0.8600")
    assert rates[("2024-01-10", "JPY")] == D("160.50")
    assert ("2024-01-10", "EUR") not in rates


# ---------------------------------------------------------------------------
#  Divisa soportada: validación
# ---------------------------------------------------------------------------

def test_security_divisa_no_soportada_rechazada(admin_client, seed_markets):
    """Crear un valor en GBP sin haberla configurado como soportada → 422."""
    r = admin_client.post("/api/securities", json={
        "name": "Vodafone", "yahoo_ticker": "VOD.L", "market": "ibex35", "currency": "GBP",
    })
    assert r.status_code == 422


def test_configurar_divisa_y_crear_valor(admin_client, seed_markets):
    """Tras configurar GBP como soportada, se puede crear un valor en GBP."""
    admin_client.patch("/api/admin/config/currencies", json={"currencies": ["USD", "GBP"]})
    r = admin_client.post("/api/securities", json={
        "name": "Vodafone", "yahoo_ticker": "VOD.L", "market": "ibex35", "currency": "GBP",
    })
    assert r.status_code == 201, r.text
    assert r.json()["currency"] == "GBP"


# ---------------------------------------------------------------------------
#  Valoración en EUR con el tipo de la divisa del valor
# ---------------------------------------------------------------------------

def test_valoracion_usa_tipo_de_la_divisa(admin_client, seed_markets, engine):
    """
    Un valor en GBP se valora en EUR con el tipo GBP del BCE (no rate=1).
    10 part. × 6 GBP / 1.20 (GBP por EUR) = 50 €.
    """
    admin_client.patch("/api/admin/config/currencies", json={"currencies": ["USD", "GBP"]})
    sec = admin_client.post("/api/securities", json={
        "name": "GBP Co", "yahoo_ticker": "GBPCO.L", "market": "ibex35", "currency": "GBP",
    }).json()["id"]
    pos = admin_client.post("/api/portfolio/positions", json={"security_id": sec}).json()["id"]
    admin_client.post(f"/api/portfolio/{pos}/transactions", json={
        "type": "buy", "date": "2024-01-10", "shares": "10", "price": "5",
        "fee": "0", "currency": "GBP", "exchange_rate": "1.15",
    })

    with Session(engine) as s:
        s.add(EcbRate(date="2024-06-01", currency="GBP", rate=D("1.20")))
        s.add(PriceSnapshot(security_id=sec, last_price=D("6"), prev_close=D("6")))
        s.commit()

    pf = admin_client.get("/api/portfolio").json()
    p = next(x for x in pf if x["security_id"] == sec)
    # market_value_eur = 10 × 6 / 1.20 = 50
    assert abs(float(p["market_value_eur"]) - 50.0) < 0.01
    # invested_eur (coste) = 10×5/1.15 ≈ 43.48 → P/L latente ≈ 6.52
    assert abs(float(p["cost_eur"]) - (50.0 / 1.15)) < 0.01
    assert abs(float(p["unrealized_pnl_eur"]) - (50.0 - 50.0 / 1.15)) < 0.05


def test_exchange_rate_endpoint_por_divisa(admin_client, seed_markets, engine):
    """El endpoint de tipo de cambio devuelve el tipo de la divisa pedida (BCE)."""
    with Session(engine) as s:
        s.add(EcbRate(date="2024-01-09", currency="GBP", rate=D("0.86")))
        s.commit()
    r = admin_client.get("/api/markets/exchange-rate?date=2024-01-10&currency=GBP").json()
    assert r["source"] == "ecb"
    assert abs(float(r["rate"]) - 0.86) < 1e-9
