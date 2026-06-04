"""
test_returns.py
===============
Tests de la TIR/XIRR (rentabilidad anualizada ponderada por dinero, v1.8.4).
"""

from datetime import date
from decimal import Decimal as D

from sqlalchemy.orm import Session

from app.models import EcbRate, PriceHistory, PriceSnapshot
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


def test_history_carry_forward_ultimas_fechas_desalineadas(admin_client, seed_markets, engine):
    """
    Regresión: dos valores con su ÚLTIMO precio en fechas distintas (típico de
    fondos vs. acciones). El último punto del histórico debe sumar AMBOS usando
    su último cierre conocido (carry-forward), no solo el que cotizó ese día.

    Antes, v_end solo incluía el valor con precio en la fecha máxima del eje, lo
    que infravaloraba la cartera y disparaba el retorno 'total' a negativo.

    A: 100 @ 10 (=1000), último precio HOY a 11 → 1100.
    B: 100 @ 10 (=1000), último precio en 2025-06-01 a 11 (sin precio hoy) → 1100.
    Valor real hoy = 2200, invertido 2000 → total ≈ +10 %.
    """
    hoy = date.today().isoformat()
    sec_a = admin_client.post("/api/securities", json={
        "name": "AccA", "yahoo_ticker": "ACCA.MC", "market": "ibex35", "currency": "EUR",
    }).json()["id"]
    sec_b = admin_client.post("/api/securities", json={
        "name": "AccB", "yahoo_ticker": "ACCB.MC", "market": "ibex35", "currency": "EUR",
    }).json()["id"]
    for sec in (sec_a, sec_b):
        pos = admin_client.post("/api/portfolio/positions", json={"security_id": sec}).json()["id"]
        admin_client.post(f"/api/portfolio/{pos}/transactions", json={
            "type": "buy", "date": "2024-01-02", "shares": "100", "price": "10",
            "fee": "0", "currency": "EUR", "exchange_rate": "1",
        })

    with Session(engine) as s:
        s.add_all([
            # A cotiza hasta HOY
            PriceHistory(security_id=sec_a, date="2024-01-02", close=D("10")),
            PriceHistory(security_id=sec_a, date=hoy, close=D("11")),
            # B deja de cotizar el 2025-06-01 (anterior a hoy)
            PriceHistory(security_id=sec_b, date="2024-01-02", close=D("10")),
            PriceHistory(security_id=sec_b, date="2025-06-01", close=D("11")),
        ])
        s.commit()

    # El último punto del histórico debe valer 2200 (A 1100 + B 1100 por carry-forward)
    hist = admin_client.get("/api/portfolio/history").json()
    assert abs(hist[-1]["value"] - 2200.0) < 0.01

    # Y el retorno total debe ser ~+10 %, no negativo
    data = admin_client.get("/api/portfolio/period-returns").json()
    assert data["total"] is not None
    assert abs(data["total"] - 10.0) < 1.0


def test_history_usa_fx_historico_por_fecha(admin_client, seed_markets, engine):
    """
    El histórico convierte cada cierre con el tipo de cambio de SU fecha, no con
    el actual. Valor en USD, precio plano (100 USD), pero el EUR/USD pasa de 1,0
    a 2,0: el valor en EUR debe caer de 100 € a 50 € entre ambas fechas.
    """
    admin_client.patch("/api/admin/config/currencies", json={"currencies": ["EUR", "USD"]})
    sec = admin_client.post("/api/securities", json={
        "name": "UsdCo", "yahoo_ticker": "USD.OQ", "market": "nasdaq", "currency": "USD",
    }).json()["id"]
    pos = admin_client.post("/api/portfolio/positions", json={"security_id": sec}).json()["id"]
    admin_client.post(f"/api/portfolio/{pos}/transactions", json={
        "type": "buy", "date": "2024-01-02", "shares": "1", "price": "100",
        "fee": "0", "currency": "USD", "exchange_rate": "1.10",
    })
    hoy = date.today().isoformat()
    with Session(engine) as s:
        s.add_all([
            PriceHistory(security_id=sec, date="2024-01-02", close=D("100")),
            PriceHistory(security_id=sec, date=hoy, close=D("100")),
            EcbRate(date="2024-01-02", currency="USD", rate=D("1.0")),
            EcbRate(date=hoy, currency="USD", rate=D("2.0")),
        ])
        s.commit()

    hist = admin_client.get("/api/portfolio/history").json()
    by_date = {h["date"]: h["value"] for h in hist}
    # 2024-01-02: 100 USD / 1,0 = 100 € ; hoy: 100 USD / 2,0 = 50 €
    assert abs(by_date["2024-01-02"] - 100.0) < 0.01
    assert abs(by_date[hoy] - 50.0) < 0.01


def test_history_split_no_infla_valor_pre_split(admin_client, seed_markets, engine):
    """
    Regresión: _history_series aplicaba todos los splits futuros a las
    transacciones sin importar la fecha 'd' que se estaba procesando.
    Resultado: para fechas ANTERIORES al split, running_shares ya estaba
    multiplicado por el ratio pero last_close seguía siendo el precio
    pre-split (auto_adjust=False) → valor ×ratio, inflado.

    Escenario:
      Compra 100 acc × 100 € el 2024-01-02.
      Split 2:1 el 2024-04-01: precio pasa de 100 € a 50 €.
      Valor correcto en AMBAS fechas: 10.000 €.
      Valor BUGGY en 2024-01-02: 200 × 100 = 20.000 € (el doble).
    """
    sec = admin_client.post("/api/securities", json={
        "name": "SplitCo", "yahoo_ticker": "SPLIT.MC", "market": "ibex35", "currency": "EUR",
    }).json()["id"]
    pos = admin_client.post("/api/portfolio/positions", json={"security_id": sec}).json()["id"]
    admin_client.post(f"/api/portfolio/{pos}/transactions", json={
        "type": "buy", "date": "2024-01-02", "shares": "100", "price": "100",
        "fee": "0", "currency": "EUR", "exchange_rate": "1",
    })
    # Split 2:1 el 2024-04-01
    admin_client.post(f"/api/admin/securities/{sec}/splits", json={
        "ex_date": "2024-04-01", "ratio_num": 2, "ratio_den": 1,
    })
    with Session(engine) as s:
        s.add_all([
            PriceHistory(security_id=sec, date="2024-01-02", close=D("100")),  # pre-split
            PriceHistory(security_id=sec, date="2024-04-01", close=D("50")),   # post-split
        ])
        s.commit()

    hist = admin_client.get("/api/portfolio/history").json()
    by_date = {h["date"]: h["value"] for h in hist}

    # Pre-split: 100 acc × 100 € = 10.000 € (no 200 × 100 = 20.000)
    assert abs(by_date["2024-01-02"] - 10_000.0) < 0.01, (
        f"Bug splits: valor pre-split es {by_date['2024-01-02']}, esperado 10000"
    )
    # Post-split: 200 acc × 50 € = 10.000 €
    assert abs(by_date["2024-04-01"] - 10_000.0) < 0.01, (
        f"Bug splits: valor post-split es {by_date['2024-04-01']}, esperado 10000"
    )
