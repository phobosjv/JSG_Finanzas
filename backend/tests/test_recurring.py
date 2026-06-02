"""
test_recurring.py
=================
Tests de las aportaciones periódicas (DCA, v1.7.3).

Cubre:
  * Generador puro de fechas: frecuencias y recorte de día de mes.
  * Endpoint POST /portfolio/{id}/recurring-buys: precio histórico por fecha
    (día hábil anterior), participaciones = importe/precio, omisión de fechas
    futuras o sin precio, y uso del tipo de cambio para valores en USD.
"""

from datetime import date
from decimal import Decimal as D

import pytest
from sqlalchemy.orm import Session

from app.models import EcbRate, PriceHistory, RecurringPlanRow
from app.scheduler.jobs import execute_due_recurring_plans
from app.services.recurring import (
    contribution_dates_until, generate_contribution_dates, nth_contribution_date,
)


# ---------------------------------------------------------------------------
#  Generador puro de fechas
# ---------------------------------------------------------------------------

def test_monthly_dates_basicas():
    fechas = generate_contribution_dates(date(2024, 1, 15), "monthly", 3)
    assert fechas == [date(2024, 1, 15), date(2024, 2, 15), date(2024, 3, 15)]


def test_monthly_recorta_dia_de_mes():
    """31 de enero + 1 mes → 29 de febrero (2024 bisiesto), no error."""
    fechas = generate_contribution_dates(date(2024, 1, 31), "monthly", 3)
    assert fechas == [date(2024, 1, 31), date(2024, 2, 29), date(2024, 3, 31)]


def test_weekly_quarterly_yearly():
    assert generate_contribution_dates(date(2024, 1, 1), "weekly", 2) == [
        date(2024, 1, 1), date(2024, 1, 8),
    ]
    assert generate_contribution_dates(date(2024, 1, 1), "quarterly", 2) == [
        date(2024, 1, 1), date(2024, 4, 1),
    ]
    assert generate_contribution_dates(date(2024, 1, 1), "yearly", 2) == [
        date(2024, 1, 1), date(2025, 1, 1),
    ]


def test_count_invalido():
    with pytest.raises(ValueError):
        generate_contribution_dates(date(2024, 1, 1), "monthly", 0)
    with pytest.raises(ValueError):
        generate_contribution_dates(date(2024, 1, 1), "monthly", 601)


def test_frecuencia_invalida():
    with pytest.raises(ValueError):
        generate_contribution_dates(date(2024, 1, 1), "daily", 3)  # type: ignore[arg-type]


def test_contribution_dates_until_rango():
    """Las fechas se generan por rango inicio→fin (ambos incluidos)."""
    fechas = contribution_dates_until(date(2024, 1, 15), "monthly", date(2024, 3, 15))
    assert fechas == [date(2024, 1, 15), date(2024, 2, 15), date(2024, 3, 15)]
    # El fin no cae justo en una fecha: se incluye hasta la última <= fin.
    fechas = contribution_dates_until(date(2024, 1, 15), "monthly", date(2024, 3, 10))
    assert fechas == [date(2024, 1, 15), date(2024, 2, 15)]


def test_contribution_dates_until_fin_anterior():
    with pytest.raises(ValueError):
        contribution_dates_until(date(2024, 3, 1), "monthly", date(2024, 1, 1))


# ---------------------------------------------------------------------------
#  Endpoint POST /portfolio/{id}/recurring-buys
# ---------------------------------------------------------------------------

def _seed_prices(engine, security_id, pairs):
    """Inserta filas price_history (lista de (fecha, close))."""
    with Session(engine) as s:
        for d, close in pairs:
            s.add(PriceHistory(security_id=security_id, date=d, close=D(close)))
        s.commit()


def _crear_sec_pos(admin_client, market="ibex35", currency="EUR"):
    sec = admin_client.post("/api/securities", json={
        "name": "Valor DCA", "yahoo_ticker": "DCA.MC", "market": market, "currency": currency,
    }).json()["id"]
    pos = admin_client.post("/api/portfolio/positions", json={"security_id": sec}).json()["id"]
    return sec, pos


