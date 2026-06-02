"""
test_transfers.py
=================
Tests de los traspasos de fondos (v1.7.0).

Cubre:
  * Motor de cálculo: transfer_out consume sin ganancia; transfer_in hereda
    el coste; el reembolso final del destino aflora la plusvalía diferida.
  * Endpoint POST /portfolio/transfer: coste heredado, posición destino,
    validaciones (origen/destino no-fondo, mismo valor, sin participaciones).
  * Scheduler: refresco de fondos limitado a una vez por hora.
"""

from datetime import date, datetime
from decimal import Decimal as D

import pytest

from app.services.calculations import (
    Transaction, compute_position, consumed_cost_fifo,
)


# ---------------------------------------------------------------------------
#  Motor de cálculo
# ---------------------------------------------------------------------------

def _buy(d, shares, price, fee="0", rate="1"):
    return Transaction("buy", date.fromisoformat(d), D(shares), D(price), D(fee), D(rate))


def test_transfer_out_consume_sin_ganancia():
    """transfer_out reduce participaciones a 0 sin generar resultado fiscal."""
    txs = [
        _buy("2023-01-10", "100", "10"),                                    # coste 1000
        Transaction("transfer_out", date(2023, 6, 1), D("100"), D("10"), D("0"), D("1")),
    ]
    res = compute_position(txs, [])
    assert res.current_shares == D("0")
    assert res.realized_gain_eur == D("0")        # traspaso NO tributa
    assert len(res.sale_matches) == 0             # no entra en informe fiscal


def test_transfer_in_hereda_coste():
    """transfer_in crea un lote cuyo coste = precio sintético × participaciones."""
    # Coste heredado 1000 EUR repartido en 120 participaciones → precio 1000/120
    precio = D("1000") / D("120")
    txs = [Transaction("transfer_in", date(2023, 6, 1), D("120"), precio, D("0"), D("1"))]
    res = compute_position(txs, [])
    assert res.current_shares == D("120")
    # invested_eur ≈ 1000 (coste heredado conservado)
    assert abs(res.invested_eur - D("1000")) < D("0.0001")


def test_reembolso_final_aflora_plusvalia_diferida():
    """
    Traspaso A→B y reembolso de B: la ganancia fiscal se calcula sobre el
    COSTE HEREDADO del origen, no sobre el valor en el momento del traspaso.

    A: compra 100 @ 10 = 1000.  Traspaso (vale 1500) a B: 120 part @ 12.50.
    Coste heredado de B = 1000.  Reembolso de B a 1800 (120 @ 15).
    Ganancia fiscal esperada = 1800 - 1000 = 800.
    """
    _, inherited_eur = consumed_cost_fifo(
        compute_position([_buy("2023-01-10", "100", "10")], []).open_lots, D("100")
    )
    assert inherited_eur == D("1000")

    precio_sint = inherited_eur / D("120")
    txs_B = [
        Transaction("transfer_in", date(2023, 6, 1), D("120"), precio_sint, D("0"), D("1")),
        Transaction("sell", date(2024, 3, 1), D("120"), D("15"), D("0"), D("1")),
    ]
    res_B = compute_position(txs_B, [])
    assert abs(res_B.realized_gain_eur - D("800")) < D("0.0001")


def test_consumed_cost_fifo_insuficiente():
    """consumed_cost_fifo lanza ValueError si no hay participaciones suficientes."""
    lots = compute_position([_buy("2023-01-10", "50", "10")], []).open_lots
    with pytest.raises(ValueError):
        consumed_cost_fifo(lots, D("100"))


# ---------------------------------------------------------------------------
#  Endpoint POST /portfolio/transfer
# ---------------------------------------------------------------------------

