"""
test_movements.py
=================
GET /api/portfolio/movements — listado de últimos movimientos (compras, ventas
y dividendos) de toda la cartera del usuario, de más reciente a más antiguo,
con tope de 50.
"""
from tests.test_api import _crear_security, _buy, _sell
from tests.test_transfers import _crear_fondos


def _div(client, pos_id, *, date, shares="100", gps="0.50", gross="50.00", wht="0", currency="EUR", rate="1"):
    return client.post(f"/api/portfolio/{pos_id}/dividends", json={
        "date": date, "shares_at_date": shares, "gross_per_share": gps,
        "gross_amount": gross, "withholding_tax": wht,
        "currency": currency, "exchange_rate": rate,
    })


def test_movements_vacio(auth_client):
    resp = auth_client.get("/api/portfolio/movements")
    assert resp.status_code == 200
    assert resp.json() == []


def test_movements_requiere_auth(client):
    assert client.get("/api/portfolio/movements").status_code in (401, 403)


def test_movements_combina_y_ordena_desc(admin_client, seed_markets):
    """Compras, ventas y dividendos se combinan y salen de más nuevo a más viejo."""
    sec_id = _crear_security(admin_client, ticker="MOV.MC")
    pos_id = admin_client.post("/api/portfolio/positions", json={"security_id": sec_id}).json()["id"]

    # buy 2024-01-10 (helper), sell 2024-06-01 (helper), dividendo 2024-03-15
    _buy(admin_client, pos_id, 100, "10.00", fee="5")
    _sell(admin_client, pos_id, 40, "12.00", fee="3")
    _div(admin_client, pos_id, date="2024-03-15", shares="100", gps="0.50", gross="50.00", wht="9.50")

    movs = admin_client.get("/api/portfolio/movements").json()
    assert len(movs) == 3
    # Orden por fecha desc: sell(06-01) > dividend(03-15) > buy(01-10)
    assert [m["kind"] for m in movs] == ["sell", "dividend", "buy"]
    assert [m["date"] for m in movs] == ["2024-06-01", "2024-03-15", "2024-01-10"]

    buy = movs[2]
    # buy: 100×10 + 5 fee = 1005
    assert float(buy["amount_native"]) == 1005.0
    assert float(buy["amount_eur"]) == 1005.0
    assert buy["yahoo_ticker"] == "MOV.MC"
    assert buy["security_id"] == sec_id

    sell = movs[0]
    # sell: 40×12 − 3 fee = 477
    assert float(sell["amount_native"]) == 477.0

    div = movs[1]
    # dividendo neto: 50.00 − 9.50 = 40.50
    assert float(div["amount_native"]) == 40.5
    assert float(div["shares"]) == 100.0
    assert float(div["price"]) == 0.50


def test_movements_excluye_traspasos(admin_client):
    """Los traspasos de fondos (transfer_in/out) no son movimientos del listado."""
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

    movs = admin_client.get("/api/portfolio/movements").json()
    # Solo la compra inicial; los dos lados del traspaso quedan fuera.
    assert all(m["kind"] in ("buy", "sell", "dividend") for m in movs)
    assert len(movs) == 1
    assert movs[0]["kind"] == "buy"


def test_movements_limita_a_50(admin_client, seed_markets):
    """Con más de 50 movimientos, el endpoint devuelve como mucho 50 (los más recientes)."""
    sec_id = _crear_security(admin_client, ticker="MANY.MC")
    pos_id = admin_client.post("/api/portfolio/positions", json={"security_id": sec_id}).json()["id"]
    # 60 compras en fechas crecientes 2020-01-01 + n días
    import datetime
    base = datetime.date(2020, 1, 1)
    for n in range(60):
        d = (base + datetime.timedelta(days=n)).isoformat()
        admin_client.post(f"/api/portfolio/{pos_id}/transactions", json={
            "type": "buy", "date": d, "shares": "1", "price": "10.00",
            "fee": "0", "currency": "EUR", "exchange_rate": "1",
        })

    movs = admin_client.get("/api/portfolio/movements").json()
    assert len(movs) == 50
    # La más reciente es 2020-01-01 + 59 días
    most_recent = (base + datetime.timedelta(days=59)).isoformat()
    assert movs[0]["date"] == most_recent


def test_movements_limit_param_capado(auth_client):
    """limit > 50 es 422 (el backend lo limita a 50)."""
    assert auth_client.get("/api/portfolio/movements?limit=100").status_code == 422
