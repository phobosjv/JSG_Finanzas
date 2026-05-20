"""
test_portfolio_repository.py
============================
Tests de la capa repositorio: el puente entre SQLite y la logica verificada.

Que se verifica (lo no trivial):
  * El ciclo Decimal: un importe escrito sale como Decimal LIMPIO, sin el
    ruido binario del REAL de SQLite.
  * La traduccion fecha texto 'YYYY-MM-DD' <-> objeto date.
  * La validacion de coherencia currency / exchange_rate.
  * Los dos metodos de transacciones (por posicion / compras por valor).
  * La integracion real: el output del repositorio alimenta
    compute_position y build_tax_report y produce las cifras esperadas.

Ejecutar:  pytest backend_tests/test_portfolio_repository.py -v
"""

from datetime import date
from decimal import Decimal

import pytest

from app.models import (
    User, Security, Position, TransactionRow, DividendRow,
)
from app.repositories.portfolio_repository import PortfolioRepository
from app.repositories.tax_report_input import build_tax_report_input
from app.services.calculations import compute_position
from app.services.tax_report import build_tax_report


def D(x: str) -> Decimal:
    return Decimal(x)


# --------------------------------------------------------------------------
#  Ayudas: poblar la BD en memoria
# --------------------------------------------------------------------------

def make_user(db, username="ana"):
    u = User(username=username, password_hash="x")
    db.add(u)
    db.flush()
    return u


def make_security(db, name="Iberdrola", market="ibex35",
                  currency="EUR", ticker="IBE.MC", isin="ES0144580Y14"):
    s = Security(name=name, isin=isin, yahoo_ticker=ticker,
                 market=market, currency=currency)
    db.add(s)
    db.flush()
    return s


def make_position(db, user, security):
    p = Position(user_id=user.id, security_id=security.id)
    db.add(p)
    db.flush()
    return p


def add_tx(db, position, type_, d, shares, price, fee="0",
           currency="EUR", rate="1"):
    row = TransactionRow(
        position_id=position.id, type=type_, date=d,
        shares=D(shares), price=D(price), fee=D(fee),
        currency=currency, exchange_rate=D(rate),
    )
    db.add(row)
    db.flush()
    return row


def add_div(db, position, d, shares_at, gross_ps, gross, wh="0",
            currency="EUR", rate="1"):
    row = DividendRow(
        position_id=position.id, date=d,
        shares_at_date=D(shares_at), gross_per_share=D(gross_ps),
        gross_amount=D(gross), withholding_tax=D(wh),
        currency=currency, exchange_rate=D(rate),
    )
    db.add(row)
    db.flush()
    return row


# --------------------------------------------------------------------------
#  1. El ciclo Decimal: nada de ruido binario
# --------------------------------------------------------------------------

def test_decimal_se_conserva_limpio(db):
    """
    Un importe con decimales se escribe y se lee de vuelta. Debe salir como
    Decimal numericamente EXACTO, no como Decimal('100.09999999999999')
    arrastrando ruido binario del REAL de SQLite. Es la prueba del tipo
    Money: la lectura pasa por str(float), que elimina ese ruido.

    Limite conocido y aceptado: el camino Decimal -> float -> Decimal NO
    preserva los ceros finales (100.10 se relee como 100.1). El VALOR es
    identico y la aritmetica Decimal exacta; solo se pierde la "escala"
    textual. Es inherente a almacenar dinero en una columna REAL de SQLite.
    No afecta al calculo (100.1 == 100.10) ni a la presentacion
    (_fmt_money hace quantize a 2 decimales). Por eso se comprueba igualdad
    numerica, NO la cadena.
    """
    u = make_user(db)
    s = make_security(db)
    p = make_position(db, u, s)
    add_tx(db, p, "buy", "2023-01-10", "10", "100.10", fee="5.07")

    repo = PortfolioRepository(db)
    txs = repo.transactions_for_position(p.id)

    assert len(txs) == 1
    tx = txs[0]
    assert isinstance(tx.price, Decimal)
    assert isinstance(tx.fee, Decimal)
    # Igualdad numerica exacta: ni ruido binario, ni aproximacion.
    assert tx.price == D("100.10")
    assert tx.fee == D("5.07")
    # El ruido binario se manifestaria como una cola larga de digitos.
    # Comprobacion robusta: la diferencia con el valor exacto es nula.
    assert tx.price - D("100.10") == D("0")
    # Y la aritmetica encadenada sigue siendo exacta:
    assert tx.shares * tx.price + tx.fee == D("1006.07")  # 10*100.10 + 5.07


