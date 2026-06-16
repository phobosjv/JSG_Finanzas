"""
test_bugs.py
============
Tests que exponen bugs confirmados y evitan regresiones.

Cada sección documenta:
  * Qué es el bug y por qué es un fallo.
  * El escenario mínimo que lo reproduce.
  * El comportamiento CORRECTO que debe pasar tras la corrección.

Ejecutar:  pytest tests/test_bugs.py -v
"""

from datetime import date
from decimal import Decimal

import pytest

from app.services.calculations import (
    Transaction, Dividend, Split,
    aggregate_portfolio, compute_position, to_eur,
)
from app.services.tax_report import (
    SecurityRef, SecuritySales, SaleMatch, build_tax_report,
)


# ---------------------------------------------------------------------------
#  Helpers
# ---------------------------------------------------------------------------

def D(x: str) -> Decimal:
    return Decimal(x)


def buy_eur(d: str, shares: str, price: str, fee: str = "0") -> Transaction:
    return Transaction("buy", date.fromisoformat(d), D(shares), D(price), D(fee), D("1"))


def sell_eur(d: str, shares: str, price: str, fee: str = "0") -> Transaction:
    return Transaction("sell", date.fromisoformat(d), D(shares), D(price), D(fee), D("1"))


def split_2_1(ex_date: str) -> Split:
    return Split(ex_date=date.fromisoformat(ex_date), ratio_num=2, ratio_den=1)


# ===========================================================================
# BUG 1 — aggregate_portfolio: avg_return_pct usa solo ganancia latente,
#          no el beneficio total (realizado + latente + dividendos).
#
# Dónde:   services/calculations.py → aggregate_portfolio()
# Síntoma: el dashboard muestra un % de rentabilidad muy bajo o cero aunque
#          haya grandes ganancias realizadas o dividendos cobrados.
# Causa:   avg_pct = unrealized / invested  (incorrecto)
#           debería ser  total_gain / invested  según la propia docstring.
# ===========================================================================

class TestBugAvgReturnPct:

    def test_avg_return_pct_incluye_ganancias_realizadas(self):
        """
        Cartera con ganancia SOLO realizada (posición ya cerrada, nada latente).

        invested=1000, realized=200, unrealized=0, dividendos=0
        total_gain = 200
        avg_return_pct correcto = 200/1000*100 = 20 %
        avg_return_pct INCORRECTO (bug) = 0/1000*100 = 0 %
        """
        posiciones = [{
            "invested_eur":       D("1000"),
            "market_value_eur":   D("1000"),   # valor de mercado = coste (sin latente)
            "realized_gain_eur":  D("200"),
            "unrealized_gain_eur": D("0"),
            "dividends_net_eur":  D("0"),
        }]
        a = aggregate_portfolio(posiciones)

        # El beneficio total se calcula correctamente...
        assert a["total_gain_eur"] == D("200")
        # ...pero el % debe reflejarlo
        assert abs(a["avg_return_pct"] - D("20")) < D("0.01"), (
            f"Bug: avg_return_pct={a['avg_return_pct']} pero debería ser 20 "
            f"(las ganancias realizadas no se incluyen en el porcentaje)"
        )

    def test_avg_return_pct_incluye_dividendos(self):
        """
        Cartera con dividendos cobrados, sin latente ni realizado.

        invested=2000, realized=0, unrealized=0, dividendos=300
        total_gain = 300
        avg_return_pct correcto = 300/2000*100 = 15 %
        avg_return_pct INCORRECTO (bug) = 0/2000*100 = 0 %
        """
        posiciones = [{
            "invested_eur":       D("2000"),
            "market_value_eur":   D("2000"),
            "realized_gain_eur":  D("0"),
            "unrealized_gain_eur": D("0"),
            "dividends_net_eur":  D("300"),
        }]
        a = aggregate_portfolio(posiciones)

        assert a["total_gain_eur"] == D("300")
        assert abs(a["avg_return_pct"] - D("15")) < D("0.01"), (
            f"Bug: avg_return_pct={a['avg_return_pct']} pero debería ser 15 "
            f"(los dividendos no se incluyen en el porcentaje)"
        )

    def test_avg_return_pct_mezcla_todos_los_componentes(self):
        """
        Escenario completo: realizado + latente + dividendos.

        Pos 1: invertido=1000, realizado=100, latente=50, dividendos=30 → total=180
        Pos 2: invertido=2000, realizado=0, latente=-100, dividendos=20 → total=-80

        total_gain = 180 + (-80) = 100
        avg_return_pct correcto = 100/3000*100 = 3.333...%

        Con el bug (solo latente): (-50)/3000*100 = -1.666...% — INCORRECTO
        """
        posiciones = [
            {
                "invested_eur":       D("1000"),
                "market_value_eur":   D("1050"),
                "realized_gain_eur":  D("100"),
                "unrealized_gain_eur": D("50"),
                "dividends_net_eur":  D("30"),
            },
            {
                "invested_eur":       D("2000"),
                "market_value_eur":   D("1900"),
                "realized_gain_eur":  D("0"),
                "unrealized_gain_eur": D("-100"),
                "dividends_net_eur":  D("20"),
            },
        ]
        a = aggregate_portfolio(posiciones)

        assert a["total_gain_eur"] == D("100")
        # total_gain(100) / invested(3000) * 100 = 3.333...%
        expected_pct = D("100") / D("3000") * D("100")
        assert abs(a["avg_return_pct"] - expected_pct) < D("0.01"), (
            f"Bug: avg_return_pct={a['avg_return_pct']} "
            f"pero debería ser ≈{expected_pct:.4f}"
        )


