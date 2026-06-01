"""
test_csv_import.py
==================
Tests de la importación CSV de operaciones de cartera (v1.6.14).

POST /api/portfolio/import-csv recibe una lista de filas JSON (el frontend
parsea el CSV y envía el resultado) y crea las transacciones/dividendos
que no existan aún.

Cubre:
- Compra básica EUR, venta EUR.
- Dividendo sin gross_amount (calculado) y con gross_amount explícito.
- Deduplicación: reimportar el mismo CSV no crea registros duplicados.
- Ticker no encontrado en catálogo → error por fila, resto se importa.
- Varios tickers distintos: crea posiciones separadas.
- Compra USD con exchange_rate.
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


def _csv_post(client, rows):
    return client.post("/api/portfolio/import-csv", json={"rows": rows})


def _buy_row(ticker="SAN.MC", date="2023-01-15", shares=100, price=3.25, fee=0.5):
    return {
        "type": "buy", "ticker": ticker, "date": date,
        "shares": shares, "price": price, "fee": fee,
        "currency": "EUR", "exchange_rate": 1,
    }


def _sell_row(ticker="SAN.MC", date="2024-06-10", shares=50, price=4.10, fee=0.5):
    return {
        "type": "sell", "ticker": ticker, "date": date,
        "shares": shares, "price": price, "fee": fee,
        "currency": "EUR", "exchange_rate": 1,
    }


def _div_row(ticker="SAN.MC", date="2023-07-05", shares=100,
             gross_per_share=0.025, gross_amount=None, withholding_tax=0.38):
    row = {
        "type": "dividend", "ticker": ticker, "date": date,
        "shares": shares, "gross_per_share": gross_per_share,
        "withholding_tax": withholding_tax,
        "currency": "EUR", "exchange_rate": 1,
    }
    if gross_amount is not None:
        row["gross_amount"] = gross_amount
    return row


# ---------------------------------------------------------------------------
#  Tests de importación básica
# ---------------------------------------------------------------------------

def test_importar_compra_basica(auth_client, admin_client, seed_markets):
    _crear_security(admin_client)
    r = _csv_post(auth_client, [_buy_row()])
    assert r.status_code == 200
    d = r.json()
    # 1 compra creada, sin duplicados ni errores
    assert d["transactions_added"] == 1
    assert d["dividends_added"] == 0
    assert d["skipped"] == 0
    assert d["errors"] == []


def test_importar_compra_y_venta(auth_client, admin_client, seed_markets):
    _crear_security(admin_client)
    rows = [_buy_row(shares=100), _sell_row(shares=50)]
    r = _csv_post(auth_client, rows)
    assert r.status_code == 200
    d = r.json()
    # 2 transacciones (compra + venta)
    assert d["transactions_added"] == 2
    assert d["errors"] == []


def test_importar_dividendo_gross_calculado(auth_client, admin_client, seed_markets):
    """Sin gross_amount: el backend lo calcula como shares × gross_per_share."""
    _crear_security(admin_client)
    _csv_post(auth_client, [_buy_row()])  # crear posición primero
    # gross_amount = 100 × 0.025 = 2.50
    r = _csv_post(auth_client, [_div_row(gross_amount=None)])
    assert r.status_code == 200
    d = r.json()
    assert d["dividends_added"] == 1
    assert d["errors"] == []


def test_importar_dividendo_gross_explicito(auth_client, admin_client, seed_markets):
    """Con gross_amount explícito del broker (puede diferir del calculado)."""
    _crear_security(admin_client)
    _csv_post(auth_client, [_buy_row()])
    r = _csv_post(auth_client, [_div_row(gross_amount=2.48)])
    assert r.status_code == 200
    d = r.json()
    assert d["dividends_added"] == 1
    assert d["errors"] == []


# ---------------------------------------------------------------------------
#  Deduplicación
# ---------------------------------------------------------------------------

def test_deduplicacion_transaccion(auth_client, admin_client, seed_markets):
    """Reimportar la misma compra no crea duplicado."""
    _crear_security(admin_client)
    rows = [_buy_row()]
    _csv_post(auth_client, rows)          # primera vez: importa
    r2 = _csv_post(auth_client, rows)     # segunda vez: omite
    assert r2.status_code == 200
    d = r2.json()
    # La fila existe → skipped=1, transactions_added=0
    assert d["transactions_added"] == 0
    assert d["skipped"] == 1
    assert d["errors"] == []


def test_deduplicacion_dividendo(auth_client, admin_client, seed_markets):
    """Reimportar el mismo dividendo no crea duplicado."""
    _crear_security(admin_client)
    _csv_post(auth_client, [_buy_row()])
    rows = [_div_row()]
    _csv_post(auth_client, rows)
    r2 = _csv_post(auth_client, rows)
    assert r2.status_code == 200
    d = r2.json()
    assert d["dividends_added"] == 0
    assert d["skipped"] == 1


# ---------------------------------------------------------------------------
#  Gestión de errores
# ---------------------------------------------------------------------------

def test_ticker_no_existe(auth_client, seed_markets):
    """Fila con ticker inexistente genera error; si hay más filas válidas se importan."""
    # No creamos ningún security
    r = _csv_post(auth_client, [_buy_row(ticker="NOEXISTE")])
    assert r.status_code == 200
    d = r.json()
    assert d["transactions_added"] == 0
    assert len(d["errors"]) == 1
    assert "NOEXISTE" in d["errors"][0]["ticker"]
    assert d["errors"][0]["row"] == 1


def test_ticker_inexistente_no_bloquea_validos(auth_client, admin_client, seed_markets):
    """El error en una fila no impide importar las demás."""
    _crear_security(admin_client, ticker="SAN.MC")
    rows = [
        _buy_row(ticker="NOEXISTE"),   # fila 1: error
        _buy_row(ticker="SAN.MC"),     # fila 2: válida
    ]
    r = _csv_post(auth_client, rows)
    assert r.status_code == 200
    d = r.json()
    assert d["transactions_added"] == 1
    assert len(d["errors"]) == 1
    assert d["errors"][0]["row"] == 1


def test_mezcla_tickers(auth_client, admin_client, seed_markets):
    """Varios tickers distintos crean posiciones separadas."""
    _crear_security(admin_client, ticker="SAN.MC", market="ibex35")
    _crear_security(admin_client, ticker="BBVA.MC", market="ibex35")
    rows = [_buy_row(ticker="SAN.MC"), _buy_row(ticker="BBVA.MC")]
    r = _csv_post(auth_client, rows)
    assert r.status_code == 200
    assert r.json()["transactions_added"] == 2


def test_usd_con_exchange_rate(auth_client, admin_client, seed_markets):
    """Compra en USD con exchange_rate válido."""
    _crear_security(admin_client, ticker="AAPL", market="nasdaq")
    row = {
        "type": "buy", "ticker": "AAPL", "date": "2023-03-20",
        "shares": 10, "price": 152.50, "fee": 1.0,
        "currency": "USD", "exchange_rate": 1.0831,
    }
    r = _csv_post(auth_client, [row])
    assert r.status_code == 200
    d = r.json()
    assert d["transactions_added"] == 1
    assert d["errors"] == []


def test_usd_exchange_rate_1_da_error(auth_client, admin_client, seed_markets):
    """USD con exchange_rate=1 es incoherente → error de fila."""
    _crear_security(admin_client, ticker="AAPL", market="nasdaq")
    row = {
        "type": "buy", "ticker": "AAPL", "date": "2023-03-20",
        "shares": 10, "price": 152.50, "fee": 1.0,
        "currency": "USD", "exchange_rate": 1,
    }
    r = _csv_post(auth_client, [row])
    assert r.status_code == 200
    d = r.json()
    assert d["transactions_added"] == 0
    assert len(d["errors"]) == 1


def test_sin_autenticacion(client, seed_markets):
    """Sin sesión iniciada → 401."""
    r = _csv_post(client, [_buy_row()])
    assert r.status_code == 401