def test_fechas_texto_se_convierten_a_date(db):
    """La columna date es texto 'YYYY-MM-DD'; el objeto Transaction lleva date."""
    u = make_user(db)
    s = make_security(db)
    p = make_position(db, u, s)
    add_tx(db, p, "buy", "2023-03-15", "5", "20")

    tx = PortfolioRepository(db).transactions_for_position(p.id)[0]
    assert tx.date == date(2023, 3, 15)
    assert isinstance(tx.date, date)


# --------------------------------------------------------------------------
#  2. Validacion de coherencia currency / exchange_rate
# --------------------------------------------------------------------------

def test_eur_con_rate_distinto_de_uno_falla(db):
    """currency='EUR' con exchange_rate != 1 es dato corrupto: debe fallar."""
    u = make_user(db)
    s = make_security(db)
    p = make_position(db, u, s)
    add_tx(db, p, "buy", "2023-01-01", "10", "100",
           currency="EUR", rate="1.08")  # incoherente

    with pytest.raises(ValueError, match="EUR"):
        PortfolioRepository(db).transactions_for_position(p.id)


def test_usd_con_rate_uno_falla(db):
    """currency='USD' con exchange_rate=1 es sospechoso: debe fallar."""
    u = make_user(db)
    s = make_security(db, name="Apple", market="nasdaq",
                      currency="USD", ticker="AAPL", isin="US0378331005")
    p = make_position(db, u, s)
    add_tx(db, p, "buy", "2023-01-01", "10", "150",
           currency="USD", rate="1")  # incoherente

    with pytest.raises(ValueError, match="USD"):
        PortfolioRepository(db).transactions_for_position(p.id)


def test_usd_coherente_pasa(db):
    """currency='USD' con rate real: la transaccion se construye sin error."""
    u = make_user(db)
    s = make_security(db, name="Apple", market="nasdaq",
                      currency="USD", ticker="AAPL", isin="US0378331005")
    p = make_position(db, u, s)
    add_tx(db, p, "buy", "2023-01-01", "10", "150",
           currency="USD", rate="1.10")

    tx = PortfolioRepository(db).transactions_for_position(p.id)[0]
    assert tx.exchange_rate == D("1.10")


# --------------------------------------------------------------------------
#  3. Los dos metodos de transacciones
# --------------------------------------------------------------------------

def test_transactions_for_position_devuelve_solo_su_posicion(db):
    """transactions_for_position no se contamina con otras posiciones."""
    u = make_user(db)
    s1 = make_security(db, ticker="IBE.MC")
    s2 = make_security(db, name="BBVA", ticker="BBVA.MC", isin="ES0113211835")
    p1 = make_position(db, u, s1)
    p2 = make_position(db, u, s2)
    add_tx(db, p1, "buy", "2023-01-01", "10", "100")
    add_tx(db, p2, "buy", "2023-01-01", "99", "5")

    txs = PortfolioRepository(db).transactions_for_position(p1.id)
    assert len(txs) == 1
    assert txs[0].shares == D("10")


def test_all_buys_for_security_solo_compras_de_cualquier_ano(db):
    """
    all_buys_for_security devuelve SOLO las compras, de cualquier ejercicio,
    y excluye las ventas. Lo necesita la regla de recompra de tax_report.
    """
    u = make_user(db)
    s = make_security(db)
    p = make_position(db, u, s)
    add_tx(db, p, "buy",  "2020-01-01", "10", "100")
    add_tx(db, p, "buy",  "2023-04-10", "10", "90")
    add_tx(db, p, "sell", "2023-05-01", "5", "120")  # venta: no debe salir

    buys = PortfolioRepository(db).all_buys_for_security(u.id, s.id)
    assert len(buys) == 2
    assert all(b.type == "buy" for b in buys)
    fechas = {b.date for b in buys}
    assert fechas == {date(2020, 1, 1), date(2023, 4, 10)}


# --------------------------------------------------------------------------
#  4. Dividendos
# --------------------------------------------------------------------------