# ===========================================================================
# BUG 2 — Backup import: se permite price=0 en transacciones,
#          aunque la API rechaza price≤0.
#
# Dónde:   api/backup.py → import_backup()
#          api/admin.py  → admin_import_backup()
# Síntoma: se insertan transacciones con precio 0 en la BD vía backup;
#          la API normal rechazaría ese precio con 422.
# Causa:   validación en backup usa  `tx_price < 0`  en lugar de  `tx_price <= 0`
# ===========================================================================

class TestBugBackupPriceCero:

    def test_import_backup_rechaza_precio_cero(self, admin_client, seed_markets):
        """
        El precio 0 en una transacción de backup debe rechazarse igual que
        lo hace el endpoint POST /portfolio/{pos_id}/transactions.
        """
        resp = admin_client.post("/api/securities", json={
            "name": "Acme Corp", "yahoo_ticker": "ACME.MC",
            "market": "ibex35", "currency": "EUR",
        })
        assert resp.status_code == 201

        backup = {
            "version": "1",
            "exported_at": "2024-01-01T00:00:00",
            "positions": [{
                "security_ticker": "ACME.MC",
                "transactions": [{
                    "type": "buy", "date": "2024-01-01",
                    "shares": "100", "price": "0",   # ← precio inválido
                    "fee": "0", "currency": "EUR", "exchange_rate": "1",
                }],
                "dividends": [],
            }],
        }
        r = admin_client.post("/api/backup/import", json=backup)
        assert r.status_code == 200, r.text
        result = r.json()
        assert result["transactions_added"] == 0, (
            f"Bug: se insertó una transacción con price=0 "
            f"(errores: {result['errors']})"
        )
        assert any("price" in e.lower() or "precio" in e.lower()
                   for e in result["errors"]), (
            f"Bug: el error debería mencionar 'price'/'precio'; errores={result['errors']}"
        )

    def test_import_admin_rechaza_precio_cero(self, admin_client, seed_markets):
        """
        Mismo control de validación en el backup de administrador.
        """
        # Crear un valor como admin
        resp = admin_client.post("/api/securities", json={
            "name": "Beta SA", "yahoo_ticker": "BETA.MC",
            "market": "ibex35", "currency": "EUR",
        })
        assert resp.status_code == 201

        backup = {
            "version": "admin_1",
            "exported_at": "2024-01-01T00:00:00",
            "users": [{"username": "adminuser", "password_hash": "x", "is_admin": True}],
            "securities": [{"yahoo_ticker": "BETA.MC", "name": "Beta SA",
                            "currency": "EUR", "market": "ibex35"}],
            "portfolios": [{
                "username": "adminuser",
                "positions": [{
                    "security_ticker": "BETA.MC",
                    "transactions": [{
                        "type": "buy", "date": "2024-01-01",
                        "shares": "50", "price": "0",  # ← precio inválido
                        "fee": "0", "currency": "EUR", "exchange_rate": "1",
                    }],
                    "dividends": [],
                }],
                "favorites": [],
            }],
        }
        r = admin_client.post("/api/admin/backup/import", json=backup)
        assert r.status_code == 200, r.text
        result = r.json()
        assert result["transactions_added"] == 0, (
            f"Bug: se insertó una transacción con price=0 en backup admin"
        )


