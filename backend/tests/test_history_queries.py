"""
test_history_queries.py
=======================
El grafico de cartera no debe hacer N+1: el numero de consultas tiene que ser
CONSTANTE, no crecer con el numero de posiciones.

Contexto (2026-08): "Mi cartera" se volvio lenta. Medido sobre la BBDD real del
usuario (27 posiciones, 214.193 filas de price_history), una sola carga hacia
**413 consultas y 1.256 ms**. Tres causas, todas N+1:

  1. GET /history/coverage repetia entero el trabajo del grafico (regresion
     introducida en la v1.24.0 al anadir el aviso).
  2. 'pos.security' se resolvia en diferido: una consulta por posicion.
  3. Una consulta de transacciones (y otra de dividendos) por posicion.

Tras corregirlo: **29 consultas y 312 ms**, con serie y retornos por periodo
byte a byte identicos a los de antes.

Este test fija la propiedad estructural -consultas constantes- en vez de un
tiempo, que dependeria de la maquina.
"""

from decimal import Decimal as D

import pytest
from sqlalchemy import event
from sqlalchemy.orm import Session

from app.api.portfolio import _history_series, _history_candidates, _portfolio_flows
from app.models import PriceHistory


class _Contador:
    """Cuenta las consultas que se ejecutan sobre el engine."""
    def __init__(self, engine):
        self.engine, self.n = engine, 0
    def __enter__(self):
        event.listen(self.engine, "before_cursor_execute", self._inc)
        return self
    def _inc(self, *a, **k):
        self.n += 1
    def __exit__(self, *exc):
        event.remove(self.engine, "before_cursor_execute", self._inc)


def _crear_posicion(client, engine, ticker, dia="2024-01-10"):
    r = client.post("/api/securities", json={
        "name": f"Test {ticker}", "yahoo_ticker": ticker,
        "market": "ibex35", "currency": "EUR",
    })
    sec = r.json()["id"]
    pos = client.post("/api/portfolio/positions", json={"security_id": sec}).json()["id"]
    client.post(f"/api/portfolio/{pos}/transactions", json={
        "type": "buy", "date": dia, "shares": "10", "price": "100",
        "fee": "0", "currency": "EUR", "exchange_rate": "1",
    })
    with Session(engine) as s:
        s.add_all([
            PriceHistory(security_id=sec, date="2024-01-11", close=D("100")),
            PriceHistory(security_id=sec, date="2024-01-12", close=D("101")),
        ])
        s.commit()
    return pos


def _consultas_con(n, admin_client, engine, db, fn):
    for i in range(n):
        _crear_posicion(admin_client, engine, f"Q{n}X{i}.MC")
    db.expire_all()
    with _Contador(engine) as c:
        fn(db)
    return c.n


def test_history_series_no_escala_con_las_posiciones(admin_client, seed_markets, engine, db):
    """Doblar las posiciones no debe doblar las consultas."""
    q3 = _consultas_con(3, admin_client, engine, db, lambda d: _history_series(d, 1, None))
    q9 = _consultas_con(6, admin_client, engine, db, lambda d: _history_series(d, 1, None))
    # 3 -> 9 posiciones. Con N+1 las consultas se triplicarian; deben quedarse igual.
    assert q9 == q3, f"N+1 en _history_series: {q3} consultas con 3 posiciones, {q9} con 9"
    assert q9 <= 12, f"demasiadas consultas fijas: {q9}"


def test_portfolio_flows_no_escala_con_las_posiciones(admin_client, seed_markets, engine, db):
    q3 = _consultas_con(3, admin_client, engine, db, lambda d: _portfolio_flows(d, 1, None))
    q9 = _consultas_con(6, admin_client, engine, db, lambda d: _portfolio_flows(d, 1, None))
    assert q9 == q3, f"N+1 en _portfolio_flows: {q3} con 3 posiciones, {q9} con 9"
    assert q9 <= 8, f"demasiadas consultas fijas: {q9}"


def test_coverage_es_mas_barato_que_el_grafico(admin_client, seed_markets, engine, db):
    """El aviso NO debe repetir el trabajo del grafico (regresion de la v1.24.0).

    Solo necesita saber si existe una cotizacion posterior a la primera compra
    -una agregada-, no traerse las series enteras.
    """
    for i in range(6):
        _crear_posicion(admin_client, engine, f"COV{i}.MC")
    db.expire_all()

    with _Contador(engine) as c_graf:
        _history_series(db, 1, None)
    with _Contador(engine) as c_cov:
        admin_client.get("/api/portfolio/history/coverage")

    assert c_cov.n <= c_graf.n, (
        f"coverage ({c_cov.n} consultas) no debe costar mas que el grafico ({c_graf.n})"
    )


def test_candidates_una_sola_consulta_de_transacciones(admin_client, seed_markets, engine, db):
    """_history_candidates agrupa: posiciones + mercados + transacciones = 3."""
    for i in range(5):
        _crear_posicion(admin_client, engine, f"CAND{i}.MC")
    db.expire_all()
    with _Contador(engine) as c:
        cands = _history_candidates(db, 1, None)
    assert len(cands) == 5
    assert c.n <= 4, f"esperadas ~3 consultas (posiciones, mercados, transacciones), hubo {c.n}"
