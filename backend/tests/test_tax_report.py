"""Tests de services/tax_report.py — verificacion del informe fiscal."""

from datetime import date
from decimal import Decimal

from app.services.calculations import SaleMatch, Transaction, Dividend
from app.services.tax_report import (
    SecurityRef, SecuritySales, DividendRecord, build_tax_report,
)


def D(x): return Decimal(x)


def sm(sell_d, buy_d, shares, cost, proceeds):
    """Construye un SaleMatch; gain = proceeds - cost (en EUR)."""
    g = D(proceeds) - D(cost)
    return SaleMatch(
        sell_date=sell_d, buy_date=buy_d, shares=D(shares),
        cost_native=D(cost), cost_eur=D(cost),
        proceeds_native=D(proceeds), proceeds_eur=D(proceeds),
        gain_native=g, gain_eur=g,
    )


def buy(d): return Transaction("buy", d, D("1"), D("1"), D("0"), D("1"))


IBEX = SecurityRef(1, "Iberdrola", "ES0144580Y14", "ibex35", fiscal_window_days=60)
NDX  = SecurityRef(2, "Apple",    "US0378331005", "nasdaq",  fiscal_window_days=365)


def test_solo_filtra_el_ano_pedido():
    """Una venta de 2022 y otra de 2023; el informe de 2023 solo ve la suya."""
    sales = [SecuritySales(IBEX, [
        sm(date(2022, 5, 1), date(2020, 1, 1), "10", "100", "150"),
        sm(date(2023, 5, 1), date(2020, 1, 1), "10", "100", "200"),
    ], all_buys=[buy(date(2020, 1, 1))])]
    r = build_tax_report(2023, sales, [])
    assert len(r.sale_lines) == 1
    assert r.sale_lines[0].sell_date.year == 2023
    assert r.total_gains_eur == D("100")  # 200 - 100


def test_ganancia_y_perdida_se_separan():
    """Una venta con ganancia y otra con perdida computable."""
    sales = [SecuritySales(IBEX, [
        sm(date(2023, 3, 1), date(2020, 1, 1), "10", "100", "180"),  # +80
        sm(date(2023, 9, 1), date(2020, 1, 1), "10", "200", "150"),  # -50
    ], all_buys=[buy(date(2020, 1, 1))])]
    r = build_tax_report(2023, sales, [])
    assert r.total_gains_eur == D("80")
    assert r.total_losses_computable_eur == D("-50")
    assert r.net_capital_result_eur == D("30")  # 80 + (-50)


def test_regla_recompra_marca_perdida_ibex():
    """
    Venta con perdida en marzo 2023. Hay una recompra del mismo valor en
    abril 2023, dentro de los dos meses. La perdida debe marcarse y NO
    entrar en el saldo computable.
    """
    sales = [SecuritySales(IBEX, [
        sm(date(2023, 3, 1), date(2020, 1, 1), "10", "200", "150"),  # -50
    ], all_buys=[
        buy(date(2020, 1, 1)),   # la compra emparejada, no cuenta
        buy(date(2023, 4, 10)),  # recompra dentro de 2 meses -> activa la regla
    ])]
    r = build_tax_report(2023, sales, [])
    assert r.sale_lines[0].loss_disallowed is True
    assert r.total_losses_disallowed_eur == D("-50")
    assert r.total_losses_computable_eur == D("0")
    assert r.net_capital_result_eur == D("0")  # la perdida no computa


def test_regla_recompra_no_aplica_fuera_de_plazo():
    """Recompra 6 meses despues: para IBEX (2 meses) NO activa la regla."""
    sales = [SecuritySales(IBEX, [
        sm(date(2023, 3, 1), date(2020, 1, 1), "10", "200", "150"),  # -50
    ], all_buys=[
        buy(date(2020, 1, 1)),
        buy(date(2023, 9, 1)),  # 6 meses despues, fuera de los 2 meses
    ])]
    r = build_tax_report(2023, sales, [])
    assert r.sale_lines[0].loss_disallowed is False
    assert r.total_losses_computable_eur == D("-50")


def test_nasdaq_plazo_un_ano():
    """
    Mismo escenario que el anterior (recompra 6 meses despues) pero en
    Nasdaq: el plazo es de un ano, asi que la regla SI se activa.
    """
    sales = [SecuritySales(NDX, [
        sm(date(2023, 3, 1), date(2020, 1, 1), "10", "200", "150"),  # -50
    ], all_buys=[
        buy(date(2020, 1, 1)),
        buy(date(2023, 9, 1)),  # 6 meses: dentro del ano para Nasdaq
    ])]
    r = build_tax_report(2023, sales, [])
    assert r.sale_lines[0].loss_disallowed is True
    assert r.net_capital_result_eur == D("0")


def test_dividendos_separados_de_ganancias():
    """Los dividendos van a su propio bloque, con bruto/retencion/neto."""
    divs = [
        DividendRecord(IBEX, Dividend(date(2023, 6, 1), D("100"), D("100"), D("19"), D("1"))),
        DividendRecord(NDX, Dividend(date(2023, 7, 1), D("50"), D("30"), D("4.5"), D("1.10"))),
    ]
    r = build_tax_report(2023, [], divs)
    assert len(r.dividend_lines) == 2
    # IBEX: bruto 100, retencion 19, neto 81 (rate 1)
    # Nasdaq: bruto 30/1.10=27.2727, retencion 4.5/1.10=4.0909, neto 23.1818
    assert abs(r.total_dividends_gross_eur - D("127.2727")) < D("0.001")
    assert abs(r.total_dividends_net_eur - D("104.1818")) < D("0.001")


