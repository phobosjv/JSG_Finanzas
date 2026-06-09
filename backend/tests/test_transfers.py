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


def test_summary_separa_acciones_y_fondos(admin_client, seed_markets):
    """
    El resumen JSON desglosa el resultado de ventas en acciones (net_sales_eur)
    y fondos (fund_net_eur), igual que el PDF. La suma es net_capital_result_eur.

    Acción: compra 10 @ 10 (coste 100) y vende a 15 (ingreso 150) → +50.
    Fondo:  compra 50 @ 10 (coste 500) y reembolsa a 13 (ingreso 650) → +150.
    """
    sec_a, _ = _crear_fondos(admin_client)

    # Acción IBEX (seed): compra y venta
    acc = admin_client.post("/api/securities", json={
        "name": "Iberdrola", "yahoo_ticker": "IBE.MC", "market": "ibex35", "currency": "EUR",
    }).json()["id"]
    pos_acc = admin_client.post("/api/portfolio/positions", json={"security_id": acc}).json()["id"]
    admin_client.post(f"/api/portfolio/{pos_acc}/transactions", json={
        "type": "buy", "date": "2023-02-01", "shares": "10", "price": "10",
        "fee": "0", "currency": "EUR", "exchange_rate": "1",
    })
    admin_client.post(f"/api/portfolio/{pos_acc}/transactions", json={
        "type": "sell", "date": "2023-09-01", "shares": "10", "price": "15",
        "fee": "0", "currency": "EUR", "exchange_rate": "1",
    })

    # Fondo: compra y reembolso (venta)
    pos_f = admin_client.post("/api/portfolio/positions", json={"security_id": sec_a}).json()["id"]
    admin_client.post(f"/api/portfolio/{pos_f}/transactions", json={
        "type": "buy", "date": "2023-02-01", "shares": "50", "price": "10",
        "fee": "0", "currency": "EUR", "exchange_rate": "1",
    })
    admin_client.post(f"/api/portfolio/{pos_f}/transactions", json={
        "type": "sell", "date": "2023-09-01", "shares": "50", "price": "13",
        "fee": "0", "currency": "EUR", "exchange_rate": "1",
    })

    r = admin_client.get("/api/reports/tax/2023/summary").json()
    assert float(r["net_sales_eur"]) == 50.0    # solo la acción
    assert float(r["fund_net_eur"]) == 150.0     # solo el fondo
    assert float(r["net_capital_result_eur"]) == 200.0  # suma


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


def test_rentabilidad_desde_traspaso(admin_client, engine):
    """
    transfer_in_market_eur = participaciones recibidas × NAV en la fecha del
    traspaso. Permite la rentabilidad "desde el traspaso" (propia del fondo).
    """
    from sqlalchemy.orm import Session
    from app.models import PriceHistory, PriceSnapshot
    from decimal import Decimal as D
    sec_a, sec_b = _crear_fondos(admin_client)
    pos_a = admin_client.post("/api/portfolio/positions", json={"security_id": sec_a}).json()["id"]
    admin_client.post(f"/api/portfolio/{pos_a}/transactions", json={
        "type": "buy", "date": "2023-01-10", "shares": "1", "price": "50",
        "fee": "0", "currency": "EUR", "exchange_rate": "1",
    })
    admin_client.post("/api/portfolio/transfer", json={
        "origin_position_id": pos_a, "shares": "1",
        "dest_security_id": sec_b, "dest_shares": "0.5", "date": "2023-06-01",
    })
    with Session(engine) as s:
        # NAV del destino el día del traspaso = 100 → valor traspasado 0,5×100 = 50.
        s.add(PriceHistory(security_id=sec_b, date="2023-06-01", close=D("100")))
        s.add(PriceSnapshot(security_id=sec_b, last_price=D("120"), prev_close=D("120")))
        s.commit()

    b = next(x for x in admin_client.get("/api/portfolio").json() if x["security_id"] == sec_b)
    assert abs(float(b["transfer_in_market_eur"]) - 50.0) < 0.01
    # Rentabilidad desde el traspaso = 120/100 - 1 = +20% (la calcula el front).


