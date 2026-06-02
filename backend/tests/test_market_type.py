"""
test_market_type.py
===================
Tests del tipo de producto por mercado (v1.7.6): segmentación de Cartera/
Dashboard y agrupación del menú de Mercados.

Cubre:
  * Admin: crear/editar mercado con market_type; is_fund_market derivado.
  * Catálogo: export incluye market_type; import lo deriva si falta.
  * Endpoints exponen market_type (overview, portfolio).
  * /portfolio/history?types= filtra por tipo de producto.
"""

from decimal import Decimal as D

from sqlalchemy.orm import Session

from app.models import PriceHistory


def _market(admin_client, code, name, market_type, currency="EUR"):
    return admin_client.post("/api/admin/markets", json={
        "code": code, "name": name, "currency": currency,
        "fiscal_window_days": 60, "market_type": market_type,
    })


# ---------------------------------------------------------------------------
#  Admin: tipo de producto e is_fund_market derivado
# ---------------------------------------------------------------------------

def test_crear_mercado_con_tipo(admin_client):
    r = _market(admin_client, "etfs_eur", "ETFs Euro", "etf")
    assert r.status_code == 201, r.text
    data = r.json()
    assert data["market_type"] == "etf"
    assert data["is_fund_market"] is False


def test_tipo_fund_deriva_is_fund_market(admin_client):
    r = _market(admin_client, "fondos_nac", "Fondos Nacionales", "fund")
    assert r.status_code == 201
    assert r.json()["market_type"] == "fund"
    assert r.json()["is_fund_market"] is True


def test_compat_is_fund_market_sin_tipo(admin_client):
    """Cliente antiguo que solo manda is_fund_market=True → tipo 'fund'."""
    r = admin_client.post("/api/admin/markets", json={
        "code": "fondos_legacy", "name": "Fondos legacy", "currency": "EUR",
        "fiscal_window_days": 60, "is_fund_market": True,
    })
    assert r.status_code == 201
    assert r.json()["market_type"] == "fund"


def test_editar_tipo_mercado(admin_client):
    _market(admin_client, "cryptos", "Crypto", "stock")
    r = admin_client.patch("/api/admin/markets/cryptos", json={"market_type": "crypto"})
    assert r.status_code == 200
    assert r.json()["market_type"] == "crypto"
    assert r.json()["is_fund_market"] is False


# ---------------------------------------------------------------------------
#  Catálogo: export / import con market_type
# ---------------------------------------------------------------------------

def test_catalogo_export_incluye_tipo(admin_client):
    _market(admin_client, "ibex35", "IBEX 35", "stock")
    _market(admin_client, "fondos_x", "Fondos X", "fund")
    data = admin_client.get("/api/admin/catalog/export").json()
    by_code = {m["code"]: m for m in data["markets"]}
    assert by_code["ibex35"]["market_type"] == "stock"
    assert by_code["fondos_x"]["market_type"] == "fund"


def test_catalogo_import_deriva_tipo_si_falta(admin_client):
    """Catálogo antiguo sin market_type: se deriva (fondo / etf / crypto / stock)."""
    body = {
        "markets": [
            {"code": "etf_old", "name": "ETF viejo", "currency": "EUR"},          # 'etf' en código → etf
            {"code": "cryptoz", "name": "Cripto vieja", "currency": "EUR"},       # 'crypto' → crypto
            {"code": "fond_old", "name": "Fondo viejo", "currency": "EUR",
             "is_fund_market": True},                                             # is_fund → fund
            {"code": "acc_old", "name": "Acciones viejas", "currency": "EUR"},    # resto → stock
        ],
        "securities": [],
    }
    r = admin_client.post("/api/admin/catalog/import", json=body)
    assert r.status_code == 200, r.text
    by_code = {m["code"]: m for m in admin_client.get("/api/admin/catalog/export").json()["markets"]}
    assert by_code["etf_old"]["market_type"] == "etf"
    assert by_code["cryptoz"]["market_type"] == "crypto"
    assert by_code["fond_old"]["market_type"] == "fund"
    assert by_code["acc_old"]["market_type"] == "stock"


def test_catalogo_import_respeta_tipo_explicito(admin_client):
    """Si el catálogo trae market_type, se respeta aunque el código sugiera otro."""
    body = {
        "markets": [
            # código con 'etf' pero declarado 'stock' explícitamente → stock
            {"code": "betf_stocks", "name": "Mercado raro", "currency": "EUR",
             "market_type": "stock"},
        ],
        "securities": [],
    }
    admin_client.post("/api/admin/catalog/import", json=body)
    by_code = {m["code"]: m for m in admin_client.get("/api/admin/catalog/export").json()["markets"]}
    assert by_code["betf_stocks"]["market_type"] == "stock"


# ---------------------------------------------------------------------------
#  Exposición de market_type y filtro de history
# ---------------------------------------------------------------------------

def _sec(admin_client, ticker, market):
    return admin_client.post("/api/securities", json={
        "name": ticker, "yahoo_ticker": ticker, "market": market, "currency": "EUR",
    }).json()["id"]


def test_overview_expone_market_type(admin_client):
    _market(admin_client, "etfs_eur", "ETFs Euro", "etf")
    _sec(admin_client, "ETF1.MC", "etfs_eur")
    data = admin_client.get("/api/markets/overview?market=etfs_eur").json()
    assert len(data) == 1
    assert data[0]["market_type"] == "etf"


def test_history_filtra_por_tipo(admin_client, engine):
    """/portfolio/history?types= solo agrega las posiciones del tipo pedido."""
    _market(admin_client, "ibex35", "IBEX 35", "stock")
    _market(admin_client, "etfs_eur", "ETFs Euro", "etf")
    sec_acc = _sec(admin_client, "ACC.MC", "ibex35")
    sec_etf = _sec(admin_client, "ETF.MC", "etfs_eur")

    pos_acc = admin_client.post("/api/portfolio/positions", json={"security_id": sec_acc}).json()["id"]
    pos_etf = admin_client.post("/api/portfolio/positions", json={"security_id": sec_etf}).json()["id"]
    for pos in (pos_acc, pos_etf):
        admin_client.post(f"/api/portfolio/{pos}/transactions", json={
            "type": "buy", "date": "2024-01-10", "shares": "10", "price": "10",
            "fee": "0", "currency": "EUR", "exchange_rate": "1",
        })
    with Session(engine) as s:
        s.add(PriceHistory(security_id=sec_acc, date="2024-01-15", close=D("12")))
        s.add(PriceHistory(security_id=sec_etf, date="2024-01-15", close=D("20")))
        s.commit()

    todo = admin_client.get("/api/portfolio/history").json()
    solo_etf = admin_client.get("/api/portfolio/history?types=etf").json()

    def val(rows, d):
        return next((r["value"] for r in rows if r["date"] == d), None)

    # 2024-01-15: acciones 10×12=120, etf 10×20=200, total=320; solo etf=200.
    assert abs(val(todo, "2024-01-15") - 320.0) < 0.01
    assert abs(val(solo_etf, "2024-01-15") - 200.0) < 0.01
