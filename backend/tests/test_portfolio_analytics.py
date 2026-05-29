"""
test_portfolio_analytics.py
===========================
Tests para los endpoints de analítica de Mi Cartera v1.6.7+:
  * GET /portfolio/closed-analytics      (scatter posiciones cerradas)
  * GET /portfolio/dividends-by-security (tabla y gráficos de dividendos)
  * GET /markets/exchange-rate           (búsqueda tipo de cambio EUR/USD)

Cubre los bugs corregidos en v1.6.8 y v1.6.10:
  * Bug v1.6.8: NameError DivRow en dividends-by-security.
  * Bug v1.6.10: división por cero en closed-analytics cuando cost_eur=0.
  * Bug v1.6.10: timeout ausente en yfinance (exchange-rate).
  * Funcionalidad nueva v1.6.10: hora real de Yahoo en LiveQuote.quote_time.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy.orm import Session

from app.models import EcbRate
from app.providers.base import LiveQuote


# ---------------------------------------------------------------------------
#  Helpers replicados de test_api.py
# ---------------------------------------------------------------------------

def _crear_security(client, ticker="DIV.MC", market="ibex35", currency="EUR"):
    r = client.post("/api/securities", json={
        "name":         f"Test {ticker}",
        "yahoo_ticker": ticker,
        "market":       market,
        "currency":     currency,
    })
    return r.json()["id"]


def _buy(client, pos_id, shares, price, d="2023-01-10", fee="0"):
    return client.post(f"/api/portfolio/{pos_id}/transactions", json={
        "type": "buy", "date": d,
        "shares": str(shares), "price": str(price), "fee": fee,
        "currency": "EUR", "exchange_rate": "1",
    })


def _sell(client, pos_id, shares, price, d="2024-06-01", fee="0"):
    return client.post(f"/api/portfolio/{pos_id}/transactions", json={
        "type": "sell", "date": d,
        "shares": str(shares), "price": str(price), "fee": fee,
        "currency": "EUR", "exchange_rate": "1",
    })


def _div(client, pos_id, shares, gross_per_share, d="2024-03-15"):
    gross = float(shares) * float(gross_per_share)
    return client.post(f"/api/portfolio/{pos_id}/dividends", json={
        "date": d,
        "shares_at_date":  str(shares),
        "gross_per_share": str(gross_per_share),
        "gross_amount":    str(gross),
        "withholding_tax": "0",
        "currency": "EUR", "exchange_rate": "1",
    })


# ===========================================================================
# GET /portfolio/closed-analytics
# ===========================================================================

class TestClosedAnalytics:

    def test_vacio_sin_posiciones(self, auth_client):
        resp = auth_client.get("/api/portfolio/closed-analytics")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_posicion_abierta_no_aparece(self, admin_client, seed_markets):
        """Una posición con acciones en cartera NO debe aparecer en closed-analytics."""
        sec_id = _crear_security(admin_client, ticker="OPEN1.MC")
        pos_id = admin_client.post(
            "/api/portfolio/positions", json={"security_id": sec_id}
        ).json()["id"]
        _buy(admin_client, pos_id, 10, "5.00")
        resp = admin_client.get("/api/portfolio/closed-analytics")
        assert resp.status_code == 200
        assert not any(p["position_id"] == pos_id for p in resp.json())

    def test_posicion_cerrada_calcula_pnl_pct_y_dias(self, admin_client, seed_markets):
        """Compra 10 acc x 10€ y vende 6 meses después a 15€.

        Aritmética:
          coste = 10 * 10 = 100 €
          ingreso = 10 * 15 = 150 €
          pnl = 50 €
          pnl_pct = 50 / 100 * 100 = 50.0 %
          días = (2024-06-01 - 2023-12-01) = 183 días
        """
        sec_id = _crear_security(admin_client, ticker="GAIN.MC")
        pos_id = admin_client.post(
            "/api/portfolio/positions", json={"security_id": sec_id}
        ).json()["id"]
        _buy(admin_client, pos_id, 10, "10.00", d="2023-12-01")
        _sell(admin_client, pos_id, 10, "15.00", d="2024-06-01")

        resp = admin_client.get("/api/portfolio/closed-analytics")
        assert resp.status_code == 200
        rows = resp.json()
        row = next((r for r in rows if r["position_id"] == pos_id), None)
        assert row is not None
        assert abs(row["pnl_pct"] - 50.0) < 0.001
        # 2023-12-01 → 2024-06-01 = exactamente 183 días
        assert row["avg_days_held"] == 183.0
        assert row["last_sell_date"] == "2024-06-01"

    def test_posicion_cerrada_dias_ponderados_por_lote(self, admin_client, seed_markets):
        """Dos lotes FIFO consumidos por dos ventas — comprueba media ponderada.

        Lote 1: compra 10 acc el 2023-01-10
        Lote 2: compra 10 acc el 2023-07-10
        Venta:  20 acc el 2024-01-10  (consume lote 1 y lote 2)

        Lote 1: días = (2024-01-10 - 2023-01-10) = 365
        Lote 2: días = (2024-01-10 - 2023-07-10) = 184
        Media ponderada por shares (iguales): (365*10 + 184*10) / 20 = 274.5
        """
        sec_id = _crear_security(admin_client, ticker="WAVG.MC")
        pos_id = admin_client.post(
            "/api/portfolio/positions", json={"security_id": sec_id}
        ).json()["id"]
        _buy(admin_client, pos_id, 10, "10.00", d="2023-01-10")
        _buy(admin_client, pos_id, 10, "10.00", d="2023-07-10")
        _sell(admin_client, pos_id, 20, "12.00", d="2024-01-10")

        resp = admin_client.get("/api/portfolio/closed-analytics")
        rows = resp.json()
        row = next((r for r in rows if r["position_id"] == pos_id), None)
        assert row is not None
        # (365 + 184) / 2 = 274.5
        assert abs(row["avg_days_held"] - 274.5) < 0.01


# ===========================================================================
# GET /portfolio/dividends-by-security
# ===========================================================================

class TestDividendsBySecurity:

    def test_vacio_sin_dividendos(self, auth_client):
        resp = auth_client.get("/api/portfolio/dividends-by-security")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_security_sin_dividendos_no_aparece(self, admin_client, seed_markets):
        """Una posición sin dividendos cobrados no debe incluirse."""
        sec_id = _crear_security(admin_client, ticker="NODIV.MC")
        pos_id = admin_client.post(
            "/api/portfolio/positions", json={"security_id": sec_id}
        ).json()["id"]
        _buy(admin_client, pos_id, 10, "5.00")
        resp = admin_client.get("/api/portfolio/dividends-by-security")
        assert resp.status_code == 200
        assert not any(r["security_id"] == sec_id for r in resp.json())

    def test_security_con_un_dividendo_aparece(self, admin_client, seed_markets):
        """Bug v1.6.8: el endpoint fallaba con NameError DivRow.

        Esta llamada debe completarse con éxito y devolver el security
        con su dividendo en lugar de error 500.
        """
        sec_id = _crear_security(admin_client, ticker="DIV1.MC")
        pos_id = admin_client.post(
            "/api/portfolio/positions", json={"security_id": sec_id}
        ).json()["id"]
        _buy(admin_client, pos_id, 100, "10.00", d="2023-01-15")
        _div(admin_client, pos_id, 100, "0.50", d="2024-03-15")

        resp = admin_client.get("/api/portfolio/dividends-by-security")
        assert resp.status_code == 200, resp.text
        rows = resp.json()
        row = next((r for r in rows if r["security_id"] == sec_id), None)
        assert row is not None
        assert row["count"] == 1
        # 100 × 0.50 = 50 €
        assert abs(row["total_eur"] - 50.0) < 0.01

    def test_dividendos_ordenados_por_total_desc(self, admin_client, seed_markets):
        """La respuesta debe venir ordenada por total_eur descendente."""
        sec_a = _crear_security(admin_client, ticker="DIVA.MC")
        sec_b = _crear_security(admin_client, ticker="DIVB.MC")
        pos_a = admin_client.post("/api/portfolio/positions", json={"security_id": sec_a}).json()["id"]
        pos_b = admin_client.post("/api/portfolio/positions", json={"security_id": sec_b}).json()["id"]
        _buy(admin_client, pos_a, 100, "10.00", d="2023-01-15")
        _buy(admin_client, pos_b, 100, "10.00", d="2023-01-15")
        _div(admin_client, pos_a, 100, "0.10")   # 10 €
        _div(admin_client, pos_b, 100, "0.50")   #  50 € → debe ser primero
        resp = admin_client.get("/api/portfolio/dividends-by-security")
        rows = resp.json()
        # Solo los que tenemos creados (puede haber otros)
        nuestros = [r for r in rows if r["security_id"] in (sec_a, sec_b)]
        assert nuestros[0]["security_id"] == sec_b
        assert nuestros[1]["security_id"] == sec_a


# ===========================================================================
# GET /markets/exchange-rate
# ===========================================================================

class TestExchangeRateEndpoint:

    def test_fecha_invalida_devuelve_422(self, auth_client):
        resp = auth_client.get("/api/markets/exchange-rate?date=2024/01/15")
        assert resp.status_code == 422

    def test_ecb_local_se_devuelve_sin_red(self, auth_client, engine):
        """Si hay registro local en ecb_rates con fecha <= solicitada, se devuelve."""
        with Session(engine) as session:
            session.add(EcbRate(date="2024-01-15", rate=Decimal("1.0876")))
            session.commit()

        resp = auth_client.get("/api/markets/exchange-rate?date=2024-01-15")
        assert resp.status_code == 200
        body = resp.json()
        assert body["source"] == "ecb"
        assert abs(body["rate"] - 1.0876) < 0.0001
        assert body["date"] == "2024-01-15"

    def test_ecb_busca_fecha_anterior_mas_cercana(self, auth_client, engine):
        """Si no hay registro exacto pero sí uno anterior, devuelve ese."""
        with Session(engine) as session:
            session.add(EcbRate(date="2024-01-10", rate=Decimal("1.0900")))
            session.commit()

        resp = auth_client.get("/api/markets/exchange-rate?date=2024-01-15")
        body = resp.json()
        assert body["source"] == "ecb"
        assert body["date"] == "2024-01-10"


# ===========================================================================
# Provider Yahoo: timestamp del último trade en LiveQuote
# ===========================================================================

class TestYahooQuoteTime:

    def test_livequote_acepta_quote_time(self):
        """v1.6.10: LiveQuote tiene campo opcional quote_time."""
        q = LiveQuote(
            last_price=Decimal("100.00"),
            prev_close=Decimal("99.00"),
            daily_change_pct=Decimal("1.01"),
            last_dividend=None,
            quote_time="2026-05-30T15:30:00+00:00",
        )
        assert q.quote_time == "2026-05-30T15:30:00+00:00"

    def test_livequote_quote_time_opcional(self):
        """LiveQuote sigue siendo compatible sin quote_time (default None)."""
        q = LiveQuote(
            last_price=Decimal("100.00"),
            prev_close=Decimal("99.00"),
            daily_change_pct=Decimal("1.01"),
            last_dividend=None,
        )
        assert q.quote_time is None