def _crear_fondos(admin_client):
    """Crea dos mercados de fondos y un valor en cada uno. Devuelve (sec_a, sec_b)."""
    admin_client.post("/api/admin/markets", json={
        "code": "fondos_a", "name": "Fondos A", "currency": "EUR",
        "fiscal_window_days": 365, "is_fund_market": True,
    })
    admin_client.post("/api/admin/markets", json={
        "code": "fondos_b", "name": "Fondos B", "currency": "EUR",
        "fiscal_window_days": 365, "is_fund_market": True,
    })
    sec_a = admin_client.post("/api/securities", json={
        "name": "Fondo Origen", "isin": "ES0000000001", "yahoo_ticker": "0PORIGEN.F",
        "market": "fondos_a", "currency": "EUR",
    }).json()["id"]
    sec_b = admin_client.post("/api/securities", json={
        "name": "Fondo Destino", "isin": "ES0000000002", "yahoo_ticker": "0PDESTINO.F",
        "market": "fondos_b", "currency": "EUR",
    }).json()["id"]
    return sec_a, sec_b


def test_traspaso_crea_destino_y_hereda_coste(admin_client):
    """Un traspaso reduce el origen a 0, crea la posición destino y hereda el coste."""
    sec_a, sec_b = _crear_fondos(admin_client)
    pos_a = admin_client.post("/api/portfolio/positions", json={"security_id": sec_a}).json()["id"]
    # Compra en A: 100 @ 10 = 1000
    admin_client.post(f"/api/portfolio/{pos_a}/transactions", json={
        "type": "buy", "date": "2023-01-10", "shares": "100", "price": "10",
        "fee": "0", "currency": "EUR", "exchange_rate": "1",
    })

    # Traspaso: 100 part de A → 120 part de B
    resp = admin_client.post("/api/portfolio/transfer", json={
        "origin_position_id": pos_a,
        "shares": "100",
        "dest_security_id": sec_b,
        "dest_shares": "120",
        "date": "2023-06-01",
    })
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert float(data["inherited_cost_eur"]) == 1000.0

    # Origen a 0 participaciones (ya no aparece como abierto)
    open_pos = admin_client.get("/api/portfolio").json()
    a_open = [p for p in open_pos if p.get("security_id") == sec_a]
    assert a_open == [] or float(a_open[0]["shares"]) == 0

    # Destino con 120 participaciones y coste heredado ~1000
    b_open = [p for p in open_pos if p.get("security_id") == sec_b]
    assert len(b_open) == 1
    assert float(b_open[0]["shares"]) == 120.0
    assert abs(float(b_open[0]["cost_eur"]) - 1000.0) < 0.01


def test_traspaso_origen_no_fondo_falla(admin_client, seed_markets):
    """Si el origen no es un fondo, el traspaso se rechaza con 422."""
    # ibex35 (seed) no es fondo
    sec_accion = admin_client.post("/api/securities", json={
        "name": "Acc", "yahoo_ticker": "ACC.MC", "market": "ibex35", "currency": "EUR",
    }).json()["id"]
    pos = admin_client.post("/api/portfolio/positions", json={"security_id": sec_accion}).json()["id"]
    admin_client.post(f"/api/portfolio/{pos}/transactions", json={
        "type": "buy", "date": "2023-01-10", "shares": "10", "price": "5",
        "fee": "0", "currency": "EUR", "exchange_rate": "1",
    })
    _, sec_b = _crear_fondos(admin_client)
    resp = admin_client.post("/api/portfolio/transfer", json={
        "origin_position_id": pos, "shares": "10",
        "dest_security_id": sec_b, "dest_shares": "10", "date": "2023-06-01",
    })
    assert resp.status_code == 422


def test_traspaso_destino_no_fondo_falla(admin_client, seed_markets):
    """Si el destino no es un fondo, el traspaso se rechaza con 422."""
    sec_a, _ = _crear_fondos(admin_client)
    pos_a = admin_client.post("/api/portfolio/positions", json={"security_id": sec_a}).json()["id"]
    admin_client.post(f"/api/portfolio/{pos_a}/transactions", json={
        "type": "buy", "date": "2023-01-10", "shares": "100", "price": "10",
        "fee": "0", "currency": "EUR", "exchange_rate": "1",
    })
    sec_accion = admin_client.post("/api/securities", json={
        "name": "Acc2", "yahoo_ticker": "ACC2.MC", "market": "ibex35", "currency": "EUR",
    }).json()["id"]
    resp = admin_client.post("/api/portfolio/transfer", json={
        "origin_position_id": pos_a, "shares": "100",
        "dest_security_id": sec_accion, "dest_shares": "10", "date": "2023-06-01",
    })
    assert resp.status_code == 422