def test_dividends_for_position(db):
    """Los dividendos de una posicion se traducen a objetos Dividend."""
    u = make_user(db)
    s = make_security(db)
    p = make_position(db, u, s)
    add_div(db, p, "2023-06-01", "100", "1", "100", wh="19")

    divs = PortfolioRepository(db).dividends_for_position(p.id)
    assert len(divs) == 1
    assert divs[0].date == date(2023, 6, 1)
    assert divs[0].gross_amount == D("100")
    assert divs[0].withholding_tax == D("19")


# --------------------------------------------------------------------------
#  5. Integracion: repositorio -> compute_position
# --------------------------------------------------------------------------

def test_integracion_compute_position(db):
    """
    El output del repositorio alimenta compute_position y produce las
    mismas cifras que test_calculations verifica de forma aislada.

    Compra 10 a 100, compra 10 a 200, venta 15 a 300 (sin comisiones).
    FIFO: ganancia realizada 2500, quedan 5 acciones vivas, invertido 1000.
    """
    u = make_user(db)
    s = make_security(db)
    p = make_position(db, u, s)
    add_tx(db, p, "buy",  "2023-01-01", "10", "100")
    add_tx(db, p, "buy",  "2023-02-01", "10", "200")
    add_tx(db, p, "sell", "2023-06-01", "15", "300")

    repo = PortfolioRepository(db)
    result = compute_position(
        repo.transactions_for_position(p.id),
        repo.dividends_for_position(p.id),
    )

    assert result.current_shares == D("5")
    assert result.invested_native == D("1000")
    assert result.realized_gain_native == D("2500")
    assert len(result.sale_matches) == 2


# --------------------------------------------------------------------------
#  6. Integracion completa: repositorio -> build_tax_report
# --------------------------------------------------------------------------

def test_integracion_informe_fiscal_completo(db):
    """
    Flujo completo: build_tax_report_input arma los SecuritySales (con sus
    matches via FIFO) y los DividendRecord; build_tax_report produce el
    informe del ejercicio.

    Escenario IBEX: compra 10 a 100 en 2020, venta 10 a 180 en 2023 -> +800.
    Dividendo de 2023: bruto 100, retencion 19, neto 81.
    """
    u = make_user(db)
    s = make_security(db)
    p = make_position(db, u, s)
    add_tx(db, p, "buy",  "2020-01-01", "10", "100")
    add_tx(db, p, "sell", "2023-05-01", "10", "180")
    add_div(db, p, "2023-06-01", "10", "10", "100", wh="19")

    sales, dividends = build_tax_report_input(db, u.id)
    report = build_tax_report(2023, sales, dividends)

    assert len(report.sale_lines) == 1
    assert report.total_gains_eur == D("800")
    assert report.net_capital_result_eur == D("800")
    assert len(report.dividend_lines) == 1
    assert report.total_dividends_net_eur == D("81")


def test_integracion_regla_recompra_via_repositorio(db):
    """
    La regla de recompra se activa con datos reales de SQLite.

    Venta con perdida en marzo 2023; recompra del mismo valor en abril 2023
    (dentro de los 2 meses del IBEX). all_buys_for_security debe traer esa
    recompra y build_tax_report debe marcar la perdida como no computable.

    Aritmetica: 10 acciones, coste 10*200=2000, venta 10*150=1500 -> -500.
    """
    u = make_user(db)
    s = make_security(db)  # IBEX -> ventana de 2 meses
    p = make_position(db, u, s)
    add_tx(db, p, "buy",  "2020-01-01", "10", "200")  # compra emparejada
    add_tx(db, p, "sell", "2023-03-01", "10", "150")  # venta con perdida -500
    add_tx(db, p, "buy",  "2023-04-10", "10", "150")  # recompra: activa regla

    sales, dividends = build_tax_report_input(db, u.id)
    report = build_tax_report(2023, sales, dividends)

    assert report.sale_lines[0].loss_disallowed is True
    assert report.total_losses_disallowed_eur == D("-500")
    assert report.total_losses_computable_eur == D("0")
    assert report.net_capital_result_eur == D("0")


def test_foreign_keys_activas(db):
    """
    PRAGMA foreign_keys ON: insertar una transaccion con position_id
    inexistente debe fallar. Confirma que el conftest aplica el PRAGMA.
    """
    from sqlalchemy.exc import IntegrityError

    db.add(TransactionRow(
        position_id=9999, type="buy", date="2023-01-01",
        shares=D("1"), price=D("1"), fee=D("0"),
        currency="EUR", exchange_rate=D("1"),
    ))
    with pytest.raises(IntegrityError):
        db.flush()