def test_fondo_destino_refleja_ganancia_o_perdida_heredada(admin_client, engine):
    """
    El destino de un traspaso muestra ganancia si el coste heredado < valor
    actual, y pérdida si es mayor. Verifica que un fondo SOLO con entradas por
    traspaso valora correctamente (coste heredado vs valor de mercado).
    """
    from sqlalchemy.orm import Session
    from app.models import PriceSnapshot
    from decimal import Decimal as D
    sec_a, sec_b = _crear_fondos(admin_client)
    pos_a = admin_client.post("/api/portfolio/positions", json={"security_id": sec_a}).json()["id"]
    # En A: compra 1 part. @ 50 (coste 50).
    admin_client.post(f"/api/portfolio/{pos_a}/transactions", json={
        "type": "buy", "date": "2023-01-10", "shares": "1", "price": "50",
        "fee": "0", "currency": "EUR", "exchange_rate": "1",
    })
    # Traspaso A→B: 1 part. de A → 0,5 part. de B (coste heredado 50).
    admin_client.post("/api/portfolio/transfer", json={
        "origin_position_id": pos_a, "shares": "1",
        "dest_security_id": sec_b, "dest_shares": "0.5", "date": "2023-06-01",
    })
    # B cotiza a 120 → valor 0,5×120 = 60; coste heredado 50 → ganancia +10.
    with Session(engine) as s:
        s.add(PriceSnapshot(security_id=sec_b, last_price=D("120"), prev_close=D("120")))
        s.commit()

    b = next(x for x in admin_client.get("/api/portfolio").json() if x["security_id"] == sec_b)
    assert abs(float(b["cost_eur"]) - 50.0) < 0.01
    assert abs(float(b["market_value_eur"]) - 60.0) < 0.01
    assert float(b["unrealized_pnl_eur"]) > 0   # gana: el coste heredado se respeta


def test_traspaso_origen_usd_hereda_coste_en_eur(admin_client):
    """
    Traspaso desde un fondo en USD a uno en EUR: el coste heredado debe venir en
    EUR (convertido con el tipo de la compra), no en USD sin convertir.
    Compra 1 part. @ 50 USD con tipo 1.10 → coste 45,4545 €.
    """
    admin_client.post("/api/admin/markets", json={
        "code": "fondos_usd", "name": "Fondos USD", "currency": "USD",
        "fiscal_window_days": 365, "market_type": "fund",
    })
    admin_client.post("/api/admin/markets", json={
        "code": "fondos_e", "name": "Fondos EUR", "currency": "EUR",
        "fiscal_window_days": 365, "market_type": "fund",
    })
    sec_usd = admin_client.post("/api/securities", json={
        "name": "Fondo USD", "yahoo_ticker": "0PUSD.F", "market": "fondos_usd", "currency": "USD",
    }).json()["id"]
    sec_eur = admin_client.post("/api/securities", json={
        "name": "Fondo EUR", "yahoo_ticker": "0PEUR.F", "market": "fondos_e", "currency": "EUR",
    }).json()["id"]
    pos_usd = admin_client.post("/api/portfolio/positions", json={"security_id": sec_usd}).json()["id"]
    admin_client.post(f"/api/portfolio/{pos_usd}/transactions", json={
        "type": "buy", "date": "2023-01-10", "shares": "1", "price": "50",
        "fee": "0", "currency": "USD", "exchange_rate": "1.10",
    })
    resp = admin_client.post("/api/portfolio/transfer", json={
        "origin_position_id": pos_usd, "shares": "1",
        "dest_security_id": sec_eur, "dest_shares": "0.5", "date": "2023-06-01",
    })
    assert resp.status_code == 201, resp.text
    # 50 USD / 1.10 = 45,4545 € (no 50 sin convertir).
    assert abs(float(resp.json()["inherited_cost_eur"]) - (50 / 1.10)) < 0.01


def test_operaciones_visibles_en_fondo_cerrado_por_traspaso(admin_client):
    """
    Un fondo traspasado al 100% queda cerrado y NO aparece en /portfolio/closed,
    pero su historial de operaciones debe seguir disponible (regresión v1.8.7).
    """
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

    # No figura como cerrada (cerrada por traspaso, sin sale_matches).
    closed = admin_client.get("/api/portfolio/closed").json()
    assert [c for c in closed if c["security_id"] == sec_a] == []

    # Pero sus operaciones (compra + transfer_out) siguen accesibles.
    ops = admin_client.get(f"/api/portfolio/by-security/{sec_a}/operations").json()
    assert ops["position_id"] == pos_a
    types = sorted(t["type"] for t in ops["transactions"])
    assert types == ["buy", "transfer_out"]


def test_operaciones_by_security_sin_posicion_404(admin_client, seed_markets):
    sec = admin_client.post("/api/securities", json={
        "name": "Sin pos", "yahoo_ticker": "NOPOS.MC", "market": "ibex35", "currency": "EUR",
    }).json()["id"]
    r = admin_client.get(f"/api/portfolio/by-security/{sec}/operations")
    assert r.status_code == 404


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
#  Fondo relacionado en tabla de operaciones (v1.9.11)
# ---------------------------------------------------------------------------