def test_traspaso_participaciones_insuficientes_falla(admin_client):
    """Traspasar más participaciones de las disponibles → 422."""
    sec_a, sec_b = _crear_fondos(admin_client)
    pos_a = admin_client.post("/api/portfolio/positions", json={"security_id": sec_a}).json()["id"]
    admin_client.post(f"/api/portfolio/{pos_a}/transactions", json={
        "type": "buy", "date": "2023-01-10", "shares": "50", "price": "10",
        "fee": "0", "currency": "EUR", "exchange_rate": "1",
    })
    resp = admin_client.post("/api/portfolio/transfer", json={
        "origin_position_id": pos_a, "shares": "100",   # solo hay 50
        "dest_security_id": sec_b, "dest_shares": "100", "date": "2023-06-01",
    })
    assert resp.status_code == 422


def test_fondo_traspasado_no_aparece_como_cerrado(admin_client):
    """
    Regresión: un fondo cuyas participaciones se traspasan ÍNTEGRAMENTE queda
    con 0 participaciones (is_closed=True) pero SIN sale_matches (el traspaso
    no genera resultado fiscal). No debe aparecer en /portfolio/closed como
    una posición cerrada fantasma con todo a cero: su valor se difirió al
    fondo de destino, no se realizó ninguna venta.
    """
    sec_a, sec_b = _crear_fondos(admin_client)
    pos_a = admin_client.post("/api/portfolio/positions", json={"security_id": sec_a}).json()["id"]
    admin_client.post(f"/api/portfolio/{pos_a}/transactions", json={
        "type": "buy", "date": "2023-01-10", "shares": "100", "price": "10",
        "fee": "0", "currency": "EUR", "exchange_rate": "1",
    })
    # Traspaso íntegro A → B: A queda a 0 participaciones.
    admin_client.post("/api/portfolio/transfer", json={
        "origin_position_id": pos_a, "shares": "100",
        "dest_security_id": sec_b, "dest_shares": "120", "date": "2023-06-01",
    })

    closed = admin_client.get("/api/portfolio/closed").json()
    # El fondo origen NO debe figurar como posición cerrada (no hubo reembolso).
    assert [c for c in closed if c["security_id"] == sec_a] == []


def test_traspaso_no_genera_resultado_fiscal(admin_client):
    """Un traspaso (sin reembolso posterior) no aporta ganancias al informe."""
    sec_a, sec_b = _crear_fondos(admin_client)
    pos_a = admin_client.post("/api/portfolio/positions", json={"security_id": sec_a}).json()["id"]
    admin_client.post(f"/api/portfolio/{pos_a}/transactions", json={
        "type": "buy", "date": "2023-01-10", "shares": "100", "price": "10",
        "fee": "0", "currency": "EUR", "exchange_rate": "1",
    })
    admin_client.post("/api/portfolio/transfer", json={
        "origin_position_id": pos_a, "shares": "100",
        "dest_security_id": sec_b, "dest_shares": "120", "date": "2023-06-01",
    })
    report = admin_client.get("/api/reports/tax/2023/summary").json()
    assert float(report["total_gains_eur"]) == 0.0
    assert float(report["net_capital_result_eur"]) == 0.0


# ---------------------------------------------------------------------------
#  Deshacer traspaso (DELETE /portfolio/transfer/{group_id})
# ---------------------------------------------------------------------------

def _traspaso_simple(admin_client):
    """Crea A (100 @ 10) y traspasa todo a B (120 part). Devuelve (sec_a, sec_b, pos_a, resp)."""
    sec_a, sec_b = _crear_fondos(admin_client)
    pos_a = admin_client.post("/api/portfolio/positions", json={"security_id": sec_a}).json()["id"]
    admin_client.post(f"/api/portfolio/{pos_a}/transactions", json={
        "type": "buy", "date": "2023-01-10", "shares": "100", "price": "10",
        "fee": "0", "currency": "EUR", "exchange_rate": "1",
    })
    resp = admin_client.post("/api/portfolio/transfer", json={
        "origin_position_id": pos_a, "shares": "100",
        "dest_security_id": sec_b, "dest_shares": "120", "date": "2023-06-01",
    })
    return sec_a, sec_b, pos_a, resp


