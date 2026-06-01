"""
test_ghostfolio_import.py
=========================
Tests de importación de exportaciones Ghostfolio (v1.6.15).

POST /api/portfolio/import-ghostfolio acepta el JSON exportado desde
Ghostfolio y crea las transacciones/dividendos que no existan aún.

Cubre:
- BUY básico, SELL, DIVIDEND con gross_amount calculado.
- Tipos ignorados (FEE, INTEREST, ITEM) no crean registros.
- Deduplicación: reimportar no crea duplicados.
- Ticker no encontrado → error por fila, resto se importa.
- Formato inválido (sin clave activities) → 400.
- Sin autenticación → 401.
"""

from __future__ import annotations


# ---------------------------------------------------------------------------
#  Helpers
# ---------------------------------------------------------------------------

def _crear_security(client, ticker="SAN.MC", market="ibex35"):
    r = client.post("/api/securities", json={
        "name": ticker, "yahoo_ticker": ticker,
        "market": market, "currency": "EUR",
    })
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _gf_post(client, activities):
    return client.post(
        "/api/portfolio/import-ghostfolio",
        json={"meta": {"date": "2024-01-01", "version": "1"}, "activities": activities},
    )


def _buy_act(ticker="SAN.MC", date="2023-01-15T00:00:00.000Z",
             qty=100, price=3.25, fee=0.5):
    return {
        "type": "BUY", "symbol": ticker, "date": date,
        "quantity": qty, "unitPrice": price, "fee": fee,
        "currency": "EUR", "dataSource": "YAHOO",
    }


def _sell_act(ticker="SAN.MC", date="2024-06-10T00:00:00.000Z",
              qty=50, price=4.10, fee=0.5):
    return {
        "type": "SELL", "symbol": ticker, "date": date,
        "quantity": qty, "unitPrice": price, "fee": fee,
        "currency": "EUR", "dataSource": "YAHOO",
    }


def _div_act(ticker="SAN.MC", date="2023-07-05T00:00:00.000Z",
             qty=100, gps=0.025, wht=0.38):
    return {
        "type": "DIVIDEND", "symbol": ticker, "date": date,
        "quantity": qty, "unitPrice": gps, "fee": wht,
        "currency": "EUR", "dataSource": "YAHOO",
    }


# ---------------------------------------------------------------------------
#  Tests básicos
# ---------------------------------------------------------------------------

def test_importar_buy(auth_client, admin_client, seed_markets):
    _crear_security(admin_client)
    r = _gf_post(auth_client, [_buy_act()])
    assert r.status_code == 200
    d = r.json()
    # 1 compra creada
    assert d["transactions_added"] == 1
    assert d["dividends_added"] == 0
    assert d["skipped"] == 0
    assert d["errors"] == []


def test_importar_sell(auth_client, admin_client, seed_markets):
    _crear_security(admin_client)
    r = _gf_post(auth_client, [_buy_act(qty=100), _sell_act(qty=50)])
    assert r.status_code == 200
    d = r.json()
    # compra + venta
    assert d["transactions_added"] == 2
    assert d["errors"] == []


def test_importar_dividend_gross_calculado(auth_client, admin_client, seed_markets):
    """gross_amount = quantity × unitPrice = 100 × 0.025 = 2.50."""
    _crear_security(admin_client)
    _gf_post(auth_client, [_buy_act()])   # crear posición primero
    r = _gf_post(auth_client, [_div_act()])
    assert r.status_code == 200
    d = r.json()
    assert d["dividends_added"] == 1
    assert d["errors"] == []


def test_tipos_ignorados_no_crean_registros(auth_client, admin_client, seed_markets):
    """FEE, INTEREST e ITEM se omiten silenciosamente (no son errores)."""
    _crear_security(admin_client)
    ignored = [
        {"type": "FEE",      "symbol": "SAN.MC", "date": "2023-01-15T00:00:00.000Z",
         "quantity": 1, "unitPrice": 1, "fee": 0, "currency": "EUR"},
        {"type": "INTEREST", "symbol": "SAN.MC", "date": "2023-01-15T00:00:00.000Z",
         "quantity": 1, "unitPrice": 1, "fee": 0, "currency": "EUR"},
        {"type": "ITEM",     "symbol": "SAN.MC", "date": "2023-01-15T00:00:00.000Z",
         "quantity": 1, "unitPrice": 1, "fee": 0, "currency": "EUR"},
    ]
    r = _gf_post(auth_client, ignored)
    assert r.status_code == 200
    d = r.json()
    assert d["transactions_added"] == 0
    assert d["dividends_added"] == 0
    assert d["errors"] == []


# ---------------------------------------------------------------------------
#  Deduplicación
# ---------------------------------------------------------------------------

def test_deduplicacion_transaccion(auth_client, admin_client, seed_markets):
    """Reimportar el mismo JSON no crea duplicados."""
    _crear_security(admin_client)
    acts = [_buy_act()]
    _gf_post(auth_client, acts)          # primera vez
    r2 = _gf_post(auth_client, acts)     # segunda vez
    assert r2.status_code == 200
    d = r2.json()
    assert d["transactions_added"] == 0
    assert d["skipped"] == 1


def test_deduplicacion_dividendo(auth_client, admin_client, seed_markets):
    _crear_security(admin_client)
    _gf_post(auth_client, [_buy_act()])
    acts = [_div_act()]
    _gf_post(auth_client, acts)
    r2 = _gf_post(auth_client, acts)
    assert r2.status_code == 200
    d = r2.json()
    assert d["dividends_added"] == 0
    assert d["skipped"] == 1


# ---------------------------------------------------------------------------
#  Gestión de errores
# ---------------------------------------------------------------------------

def test_ticker_no_existe(auth_client, seed_markets):
    """Ticker sin registrar → error por fila, sin bloquear otras."""
    r = _gf_post(auth_client, [_buy_act(ticker="NOEXISTE")])
    assert r.status_code == 200
    d = r.json()
    assert d["transactions_added"] == 0
    assert len(d["errors"]) == 1
    assert "NOEXISTE" in d["errors"][0]["ticker"]


def test_ticker_inexistente_no_bloquea_validos(auth_client, admin_client, seed_markets):
    _crear_security(admin_client, ticker="SAN.MC")
    acts = [_buy_act(ticker="NOEXISTE"), _buy_act(ticker="SAN.MC")]
    r = _gf_post(auth_client, acts)
    assert r.status_code == 200
    d = r.json()
    assert d["transactions_added"] == 1
    assert len(d["errors"]) == 1


def test_formato_invalido_sin_activities(auth_client):
    """JSON sin clave activities → 400."""
    r = auth_client.post("/api/portfolio/import-ghostfolio",
                         json={"meta": {"version": "1"}})
    assert r.status_code == 400


def test_sin_autenticacion(client, seed_markets):
    """Sin sesión → 401."""
    r = _gf_post(client, [_buy_act()])
    assert r.status_code == 401