# ===========================================================================
# BUG 3 — Backup import: transacción USD con exchange_rate=1 no se valida,
#          se inserta en la BD y rompe la carga de la cartera.
#
# Dónde:   api/backup.py → import_backup()
#          api/admin.py  → admin_import_backup()
# Síntoma: POST /backup/import acepta una compra USD con rate=1; cuando
#          después se llama GET /portfolio, el repositorio lanza ValueError
#          ("currency='USD' con exchange_rate=1 es sospechoso") y el
#          endpoint devuelve 500.
# Causa:   la validación de coherencia divisa/rate solo existe en
#          PortfolioRepository._check_currency_consistency, no en backup.
# ===========================================================================

class TestBugBackupUsdRateUno:

    def test_import_backup_rechaza_usd_con_rate_uno(self, admin_client, seed_markets):
        """
        Una compra en USD con exchange_rate=1 debe rechazarse en el import,
        no insertarse silenciosamente para romper GET /portfolio después.
        """
        resp = admin_client.post("/api/securities", json={
            "name": "Apple Inc", "yahoo_ticker": "AAPL",
            "market": "nasdaq", "currency": "USD",
        })
        assert resp.status_code == 201, resp.text

        backup = {
            "version": "1",
            "exported_at": "2024-01-01T00:00:00",
            "positions": [{
                "security_ticker": "AAPL",
                "transactions": [{
                    "type": "buy", "date": "2024-01-01",
                    "shares": "10", "price": "150",
                    "fee": "0",
                    "currency": "USD",
                    "exchange_rate": "1",  # ← incoherente con USD
                }],
                "dividends": [],
            }],
        }
        r = admin_client.post("/api/backup/import", json=backup)
        assert r.status_code == 200, r.text
        result = r.json()

        # La transacción no debe haberse insertado
        assert result["transactions_added"] == 0, (
            f"Bug: se insertó transacción USD con rate=1; "
            f"el portfolio se romperá al cargarse. Errores: {result['errors']}"
        )
        # Debe haber un error explicativo
        assert result["errors"], (
            "Bug: no se reportó ningún error para la transacción USD con rate=1"
        )

    def test_portfolio_no_se_rompe_tras_import_invalido(self, admin_client, seed_markets):
        """
        GET /portfolio debe devolver 200 aunque hubiese algún intento de
        importar datos incoherentes (el import debe haberlos rechazado).
        """
        resp = admin_client.post("/api/securities", json={
            "name": "Microsoft", "yahoo_ticker": "MSFT",
            "market": "nasdaq", "currency": "USD",
        })
        assert resp.status_code == 201

        # Intentar importar transacción USD con rate=1
        backup = {
            "version": "1",
            "exported_at": "2024-01-01T00:00:00",
            "positions": [{
                "security_ticker": "MSFT",
                "transactions": [{
                    "type": "buy", "date": "2024-01-01",
                    "shares": "5", "price": "300",
                    "fee": "0", "currency": "USD", "exchange_rate": "1",
                }],
                "dividends": [],
            }],
        }
        admin_client.post("/api/backup/import", json=backup)

        # El portfolio no debe fallar (si el import rechazó la tx correctamente)
        r = admin_client.get("/api/portfolio")
        assert r.status_code == 200, (
            f"Bug: GET /portfolio devuelve {r.status_code} (500) porque se insertó "
            f"una transacción USD incoherente que el import debería haber rechazado"
        )