def test_aportaciones_crean_compras_con_precio_historico(admin_client, seed_markets, engine):
    """3 aportaciones mensuales de 100€: participaciones = 100/precio de cada fecha."""
    sec, pos = _crear_sec_pos(admin_client)
    _seed_prices(engine, sec, [
        ("2024-01-15", "10"),   # 100/10 = 10 part.
        ("2024-02-15", "20"),   # 100/20 = 5 part.
        ("2024-03-15", "25"),   # 100/25 = 4 part.
    ])
    resp = admin_client.post(f"/api/portfolio/{pos}/recurring-buys", json={
        "amount_per_period": "100", "fee_per_period": "0",
        "frequency": "monthly", "start_date": "2024-01-15", "end_date": "2024-03-15",
    })
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["created"] == 3
    assert data["skipped"] == []
    assert float(data["total_invested_native"]) == 300.0
    assert float(data["total_shares"]) == 19.0   # 10 + 5 + 4

    # Se crearon 3 compras reales en la posición.
    txs = admin_client.get(f"/api/portfolio/{pos}/transactions").json()
    buys = [t for t in txs if t["type"] == "buy"]
    assert len(buys) == 3


def test_aportacion_usa_dia_habil_anterior(admin_client, seed_markets, engine):
    """Si la fecha de aportación no cotiza, usa el precio del día hábil anterior."""
    sec, pos = _crear_sec_pos(admin_client)
    # Solo hay precio el viernes 12; la aportación es el lunes 15.
    _seed_prices(engine, sec, [("2024-01-12", "10")])
    resp = admin_client.post(f"/api/portfolio/{pos}/recurring-buys", json={
        "amount_per_period": "100", "frequency": "monthly",
        "start_date": "2024-01-15", "end_date": "2024-01-15",
    })
    data = resp.json()
    assert data["created"] == 1
    assert float(data["total_shares"]) == 10.0   # 100 / 10 (precio del 12)


def test_aportacion_sin_precio_se_omite(admin_client, seed_markets, engine):
    """Una fecha sin ningún precio histórico anterior se omite con motivo."""
    sec, pos = _crear_sec_pos(admin_client)
    _seed_prices(engine, sec, [("2024-03-15", "25")])  # solo marzo
    resp = admin_client.post(f"/api/portfolio/{pos}/recurring-buys", json={
        "amount_per_period": "100", "frequency": "monthly",
        "start_date": "2024-01-15", "end_date": "2024-03-15",
    })
    data = resp.json()
    assert data["created"] == 1                 # solo la de marzo
    assert len(data["skipped"]) == 2            # enero y febrero sin precio
    assert all("precio" in s["reason"] for s in data["skipped"])


def test_aportacion_futura_crea_plan_no_compras(admin_client, seed_markets, engine):
    """
    Las fechas futuras NO se crean como compras (no hay cotización): se guardan
    como un plan que el scheduler ejecutará. El caso que reportó el usuario.
    """
    sec, pos = _crear_sec_pos(admin_client)
    resp = admin_client.post(f"/api/portfolio/{pos}/recurring-buys", json={
        "amount_per_period": "200", "frequency": "monthly",
        "start_date": "2099-01-01", "end_date": "2099-03-01",
    })
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["created"] == 0          # nada se crea por adelantado
    assert data["skipped"] == []
    assert data["plan"] is not None
    assert data["plan"]["remaining"] == 3
    assert data["plan"]["next_date"] == "2099-01-01"
    assert float(data["plan"]["amount_per_period"]) == 200.0

    # No se ha creado ninguna compra todavía.
    txs = admin_client.get(f"/api/portfolio/{pos}/transactions").json()
    assert [t for t in txs if t["type"] == "buy"] == []

    # El plan aparece en la lista de planes activos.
    plans = admin_client.get("/api/portfolio/recurring-plans").json()
    assert len(plans) == 1
    assert plans[0]["security_id"] == sec


def test_scheduler_ejecuta_plan_vencido(admin_client, seed_markets, engine):
    """El scheduler crea las compras de un plan cuando llegan sus fechas."""
    from sqlalchemy.orm import Session
    sec, pos = _crear_sec_pos(admin_client)
    # Plan futuro de 2 aportaciones mensuales de 100€.
    admin_client.post(f"/api/portfolio/{pos}/recurring-buys", json={
        "amount_per_period": "100", "frequency": "monthly",
        "start_date": "2099-01-01", "end_date": "2099-02-01",
    })
    _seed_prices(engine, sec, [("2099-01-01", "10"), ("2099-02-01", "20")])

    # Ejecutar con 'hoy' = 2099-02-01: las dos aportaciones están vencidas.
    with Session(engine) as s:
        created = execute_due_recurring_plans(s, today=date(2099, 2, 1))
    assert created == 2

    txs = admin_client.get(f"/api/portfolio/{pos}/transactions").json()
    buys = sorted([t for t in txs if t["type"] == "buy"], key=lambda t: t["date"])
    assert len(buys) == 2
    assert float(buys[0]["shares"]) == 10.0   # 100/10
    assert float(buys[1]["shares"]) == 5.0    # 100/20

    # Plan completado → ya no figura como activo.
    assert admin_client.get("/api/portfolio/recurring-plans").json() == []