def test_deshacer_traspaso_restaura_origen(admin_client):
    """Deshacer un traspaso borra ambas filas y devuelve el origen a su estado previo."""
    sec_a, sec_b, pos_a, resp = _traspaso_simple(admin_client)
    group_id = resp.json()["transfer_group_id"]

    d = admin_client.delete(f"/api/portfolio/transfer/{group_id}")
    assert d.status_code == 204, d.text

    # El origen vuelve a tener sus 100 participaciones (abierto de nuevo).
    open_pos = admin_client.get("/api/portfolio").json()
    a_open = [p for p in open_pos if p["security_id"] == sec_a]
    assert len(a_open) == 1
    assert float(a_open[0]["shares"]) == 100.0
    # El destino ya no tiene participaciones del traspaso deshecho.
    b_open = [p for p in open_pos if p["security_id"] == sec_b]
    assert b_open == [] or float(b_open[0]["shares"]) == 0

    # Las dos filas del traspaso ya no existen en el origen.
    txs_a = admin_client.get(f"/api/portfolio/{pos_a}/transactions").json()
    assert all(t["type"] not in ("transfer_in", "transfer_out") for t in txs_a)


def test_deshacer_traspaso_inexistente_404(admin_client):
    """Deshacer un group_id que no existe → 404."""
    resp = admin_client.delete("/api/portfolio/transfer/noexiste123")
    assert resp.status_code == 404


def test_deshacer_traspaso_con_reembolso_posterior_falla(admin_client):
    """
    Si el destino ya reembolsó las participaciones heredadas, deshacer el
    traspaso las dejaría sin respaldo → 422 (no se permite).
    """
    sec_a, sec_b, pos_a, resp = _traspaso_simple(admin_client)
    group_id = resp.json()["transfer_group_id"]
    dest_pos_id = resp.json()["dest_position_id"]

    # Reembolso (venta) en el destino de las 120 participaciones heredadas.
    admin_client.post(f"/api/portfolio/{dest_pos_id}/transactions", json={
        "type": "sell", "date": "2024-03-01", "shares": "120", "price": "15",
        "fee": "0", "currency": "EUR", "exchange_rate": "1",
    })

    d = admin_client.delete(f"/api/portfolio/transfer/{group_id}")
    assert d.status_code == 422


def test_editar_transaccion_traspaso_bloqueada(admin_client):
    """Una fila transfer_in/transfer_out no se edita por el CRUD genérico → 422."""
    sec_a, sec_b, pos_a, resp = _traspaso_simple(admin_client)
    out_id = resp.json()["transfer_out_id"]
    r = admin_client.patch(f"/api/portfolio/{pos_a}/transactions/{out_id}", json={
        "type": "buy", "date": "2023-06-01", "shares": "100", "price": "10",
        "fee": "0", "currency": "EUR", "exchange_rate": "1",
    })
    assert r.status_code == 422


def test_borrar_transaccion_traspaso_bloqueada(admin_client):
    """Una fila transfer_in/transfer_out no se borra suelta por el CRUD genérico → 422."""
    sec_a, sec_b, pos_a, resp = _traspaso_simple(admin_client)
    out_id = resp.json()["transfer_out_id"]
    r = admin_client.delete(f"/api/portfolio/{pos_a}/transactions/{out_id}")
    assert r.status_code == 422


# ---------------------------------------------------------------------------
#  Scheduler: refresco de fondos una vez por hora
# ---------------------------------------------------------------------------

def test_should_refresh_funds_live(db):
    """Los fondos solo se refrescan si cambia la hora de reloj."""
    from app.scheduler.jobs import (
        _should_refresh_funds_live, _mark_funds_refreshed,
    )
    now = datetime(2026, 6, 2, 15, 5, 0)
    # Sin marca previa → refrescar
    assert _should_refresh_funds_live(db, now) is True
    _mark_funds_refreshed(db, now)
    # Misma hora → no refrescar
    assert _should_refresh_funds_live(db, datetime(2026, 6, 2, 15, 40, 0)) is False
    # Hora siguiente → refrescar
    assert _should_refresh_funds_live(db, datetime(2026, 6, 2, 16, 1, 0)) is True