# ===========================================================================
# BUG 4 — Backup import: la clave de deduplicación de transacciones no
#          incluye la comisión ni el tipo de cambio.
#
# Dónde:   api/backup.py → import_backup()
#          api/admin.py  → admin_import_backup()
# Síntoma: si existe una transacción (fecha, tipo, shares, price, fee=5) y
#          se importa otra transacción idéntica salvo fee=8, la segunda se
#          omite silenciosamente (pérdida de datos).
# Causa:   existing_txs = {(date, type, shares, price)} — falta fee y rate.
# ===========================================================================

class TestBugBackupDedupFee:

    def test_dos_compras_misma_fecha_precio_distinto_fee_se_importan(
        self, admin_client, seed_markets
    ):
        """
        Dos compras el mismo día, mismas acciones y precio, pero comisiones
        distintas (fee=5.7 vs fee=8.3) son transacciones DISTINTAS.

        Escenario: la posición ya tiene fee=5.7; el backup trae las dos.
        Solo debe añadirse fee=8.3 (idempotencia: fee=5.7 ya existe).

        Usamos price=7.53 y shares=15.5 (valores sin trailing-zero en float)
        para evitar que la comparación Decimal falle por representación.

        Bug anterior: la clave de dedup era (date, type, shares, price) sin fee.
        Dos transacciones con la misma (date, type, shares, price) y distinta
        fee compartían clave, así que la segunda se omitía silenciosamente.
        """
        resp = admin_client.post("/api/securities", json={
            "name": "Gamma Corp", "yahoo_ticker": "GAM.MC",
            "market": "ibex35", "currency": "EUR",
        })
        assert resp.status_code == 201
        sec_id = resp.json()["id"]

        pos_resp = admin_client.post("/api/portfolio/positions",
                                     json={"security_id": sec_id})
        assert pos_resp.status_code == 201
        pos_id = pos_resp.json()["id"]

        # Transacción ya existente: fee=5.7
        admin_client.post(f"/api/portfolio/{pos_id}/transactions", json={
            "type": "buy", "date": "2024-01-01",
            "shares": "15.5", "price": "7.53",
            "fee": "5.7",
            "currency": "EUR", "exchange_rate": "1",
        })

        # Importar backup con fee=5.7 (ya existe) Y fee=8.3 (nueva)
        backup = {
            "version": "1",
            "exported_at": "2024-01-01T00:00:00",
            "positions": [{
                "security_ticker": "GAM.MC",
                "transactions": [
                    {
                        "type": "buy", "date": "2024-01-01",
                        "shares": "15.5", "price": "7.53",
                        "fee": "5.7",   # ← ya existe
                        "currency": "EUR", "exchange_rate": "1",
                    },
                    {
                        "type": "buy", "date": "2024-01-01",
                        "shares": "15.5", "price": "7.53",
                        "fee": "8.3",   # ← diferente → transacción distinta
                        "currency": "EUR", "exchange_rate": "1",
                    },
                ],
                "dividends": [],
            }],
        }
        r = admin_client.post("/api/backup/import", json=backup)
        assert r.status_code == 200, r.text
        result = r.json()

        # Solo debe añadirse la de fee=8.3
        assert result["transactions_added"] == 1, (
            f"Bug: se añadieron {result['transactions_added']} transacciones. "
            f"Debería ser 1 (solo fee=8.3). "
            f"Si es 0: la de fee=8.3 fue omitida por la clave de dedup sin fee."
        )

        # Ahora debe haber exactamente 2 transacciones
        txs_resp = admin_client.get(f"/api/portfolio/{pos_id}/transactions")
        assert len(txs_resp.json()) == 2, (
            f"Hay {len(txs_resp.json())} transacciones; deberían ser 2"
        )


# ===========================================================================
# BUG 5 — get_closed_positions: shares_sold usa shares crudas (pre-split),
#          no el equivalente post-split.
#
# Dónde:   api/portfolio.py → get_closed_positions()
# Síntoma: para una posición cerrada con ventas realizadas ANTES de un split,
#          shares_sold muestra la mezcla de unidades pre- y post-split,
#          dando un total incorrecto.
# Causa:   shares_sold = sum(tx.shares for tx in txs if tx.type=="sell")
#          'txs' son las transacciones crudas, sin normalizar por splits.
#          Debería derivarse de computed.sale_matches (que sí están
#          normalizados a equivalente post-split).
#
# Ejemplo:
#   Compra 100 acc; venta 30 acc (pre-split); split 2:1; venta 140 acc.
#   Shares normalizadas: buy→200, sell1→60, sell2→140. Total cerrado: 200.
#   Con el bug: shares_sold = 30 + 140 = 170  (incorrecto)
#   Correcto:   shares_sold = 60 + 140 = 200
# ===========================================================================