def test_scheduler_no_ejecuta_aportaciones_no_vencidas(admin_client, seed_markets, engine):
    """Solo se ejecutan las aportaciones cuya fecha ya llegó (<= hoy)."""
    from sqlalchemy.orm import Session
    sec, pos = _crear_sec_pos(admin_client)
    admin_client.post(f"/api/portfolio/{pos}/recurring-buys", json={
        "amount_per_period": "100", "frequency": "monthly",
        "start_date": "2099-01-01", "end_date": "2099-03-01",
    })
    _seed_prices(engine, sec, [("2099-01-01", "10"), ("2099-02-01", "20")])

    # 'hoy' = 2099-01-15: solo la primera (01-01) está vencida.
    with Session(engine) as s:
        created = execute_due_recurring_plans(s, today=date(2099, 1, 15))
    assert created == 1

    plans = admin_client.get("/api/portfolio/recurring-plans").json()
    assert len(plans) == 1
    assert plans[0]["remaining"] == 2            # quedan 2 por ejecutar
    assert plans[0]["next_date"] == "2099-02-01"


def test_cancelar_plan(admin_client, seed_markets, engine):
    """Cancelar un plan lo elimina sin tocar las compras ya creadas."""
    sec, pos = _crear_sec_pos(admin_client)
    admin_client.post(f"/api/portfolio/{pos}/recurring-buys", json={
        "amount_per_period": "100", "frequency": "monthly",
        "start_date": "2099-01-01", "end_date": "2099-03-01",
    })
    plans = admin_client.get("/api/portfolio/recurring-plans").json()
    plan_id = plans[0]["id"]
    d = admin_client.delete(f"/api/portfolio/recurring-plans/{plan_id}")
    assert d.status_code == 204
    assert admin_client.get("/api/portfolio/recurring-plans").json() == []


def test_backfill_pasado_no_crea_plan(admin_client, seed_markets, engine):
    """Una serie totalmente pasada se registra como compras y NO deja plan."""
    sec, pos = _crear_sec_pos(admin_client)
    _seed_prices(engine, sec, [("2024-01-15", "10"), ("2024-02-15", "20")])
    resp = admin_client.post(f"/api/portfolio/{pos}/recurring-buys", json={
        "amount_per_period": "100", "frequency": "monthly",
        "start_date": "2024-01-15", "end_date": "2024-02-15",
    })
    data = resp.json()
    assert data["created"] == 2
    assert data["plan"] is None
    assert admin_client.get("/api/portfolio/recurring-plans").json() == []


def test_aportacion_usd_usa_tipo_de_cambio(admin_client, seed_markets, engine):
    """Para un valor en USD, las compras llevan el tipo BCE de la fecha."""
    sec, pos = _crear_sec_pos(admin_client, market="nasdaq", currency="USD")
    _seed_prices(engine, sec, [("2024-01-15", "50")])
    with Session(engine) as s:
        s.add(EcbRate(date="2024-01-10", rate=D("1.10")))
        s.commit()
    resp = admin_client.post(f"/api/portfolio/{pos}/recurring-buys", json={
        "amount_per_period": "100", "frequency": "monthly",
        "start_date": "2024-01-15", "end_date": "2024-01-15",
    })
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["created"] == 1
    txs = admin_client.get(f"/api/portfolio/{pos}/transactions").json()
    buy = [t for t in txs if t["type"] == "buy"][0]
    assert buy["currency"] == "USD"
    assert float(buy["exchange_rate"]) == 1.10
    assert float(buy["shares"]) == 2.0   # 100 / 50


def test_aportacion_importe_invalido(admin_client, seed_markets):
    """Importe <= 0 → 422 de validación."""
    sec, pos = _crear_sec_pos(admin_client)
    resp = admin_client.post(f"/api/portfolio/{pos}/recurring-buys", json={
        "amount_per_period": "0", "frequency": "monthly",
        "start_date": "2024-01-15", "end_date": "2024-03-15",
    })
    assert resp.status_code == 422