def test_operations_incluye_fondo_relacionado(admin_client):
    """
    GET /portfolio/by-security/{id}/operations debe devolver related_security_id
    y related_security_name para las filas de traspaso (transfer_in / transfer_out).

    Para la transfer_out de A → B:   related = B.
    Para la transfer_in  de B ← A:   related = A.
    """
    sec_a, sec_b, pos_a, resp = _traspaso_simple(admin_client)
    assert resp.status_code == 201, resp.text

    # Operaciones del fondo origen (A): la transfer_out debe referenciar a B.
    # (La posición A está cerrada tras el traspaso total, pero operations la devuelve.)
    ops_a = admin_client.get(f"/api/portfolio/by-security/{sec_a}/operations").json()
    out_tx = next(t for t in ops_a["transactions"] if t["type"] == "transfer_out")
    assert out_tx["related_security_id"] == sec_b, (
        f"transfer_out de A debe apuntar a sec_b={sec_b}, got {out_tx['related_security_id']}"
    )
    assert out_tx["related_security_name"] is not None

    # Operaciones del fondo destino (B): la transfer_in debe referenciar a A.
    ops_b = admin_client.get(f"/api/portfolio/by-security/{sec_b}/operations").json()
    in_tx = next(t for t in ops_b["transactions"] if t["type"] == "transfer_in")
    assert in_tx["related_security_id"] == sec_a, (
        f"transfer_in de B debe apuntar a sec_a={sec_a}, got {in_tx['related_security_id']}"
    )
    assert in_tx["related_security_name"] is not None


def test_operations_sin_traspaso_sin_related(admin_client, seed_markets):
    """Las compras/ventas normales no tienen related_security_id."""
    sec = admin_client.post("/api/securities", json={
        "name": "NormalSec", "yahoo_ticker": "NRM.MC", "market": "ibex35", "currency": "EUR",
    }).json()["id"]
    pos = admin_client.post("/api/portfolio/positions", json={"security_id": sec}).json()["id"]
    admin_client.post(f"/api/portfolio/{pos}/transactions", json={
        "type": "buy", "date": "2024-01-02", "shares": "10", "price": "5",
        "fee": "0", "currency": "EUR", "exchange_rate": "1",
    })
    ops = admin_client.get(f"/api/portfolio/by-security/{sec}/operations").json()
    buy_tx = ops["transactions"][0]
    assert buy_tx["related_security_id"] is None
    assert buy_tx["related_security_name"] is None


# ---------------------------------------------------------------------------
#  Fuente ÚNICA del objetivo de compra: favorites (no la posición) — v1.10.6
#
#  Regresión: en v1.9.11 se añadió un target_buy_price duplicado en positions
#  (endpoint PATCH /portfolio/{id}/target-buy). En v1.9.14 la fuente real pasó
#  a ser favorites y aquel quedó muerto; se eliminó en v1.10.6. Estos tests
#  evitan reintroducir el campo/endpoint dual y fijan favorites como fuente.
# ---------------------------------------------------------------------------

def test_no_existe_endpoint_target_buy_en_posicion(admin_client, seed_markets):
    """El endpoint zombie PATCH /portfolio/{id}/target-buy ya no debe existir."""
    sec = admin_client.post("/api/securities", json={
        "name": "TargetCo", "yahoo_ticker": "TGT.MC", "market": "ibex35", "currency": "EUR",
    }).json()["id"]
    pos = admin_client.post("/api/portfolio/positions", json={"security_id": sec}).json()["id"]
    r = admin_client.patch(f"/api/portfolio/{pos}/target-buy", json={"target_buy_price": "12.50"})
    assert r.status_code in (404, 405), (
        "El objetivo de compra se gestiona en favorites; este endpoint debe estar eliminado."
    )


def test_position_summary_no_expone_target_buy(admin_client, seed_markets):
    """GET /portfolio NO debe exponer target_buy_price (vive en favorites)."""
    sec = admin_client.post("/api/securities", json={
        "name": "PortTgt", "yahoo_ticker": "PRT.MC", "market": "ibex35", "currency": "EUR",
    }).json()["id"]
    pos = admin_client.post("/api/portfolio/positions", json={"security_id": sec}).json()["id"]
    admin_client.post(f"/api/portfolio/{pos}/transactions", json={
        "type": "buy", "date": "2024-01-02", "shares": "5", "price": "10",
        "fee": "0", "currency": "EUR", "exchange_rate": "1",
    })
    pos_data = next(p for p in admin_client.get("/api/portfolio").json() if p["security_id"] == sec)
    assert "target_buy_price" not in pos_data


def test_objetivo_compra_se_guarda_en_favorites(admin_client, seed_markets):
    """La fuente única del objetivo de compra es favorites (PATCH /favorites/{id})."""
    sec = admin_client.post("/api/securities", json={
        "name": "FavTgt", "yahoo_ticker": "FTG.MC", "market": "ibex35", "currency": "EUR",
    }).json()["id"]
    admin_client.post(f"/api/favorites/{sec}")
    r = admin_client.patch(f"/api/favorites/{sec}", json={"target_buy_price": "9.50"})
    assert r.status_code == 200
    assert float(r.json()["target_buy_price"]) == 9.50


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