class TestBugClosedPositionSharesSold:

    def test_shares_sold_correctas_con_split(self, admin_client, seed_markets):
        """
        Posición:
          1. Compra 100 acc × 10 €.
          2. Venta  30 acc × 12 € (pre-split).
          3. Split 2:1.
          4. Venta 140 acc × 6 € (post-split, equivalen a 70 pre-split).
          → Posición cerrada (100-30-70 = 0 pre-split ≡ 200-60-140 = 0 post).

        El total de shares_sold en equivalente post-split = 60 + 140 = 200.
        Con el bug: 30 + 140 = 170.
        """
        # Crear valor y posición
        resp = admin_client.post("/api/securities", json={
            "name": "Delta SA", "yahoo_ticker": "DELTA.MC",
            "market": "ibex35", "currency": "EUR",
        })
        assert resp.status_code == 201
        sec_id = resp.json()["id"]

        pos_resp = admin_client.post("/api/portfolio/positions",
                                     json={"security_id": sec_id})
        assert pos_resp.status_code == 201
        pos_id = pos_resp.json()["id"]

        # 1. Compra 100 acc
        admin_client.post(f"/api/portfolio/{pos_id}/transactions", json={
            "type": "buy", "date": "2024-01-10",
            "shares": "100", "price": "10.00",
            "fee": "0", "currency": "EUR", "exchange_rate": "1",
        })

        # 2. Venta 30 acc pre-split
        r = admin_client.post(f"/api/portfolio/{pos_id}/transactions", json={
            "type": "sell", "date": "2024-03-01",
            "shares": "30", "price": "12.00",
            "fee": "0", "currency": "EUR", "exchange_rate": "1",
        })
        assert r.status_code == 201

        # 3. Split 2:1
        admin_client.post(f"/api/admin/securities/{sec_id}/splits", json={
            "ex_date": "2024-06-01", "ratio_num": 2, "ratio_den": 1,
        })

        # 4. Venta 140 acc post-split
        r = admin_client.post(f"/api/portfolio/{pos_id}/transactions", json={
            "type": "sell", "date": "2024-09-01",
            "shares": "140", "price": "6.00",
            "fee": "0", "currency": "EUR", "exchange_rate": "1",
        })
        assert r.status_code == 201

        # La posición debe estar cerrada
        r = admin_client.get("/api/portfolio/closed")
        assert r.status_code == 200
        closed = r.json()
        assert len(closed) == 1, "La posición debería aparecer en cerradas"

        shares_sold = Decimal(closed[0]["shares_sold"])
        assert shares_sold == Decimal("200"), (
            f"Bug: shares_sold={shares_sold} pero debería ser 200 "
            f"(equivalente post-split: 60 + 140). "
            f"Con el bug aparece 170 (pre+post mezclados: 30 + 140)."
        )


# ===========================================================================
# BUG 6 — _is_loss_disallowed: descarta TODAS las compras de la fecha
#          emparejada, no solo la compra emparejada con la venta.
#
# Dónde:   services/tax_report.py → _is_loss_disallowed()
# Síntoma: si hay dos compras el mismo día y una de ellas es la emparejada
#          por FIFO con la venta con pérdida, la OTRA compra del mismo día
#          también se descarta aunque debería activar la regla de recompra.
# Causa:   `if buy.date == match.buy_date: continue`
#          salta TODAS las compras de esa fecha, no solo la 1ª (la emparejada).
#
# Ejemplo:
#   Compra A: 10 acc el 2023-01-10 (emparejada con la venta)
#   Compra B:  5 acc el 2023-01-10 (mismo día, DISTINTA compra → recompra)
#   Venta   : 10 acc el 2023-02-01 con pérdida
#   La Compra B está dentro de los 60 días de la venta → debería activar
#   la regla. Con el bug, B se salta porque su fecha == match.buy_date.
# ===========================================================================