def test_avisos_presentes():
    """El informe siempre lleva el aviso de 'orientativo'."""
    r = build_tax_report(2023, [], [])
    assert any("orientativo" in w for w in r.warnings)


def test_avisos_estimacion_solo_con_base():
    """
    Los avisos sobre alcance de la cuota (sin compensación 25 % / arrastre) y
    sobre el reparto orientativo aparecen solo si hay base imponible.
    """
    from app.services.pdf_generator import _build_context

    # Con ganancia → hay base → avisos presentes
    sales = [SecuritySales(IBEX, [
        sm(date(2023, 5, 1), date(2020, 1, 1), "10", "100", "200"),
    ], all_buys=[buy(date(2020, 1, 1))])]
    ws = _build_context(build_tax_report(2023, sales, []), lang="es")["warnings"]
    assert any("25 %" in w for w in ws)
    assert any("no sumar exactamente" in w for w in ws)

    # Sin operaciones → sin base → no aparecen
    ws_empty = _build_context(build_tax_report(2023, [], []), lang="es")["warnings"]
    assert not any("25 %" in w for w in ws_empty)


# --- v1.8.9: las ventas de fondos van en su propia sección (Bloque 4) ---

FONDO = SecurityRef(3, "Bulnes FI", "ES0000000003", "fondos",
                    fiscal_window_days=60, is_fund_market=True)


def test_fondos_en_seccion_aparte_del_pdf():
    """
    Las ventas de fondos NO aparecen en el Bloque 1/2 (acciones) sino en el
    Bloque 4 (fund_lines), y los movimientos de fondos no se detallan.
    """
    from app.services.pdf_generator import _build_context

    sales = [
        SecuritySales(IBEX, [
            sm(date(2023, 5, 1), date(2020, 1, 1), "10", "100", "200"),  # +100 acción
        ], all_buys=[buy(date(2020, 1, 1))]),
        SecuritySales(FONDO, [
            sm(date(2023, 6, 1), date(2021, 1, 1), "50", "500", "650"),  # +150 fondo
        ], all_buys=[buy(date(2021, 1, 1))]),
    ]
    r = build_tax_report(2023, sales, [])
    ctx = _build_context(r, lang="es")

    # Bloque 1 (acciones): solo Iberdrola, sin el fondo
    nombres_acc = {l["security_name"] for l in ctx["sale_lines"]}
    assert "Iberdrola" in nombres_acc
    assert all("Bulnes" not in n for n in nombres_acc)

    # Bloque 2 (movimientos): no detalla el fondo
    assert all("Bulnes" not in m["security_name"] for m in ctx["movement_lines"])

    # Bloque 4 (fondos): aparece el fondo, sin sufijo «(F)» (redundante aquí)
    nombres_fondo = {l["security_name"] for l in ctx["fund_lines"]}
    assert nombres_fondo == {"Bulnes FI"}
    # Resultado del fondo +150 €
    assert ctx["fund_totals"]["gains"] == "150,00"
    # El resumen ejecutivo sigue agregando acción + fondo: 100 + 150 = 250
    assert ctx["summary"]["net_capital"] == "250,00"
    # La tarjeta de ventas muestra SOLO acciones; la de fondos, solo fondos
    assert ctx["summary"]["net_sales"] == "100,00"
    assert ctx["summary"]["fund_net"] == "150,00"


def test_resumen_cuota_por_componente():
    """
    Cada tarjeta de ganancia lleva su cuota estimada = importe × tipo efectivo.
    Acción +100, fondo +150, sin dividendos. Base = 250.
    Con el primer tramo al 19% (250 < 6.000), cuota total = 47,50 y tipo
    efectivo = 19%. Cuota ventas = 100×19% = 19,00; fondos = 150×19% = 28,50.
    """
    from app.services.pdf_generator import _build_context

    sales = [
        SecuritySales(IBEX, [
            sm(date(2023, 5, 1), date(2020, 1, 1), "10", "100", "200"),  # +100
        ], all_buys=[buy(date(2020, 1, 1))]),
        SecuritySales(FONDO, [
            sm(date(2023, 6, 1), date(2021, 1, 1), "50", "500", "650"),  # +150
        ], all_buys=[buy(date(2021, 1, 1))]),
    ]
    ctx = _build_context(build_tax_report(2023, sales, []), lang="es")
    s = ctx["summary"]
    assert s["estimated_tax"] == "47,50"
    assert s["sales_tax"] == "19,00"
    assert s["fund_tax"] == "28,50"
    assert s["div_tax"] == "0,00"


def test_sin_fondos_bloque4_vacio():
    """Sin ventas de fondos, fund_lines está vacío (la plantilla muestra el aviso)."""
    from app.services.pdf_generator import _build_context

    sales = [SecuritySales(IBEX, [
        sm(date(2023, 5, 1), date(2020, 1, 1), "10", "100", "200"),
    ], all_buys=[buy(date(2020, 1, 1))])]
    ctx = _build_context(build_tax_report(2023, sales, []), lang="es")
    assert ctx["fund_lines"] == []
