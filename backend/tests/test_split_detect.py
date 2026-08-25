"""
test_split_detect.py
====================
GET /api/admin/splits/detect — splits y contrasplits NO registrados, buscados
sobre las carteras de TODOS los usuarios.

Contexto (incidente real, 2026-08): AMP.MC hizo un contrasplit 1:25 que nadie
dio de alta. Yahoo reajusta hacia atras la serie entera en cuanto ocurre, asi
que las 9.500 acciones de un usuario pasaron a valorarse contra precios x25: una
posicion de 1.500 EUR figuraba como 38.000 y el grafico llego a marcar ~68.000
EUR de cartera, con un desplome vertical el dia de la venta.

Lo peor no fue el error sino el silencio. /history/coverage no lo ve, porque
solo detecta datos que FALTAN y aqui no falta ninguno: estan todos, en otra
escala. La curva sale completa y verosimil. Se encontro comparando a mano el
precio pagado con el cierre de ese dia, que es justo lo que automatiza esto.
"""

from decimal import Decimal as D

from sqlalchemy.orm import Session

from app.models import PriceHistory


def _sec(client, ticker):
    r = client.post("/api/securities", json={
        "name": f"Test {ticker}", "yahoo_ticker": ticker,
        "market": "continuo", "currency": "EUR",
    })
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _compra(client, sec_id, d, shares, price):
    pos = client.post("/api/portfolio/positions", json={"security_id": sec_id}).json()["id"]
    r = client.post(f"/api/portfolio/{pos}/transactions", json={
        "type": "buy", "date": d, "shares": shares, "price": price,
        "fee": "0", "currency": "EUR", "exchange_rate": "1",
    })
    assert r.status_code in (200, 201), r.text
    return pos


def test_detecta_contrasplit_no_registrado(admin_client, seed_markets, engine):
    """2.500 acc a 0,16 EUR contra una serie que cotiza a 4,00: factor 25."""
    sec = _sec(admin_client, "CONTRA.MC")
    _compra(admin_client, sec, "2025-01-02", "2500", "0.16")
    with Session(engine) as s:
        s.add(PriceHistory(security_id=sec, date="2025-01-02", close=D("4.00")))
        s.commit()

    det = admin_client.get("/api/admin/splits/detect").json()["detected"]
    assert len(det) == 1, det
    e = det[0]
    assert e["ticker"] == "CONTRA.MC"
    assert abs(e["factor"] - 25.0) < 0.01
    # cierre/pagado = ratio_den/ratio_num -> contrasplit 1:25
    assert (e["suggested_ratio_num"], e["suggested_ratio_den"]) == (1, 25)
    assert e["users"] == ["adminuser"]
    assert e["registered_splits"] == 0


def test_detecta_split_normal(admin_client, seed_markets, engine):
    """Un split 2:1 deja el cierre ajustado a la MITAD del precio pagado."""
    sec = _sec(admin_client, "DOBLE.MC")
    _compra(admin_client, sec, "2025-01-02", "100", "100")
    with Session(engine) as s:
        s.add(PriceHistory(security_id=sec, date="2025-01-02", close=D("50")))
        s.commit()

    e = admin_client.get("/api/admin/splits/detect").json()["detected"][0]
    assert abs(e["factor"] - 0.5) < 0.01
    assert (e["suggested_ratio_num"], e["suggested_ratio_den"]) == (2, 1)


def test_split_ya_registrado_no_aparece(admin_client, seed_markets, engine):
    """
    Lo que ya esta dado de alta esta resuelto: normalize_splits deja el precio en
    la misma escala que la serie. Si siguiera apareciendo, el aviso seria ruido y
    dejaria de leerse.
    """
    sec = _sec(admin_client, "OK.MC")
    _compra(admin_client, sec, "2025-01-02", "100", "100")
    admin_client.post(f"/api/admin/securities/{sec}/splits", json={
        "ex_date": "2025-06-01", "ratio_num": 2, "ratio_den": 1,
    })
    with Session(engine) as s:
        s.add(PriceHistory(security_id=sec, date="2025-01-02", close=D("50")))
        s.commit()

    assert admin_client.get("/api/admin/splits/detect").json()["detected"] == []


def test_valor_normal_no_aparece(admin_client, seed_markets, engine):
    """Variacion intradia normal: no es un split."""
    sec = _sec(admin_client, "SANO.MC")
    _compra(admin_client, sec, "2025-01-02", "100", "10")
    with Session(engine) as s:
        s.add(PriceHistory(security_id=sec, date="2025-01-02", close=D("10.4")))
        s.commit()

    assert admin_client.get("/api/admin/splits/detect").json()["detected"] == []


def test_agrega_todos_los_usuarios(client, test_user, test_admin, seed_markets, engine):
    """
    El admin ve el valor UNA vez, con los dos usuarios afectados.

    Se usa un solo 'client' con re-login explicito: auth_client y admin_client
    comparten instancia (StaticPool) y el ultimo login ganaria.
    """
    client.post("/api/auth/login", json={"username": "adminuser", "password": "adminpass123"})
    sec = _sec(client, "COMUN.MC")
    _compra(client, sec, "2025-01-02", "1000", "0.20")

    client.post("/api/auth/login", json={"username": "testuser", "password": "testpass123"})
    _compra(client, sec, "2025-02-03", "500", "0.22")

    with Session(engine) as s:
        s.add_all([
            PriceHistory(security_id=sec, date="2025-01-02", close=D("5.00")),
            PriceHistory(security_id=sec, date="2025-02-03", close=D("5.50")),
        ])
        s.commit()

    client.post("/api/auth/login", json={"username": "adminuser", "password": "adminpass123"})
    det = client.get("/api/admin/splits/detect").json()["detected"]
    assert len(det) == 1, det
    assert det[0]["users"] == ["adminuser", "testuser"]
    assert abs(det[0]["factor"] - 25.0) < 0.01


def test_detect_requiere_admin(auth_client):
    assert auth_client.get("/api/admin/splits/detect").status_code == 403