IBEX_REF = SecurityRef(1, "Iberdrola", "ES0144580Y14", "ibex35",
                       fiscal_window_days=60)


def _sm(sell_d: date, buy_d: date, gain: str) -> SaleMatch:
    """SaleMatch mínimo con ganancia dada (positiva=ganancia, negativa=pérdida)."""
    gain_d = D(gain)
    cost = D("200")
    proceeds = cost + gain_d
    return SaleMatch(
        sell_date=sell_d, buy_date=buy_d, shares=D("10"),
        cost_native=cost, cost_eur=cost,
        proceeds_native=proceeds, proceeds_eur=proceeds,
        gain_native=gain_d, gain_eur=gain_d,
    )


class TestBugRecompraDosBuysMismaFecha:

    def test_recompra_detectada_cuando_segunda_compra_misma_fecha(self):
        """
        Dos compras el mismo día (2023-01-10):
          - Compra A: 10 acc (esta es la emparejada por FIFO con la venta)
          - Compra B:  5 acc (no emparejada, pero dentro del plazo de 60 días)

        Venta: 10 acc el 2023-02-01 con pérdida.

        La Compra B está dentro del plazo [2023-02-01 - 60d, 2023-02-01 + 60d].
        Debe activar la regla de recompra. Con el bug no la activa porque
        toda fecha 2023-01-10 se descarta en el bucle.
        """
        buy_date = date(2023, 1, 10)
        sell_date = date(2023, 2, 1)  # 22 días después de las compras

        match = _sm(sell_date, buy_date, "-50")  # pérdida de 50 €

        all_buys = [
            # Compra A: la emparejada (10 acc)
            Transaction("buy", buy_date, D("10"), D("20"), D("0"), D("1")),
            # Compra B: distinta compra el mismo día (5 acc) → DEBERÍA ser recompra
            Transaction("buy", buy_date, D("5"),  D("20"), D("0"), D("1")),
        ]

        sales = [SecuritySales(IBEX_REF, [match], all_buys=all_buys)]
        report = build_tax_report(2023, sales, [])

        assert len(report.sale_lines) == 1
        line = report.sale_lines[0]

        assert line.loss_disallowed is True, (
            f"Bug: la pérdida no se marcó como no computable "
            f"(la Compra B del mismo día debería activar la regla de recompra, "
            f"pero se descartó junto con la Compra A porque share la misma fecha)"
        )
        assert report.total_losses_disallowed_eur == D("-50"), (
            f"Bug: total_losses_disallowed_eur={report.total_losses_disallowed_eur} "
            f"debería ser -50"
        )

    def test_compra_emparejada_sola_no_activa_recompra(self):
        """
        Control: solo hay UNA compra en la fecha emparejada. En ese caso,
        la regla de recompra NO debe activarse (la compra emparejada no
        cuenta como "recompra").
        """
        buy_date = date(2023, 1, 10)
        sell_date = date(2023, 2, 1)

        match = _sm(sell_date, buy_date, "-50")

        all_buys = [
            # Solo la compra emparejada — no hay recompra
            Transaction("buy", buy_date, D("10"), D("20"), D("0"), D("1")),
        ]

        sales = [SecuritySales(IBEX_REF, [match], all_buys=all_buys)]
        report = build_tax_report(2023, sales, [])

        assert report.sale_lines[0].loss_disallowed is False, (
            "La compra emparejada no debe contar como recompra"
        )
        assert report.total_losses_computable_eur == D("-50")


# ===========================================================================
# BUG 7 — Backup import: validación de divisa/cambio no cubre la coherencia
#          completa (USD con rate=1 almacena datos que rompen el cálculo).
#          Test adicional a nivel de cálculo puro para verificar la detección.
# ===========================================================================

class TestBugCoherenciaDivisaCalculo:

    def test_to_eur_con_rate_cero_lanza_error(self):
        """to_eur debe rechazar exchange_rate=0 para evitar división por cero."""
        with pytest.raises(ValueError, match="0"):
            to_eur(D("100"), D("0"))

    def test_compute_position_con_exchange_rate_coherente(self):
        """Smoke test: posición EUR simple no debe fallar."""
        txs = [Transaction("buy", date(2024, 1, 1), D("10"), D("100"), D("0"), D("1"))]
        r = compute_position(txs, [])
        assert r.current_shares == D("10")
        assert r.invested_eur == D("1000")


# ===========================================================================
# BUG 8 — Valores muy ilíquidos sin snapshot (tarjetas vacías, gráfico OK).
#   Yahoo solo publica UN cierre para algunos valores del Continuo (p. ej.
#   NXTE.XD: una sola barra, 2026-06-15). fetch_live_quote exigía len(df) >= 2
#   para poder calcular prev_close y la variación del día, y lanzaba ValueError
#   si solo había una barra. Resultado: _update_snapshot_for_security fallaba,
#   nunca se escribía price_snapshots y las tarjetas (precio, %, Mín./Máx.) no
#   se mostraban — aunque el gráfico histórico sí, porque lee price_history.
#   Corrección: con una sola barra se devuelve la cotización igualmente, con
#   prev_close=None y daily_change_pct=None (variación "—" en la UI).
# ===========================================================================

class TestBugValorIliquidoUnaBarra:

    def _single_row_df(self, close: float):
        import pandas as pd
        idx = pd.DatetimeIndex([pd.Timestamp("2026-06-15", tz="Europe/Madrid")])
        return pd.DataFrame({"Close": [close], "Volume": [0]}, index=idx)

    def test_fetch_live_quote_una_sola_barra(self, monkeypatch):
        """Una única barra → LiveQuote con prev_close y pct None (no ValueError)."""
        import pandas as pd
        from app.providers import yahoo
        from app.providers.yahoo import YahooProvider

        df = self._single_row_df(1.024)

        class FakeTicker:
            def __init__(self, ticker): pass
            def history(self, *a, **k): return df
            @property
            def dividends(self): return pd.Series(dtype="float64")

        monkeypatch.setattr(yahoo.yf, "Ticker", FakeTicker)

        quote = YahooProvider().fetch_live_quote("NXTE.XD")
        # last_price = la única barra; sin día anterior no hay variación.
        assert float(quote.last_price) == 1.024
        assert quote.prev_close is None
        assert quote.daily_change_pct is None

    def test_update_snapshot_se_crea_con_una_barra(self, admin_client, seed_markets, engine, monkeypatch):
        """
        _update_snapshot_for_security crea el snapshot aunque el quote solo
        tenga last_price (prev_close/pct None), tomando los rangos Mín./Máx. de
        price_history. Antes no se escribía nada y la ficha quedaba sin tarjetas.
        """
        from sqlalchemy.orm import Session
        from app.models import PriceHistory, PriceSnapshot, Security
        from app.providers.base import LiveQuote
        from app.scheduler import jobs

        sec = admin_client.post("/api/securities", json={
            "name": "Nueva Expresion Textil", "yahoo_ticker": "NXTE.XD",
            "market": "continuo", "currency": "EUR",
        }).json()["id"]
        with Session(engine) as s:
            # Histórico esparcido (el gráfico funciona con esto):
            s.add(PriceHistory(security_id=sec, date="2026-06-04", close=D("0.977")))
            s.add(PriceHistory(security_id=sec, date="2026-06-15", close=D("1.024")))
            s.commit()

        # Quote de un valor ilíquido: solo last_price.
        def fake_quote(ticker, with_dividends=True):
            return LiveQuote(
                last_price=D("1.024"), prev_close=None,
                daily_change_pct=None, last_dividend=None,
                quote_time="2026-06-15T00:00:00+00:00",
            )
        monkeypatch.setattr(jobs._yahoo, "fetch_live_quote", fake_quote)

        with Session(engine) as s:
            secrow = s.get(Security, sec)
            jobs._update_snapshot_for_security(s, secrow)
            snap = s.get(PriceSnapshot, sec)
            assert snap is not None, "El snapshot debe crearse aunque solo haya una barra"
            assert float(snap.last_price) == 1.024
            assert snap.prev_close is None
            assert snap.daily_change_pct is None
            # Rangos desde price_history: mín 0.977, máx 1.024
            assert float(snap.min_1y) == 0.977
            assert float(snap.max_1y) == 1.024
