"""
services/pdf_generator.py
=========================
Renderiza un TaxReport a HTML usando Jinja2.

El HTML resultante se sirve directamente al navegador; el usuario imprime
a PDF con Ctrl+P. No se usa WeasyPrint ni ninguna dependencia nativa.

Soporta dos idiomas: español ("es") e inglés ("en").
El parámetro `lang` controla el idioma de todas las etiquetas estáticas.
El texto dinámico (razón de pérdida no computable) también se localiza.
Los Decimal se convierten a cadena AQUÍ, en la frontera de presentación;
la plantilla recibe texto listo y no hace aritmética.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from app.services.tax_report import TaxReport, SaleLine

# ---------------------------------------------------------------------------
# Tramos IRPF base del ahorro (vigentes desde 2023)
# (limit, rate): limit=None significa sin techo (último tramo).
# ---------------------------------------------------------------------------
_BRACKETS: list[tuple[Decimal | None, int]] = [
    (Decimal("6000"),   19),
    (Decimal("50000"),  21),
    (Decimal("200000"), 23),
    (Decimal("300000"), 27),
    (None,              28),
]
_BRACKET_COLORS: dict[int, str] = {
    19: "#4CAF50",
    21: "#8BC34A",
    23: "#FFC107",
    27: "#FF9800",
    28: "#F44336",
}

_TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "reports" / "templates"


# ---------------------------------------------------------------------------
# Etiquetas i18n para la plantilla HTML
# ---------------------------------------------------------------------------

_LABELS: dict[str, dict[str, str]] = {
    "es": {
        "page_header":             "Informe para la declaración de la renta",
        "fiscal_year":             "Ejercicio fiscal",
        "generated_at":            "Generado el",
        # Tarjetas resumen (página 1)
        "card_net_sales":          "Resultado neto ventas",
        "card_net_sales_sub":      "Comisiones ya incluidas en el cálculo",
        "card_dividends":          "Dividendos netos",
        "card_gross":              "Bruto",
        "card_withholding":        "Ret.",
        "card_commissions":        "Comisiones pagadas",
        "card_commissions_sub":    "Ya descontadas del coste de adquisición",
        "card_taxbase":            "Base imponible estimada",
        "card_marginal":           "Tramo marginal:",
        "card_cuota":              "Cuota estimada:",
        "brackets_title":          "Distribución por tramos",
        # Bloque 1: ganancias/pérdidas
        "block1_title":            "1. Ganancias y pérdidas patrimoniales (venta de acciones)",
        "block1_empty":            "No se han registrado ventas de acciones en este ejercicio.",
        "col_security":            "Valor",
        "col_isin":                "ISIN",
        "col_buy_date":            "F. compra",
        "col_sell_date":           "F. venta",
        "col_shares":              "Acciones",
        "col_cost":                "Coste (€)",
        "col_proceeds":            "Venta (€)",
        "col_result":              "Resultado (€)",
        "flag_no_compute":         "NO COMPUTA",
        "sum_gains":               "Ganancias del ejercicio",
        "sum_losses_computable":   "Pérdidas computables",
        "sum_losses_disallowed":   "Pérdidas marcadas (no computan este ejercicio)",
        "sum_net_capital":         "Saldo computable del ejercicio",
        # Bloque 2: detalle de movimientos
        "block2_title":            "2. Detalle de movimientos (compras y ventas del ejercicio)",
        "block2_hint":             (
            "Operaciones de compra y venta que han afectado al ejercicio. "
            "Los importes son en euros (al tipo BCE en la fecha de la operación). "
            "El precio unitario de compra excluye comisión; el de venta incluye comisión bruta."
        ),
        "block2_empty":            "No hay movimientos de compraventa en este ejercicio.",
        "col_type":                "Tipo",
        "col_date":                "Fecha",
        "col_unit_price":          "Precio unit. (€)",
        "col_fee":                 "Comisión (€)",
        "col_currency":            "Divisa",
        "col_total":               "Total (€)",
        "type_buy":                "Compra",
        "type_sell":               "Venta",
        # Bloque 3: dividendos
        "block3_title":            "3. Rendimientos del capital mobiliario (dividendos)",
        "block3_empty":            "No se han registrado dividendos en este ejercicio.",
        "col_pay_date":            "Fecha de cobro",
        "col_gross":               "Bruto (€)",
        "col_withholding":         "Retención origen (€)",
        "col_net":                 "Neto (€)",
        "total":                   "TOTAL",
        # Avisos
        "warnings_title":          "Avisos importantes",
        "warn_generic":            (
            "Informe orientativo de apoyo. No sustituye la revisión de un asesor "
            "fiscal ni constituye asesoramiento."
        ),
        "warn_disallowed":         (
            "Se han detectado posibles pérdidas afectadas por la regla de "
            "recompra. Aparecen marcadas y NO se han incluido en el saldo "
            "computable. Su tratamiento definitivo depende del concepto de "
            "valores homogéneos y debe revisarse."
        ),
        "warn_withholding":        (
            "Existen retenciones en origen sobre dividendos. La deducción por "
            "doble imposición internacional no se calcula en este informe: "
            "depende del conjunto de la declaración."
        ),
        # Pie de página (CSS @page — necesita duplicarse)
        "page_num":                "Página",
        "page_of":                 "de",
    },
    "en": {
        "page_header":             "Tax return report",
        "fiscal_year":             "Fiscal year",
        "generated_at":            "Generated on",
        "card_net_sales":          "Net capital result",
        "card_net_sales_sub":      "Commissions already included in the calculation",
        "card_dividends":          "Net dividends",
        "card_gross":              "Gross",
        "card_withholding":        "Withh.",
        "card_commissions":        "Commissions paid",
        "card_commissions_sub":    "Already deducted from acquisition cost",
        "card_taxbase":            "Estimated taxable base",
        "card_marginal":           "Marginal rate:",
        "card_cuota":              "Estimated tax:",
        "brackets_title":          "Distribution by tax bracket",
        "block1_title":            "1. Capital gains and losses (share sales)",
        "block1_empty":            "No share sales recorded for this fiscal year.",
        "col_security":            "Security",
        "col_isin":                "ISIN",
        "col_buy_date":            "Buy date",
        "col_sell_date":           "Sell date",
        "col_shares":              "Shares",
        "col_cost":                "Cost (€)",
        "col_proceeds":            "Proceeds (€)",
        "col_result":              "Result (€)",
        "flag_no_compute":         "NOT DEDUCTIBLE",
        "sum_gains":               "Gains for the year",
        "sum_losses_computable":   "Deductible losses",
        "sum_losses_disallowed":   "Flagged losses (not deductible this year)",
        "sum_net_capital":         "Net taxable capital result",
        "block2_title":            "2. Transaction details (buys and sells for the year)",
        "block2_hint":             (
            "Buy and sell transactions affecting this fiscal year. "
            "All amounts are in euros (ECB exchange rate on transaction date). "
            "Buy unit price excludes commission; sell unit price is gross before commission."
        ),
        "block2_empty":            "No buy/sell transactions for this fiscal year.",
        "col_type":                "Type",
        "col_date":                "Date",
        "col_unit_price":          "Unit price (€)",
        "col_fee":                 "Fee (€)",
        "col_currency":            "Currency",
        "col_total":               "Total (€)",
        "type_buy":                "Buy",
        "type_sell":               "Sell",
        "block3_title":            "3. Investment income (dividends)",
        "block3_empty":            "No dividends recorded for this fiscal year.",
        "col_pay_date":            "Pay date",
        "col_gross":               "Gross (€)",
        "col_withholding":         "Withholding tax (€)",
        "col_net":                 "Net (€)",
        "total":                   "TOTAL",
        "warnings_title":          "Important notices",
        "warn_generic":            (
            "Indicative report for reference only. It does not replace the review "
            "of a tax advisor and does not constitute tax advice."
        ),
        "warn_disallowed":         (
            "Possible wash-sale rule losses have been detected. They are flagged "
            "and NOT included in the net taxable result. Final treatment depends "
            "on the concept of homogeneous securities and should be reviewed."
        ),
        "warn_withholding":        (
            "There are withholding taxes on dividends. The double-taxation "
            "deduction is not calculated in this report: it depends on the "
            "overall tax return."
        ),
        "page_num":                "Page",
        "page_of":                 "of",
    },
}


# ---------------------------------------------------------------------------
# Formateo de valores para la plantilla
# ---------------------------------------------------------------------------

def _fmt_money(value: Decimal) -> str:
    """1.234.567,89 — separador de miles punto, decimal coma."""
    q = value.quantize(Decimal("0.01"))
    s = f"{q:,.2f}"
    return s.replace(",", "X").replace(".", ",").replace("X", ".")


def _fmt_shares(value: Decimal) -> str:
    """Sin decimales si es entero; hasta 6 si hay fracción."""
    if value == value.to_integral_value():
        return str(int(value))
    return f"{value:.6f}".rstrip("0").rstrip(".").replace(".", ",")


def _fmt_date(d) -> str:
    return d.strftime("%d/%m/%Y")


# ---------------------------------------------------------------------------
# Texto localizado de la regla de recompra
# ---------------------------------------------------------------------------

def _fmt_disallowed_reason(fiscal_window_days: int, lang: str) -> str:
    """Genera el texto de aviso de regla de recompra en el idioma solicitado."""
    days = fiscal_window_days
    if days >= 365:
        plazo = "un año" if lang == "es" else "one year"
    elif days >= 30:
        meses = round(days / 30)
        if lang == "es":
            plazo = f"{meses} {'mes' if meses == 1 else 'meses'}"
        else:
            plazo = f"{meses} {'month' if meses == 1 else 'months'}"
    else:
        if lang == "es":
            plazo = f"{days} {'día' if days == 1 else 'días'}"
        else:
            plazo = f"{days} {'day' if days == 1 else 'days'}"

    if lang == "es":
        return (
            f"Posible aplicación de la regla de recompra: existe una compra del "
            f"mismo valor dentro del plazo de {plazo} alrededor de la venta. "
            f"La pérdida puede no ser computable en este ejercicio."
        )
    return (
        f"Possible wash-sale rule: there is a purchase of the same security "
        f"within {plazo} of the sale date. The loss may not be deductible "
        f"for this tax year."
    )


# ---------------------------------------------------------------------------
# Movimientos agregados (Bloque 2)
# ---------------------------------------------------------------------------

def _build_movement_lines(sale_lines: list[SaleLine], lang: str) -> list[dict]:
    """
    Agrega los pares FIFO (SaleLine) en filas de movimiento por fecha.

    Las ventas del mismo valor y fecha se agrupan en una sola fila "Venta".
    Las compras del mismo valor y fecha (aunque procedentes de distintos pares
    FIFO) se agrupan en una sola fila "Compra".
    Todos los importes ya están en euros; la columna "Divisa" muestra la divisa
    nativa del valor (EUR o USD) para referencia.
    """
    lbl = _LABELS.get(lang, _LABELS["es"])

    # sell: (name, sell_date, isin, currency) -> {shares, gross, fee}
    sells: dict = {}
    # buy:  (name, buy_date,  isin, currency) -> {shares, cost_no_fee, cost_total, fee}
    buys: dict = {}

    for line in sale_lines:
        # SELL
        sk = (line.security_name, line.sell_date, line.isin, line.currency)
        if sk not in sells:
            sells[sk] = {
                "shares": Decimal("0"),
                "gross":  Decimal("0"),
                "fee":    Decimal("0"),
            }
        sells[sk]["shares"] += line.shares
        sells[sk]["gross"]  += line.proceeds_eur + line.sell_fee_eur
        sells[sk]["fee"]    += line.sell_fee_eur

        # BUY
        bk = (line.security_name, line.buy_date, line.isin, line.currency)
        if bk not in buys:
            buys[bk] = {
                "shares":       Decimal("0"),
                "cost_no_fee":  Decimal("0"),
                "cost_total":   Decimal("0"),
                "fee":          Decimal("0"),
            }
        buys[bk]["shares"]      += line.shares
        buys[bk]["cost_no_fee"] += line.cost_eur - line.buy_fee_eur
        buys[bk]["cost_total"]  += line.cost_eur
        buys[bk]["fee"]         += line.buy_fee_eur

    movements: list[dict] = []

    for (name, dt, isin, currency), data in sells.items():
        shares = data["shares"]
        gross  = data["gross"]
        fee    = data["fee"]
        unit_p = gross / shares if shares else Decimal("0")
        movements.append({
            "type_label":    lbl["type_sell"],
            "is_sell":       True,
            "_date_obj":     dt,          # solo para ordenar; no va a la plantilla
            "date":          _fmt_date(dt),
            "security_name": name,
            "isin":          isin or "—",
            "shares":        _fmt_shares(shares),
            "unit_price":    _fmt_money(unit_p),
            "fee":           _fmt_money(fee),
            "currency":      currency,
            "total":         _fmt_money(gross),
        })

    for (name, dt, isin, currency), data in buys.items():
        shares      = data["shares"]
        cost_no_fee = data["cost_no_fee"]
        cost_total  = data["cost_total"]
        fee         = data["fee"]
        unit_p = cost_no_fee / shares if shares else Decimal("0")
        movements.append({
            "type_label":    lbl["type_buy"],
            "is_sell":       False,
            "_date_obj":     dt,
            "date":          _fmt_date(dt),
            "security_name": name,
            "isin":          isin or "—",
            "shares":        _fmt_shares(shares),
            "unit_price":    _fmt_money(unit_p),
            "fee":           _fmt_money(fee),
            "currency":      currency,
            "total":         _fmt_money(cost_total),
        })

    # Ordenar: fecha asc, luego nombre, luego compras antes que ventas (False < True)
    movements.sort(key=lambda m: (m["_date_obj"], m["security_name"], m["is_sell"]))

    # Eliminar clave interna antes de pasar a la plantilla
    for m in movements:
        del m["_date_obj"]

    return movements


# ---------------------------------------------------------------------------
# Avisos localizados
# ---------------------------------------------------------------------------

def _build_warnings(report: TaxReport, lang: str) -> list[str]:
    """Genera la lista de avisos del informe en el idioma solicitado."""
    lbl = _LABELS.get(lang, _LABELS["es"])
    ws = [lbl["warn_generic"]]
    if report.total_losses_disallowed_eur < Decimal("0"):
        ws.append(lbl["warn_disallowed"])
    if report.total_dividends_withholding_eur > Decimal("0"):
        ws.append(lbl["warn_withholding"])
    return ws


# ---------------------------------------------------------------------------
# Resumen ejecutivo: base imponible + tramos IRPF
# ---------------------------------------------------------------------------

def _build_tax_summary(report: TaxReport) -> dict:
    """
    Calcula el resumen fiscal para la primera página del informe.

    Base imponible estimada = max(0, resultado_neto_ventas) + dividendos_netos.
    """
    base = (
        max(Decimal("0"), report.net_capital_result_eur)
        + report.total_dividends_net_eur
    )
    base = max(Decimal("0"), base)

    estimated_tax = Decimal("0")
    marginal = 19
    segments: list[dict] = []
    remaining = base
    prev = Decimal("0")

    for limit, rate in _BRACKETS:
        slice_amt = (
            min(remaining, limit - prev) if limit is not None else remaining
        )
        if slice_amt > Decimal("0"):
            estimated_tax += slice_amt * Decimal(str(rate)) / Decimal("100")
            pct = float(slice_amt / base * 100) if base > Decimal("0") else 0.0
            segments.append(
                {
                    "rate":   rate,
                    "amount": _fmt_money(slice_amt),
                    "pct":    f"{pct:.4f}",
                    "color":  _BRACKET_COLORS[rate],
                }
            )
            marginal = rate
        remaining -= slice_amt
        if limit is not None:
            prev = limit
        if remaining <= Decimal("0"):
            break

    return {
        "net_capital":          _fmt_money(report.net_capital_result_eur),
        "net_capital_positive": report.net_capital_result_eur >= Decimal("0"),
        "div_gross":            _fmt_money(report.total_dividends_gross_eur),
        "div_withholding":      _fmt_money(report.total_dividends_withholding_eur),
        "div_net":              _fmt_money(report.total_dividends_net_eur),
        "div_net_positive":     report.total_dividends_net_eur >= Decimal("0"),
        "commission_total":     _fmt_money(report.total_commission_eur),
        "base_imponible":       _fmt_money(base),
        "base_positive":        base > Decimal("0"),
        "estimated_tax":        _fmt_money(estimated_tax),
        "marginal_rate":        marginal,
        "segments":             segments,
    }


# ---------------------------------------------------------------------------
# Contexto completo para Jinja2
# ---------------------------------------------------------------------------

def _build_context(report: TaxReport, lang: str = "es") -> dict:
    lbl = _LABELS.get(lang, _LABELS["es"])

    # Bloque 1: pares FIFO formateados
    sale_lines = [
        {
            "security_name":    line.security_name,
            "isin":             line.isin,
            "market":           line.market,
            "buy_date":         _fmt_date(line.buy_date),
            "sell_date":        _fmt_date(line.sell_date),
            "shares":           _fmt_shares(line.shares),
            "cost_eur":         _fmt_money(line.cost_eur),
            "proceeds_eur":     _fmt_money(line.proceeds_eur),
            "gain_eur":         _fmt_money(line.gain_eur),
            "gain_positive":    line.gain_eur >= Decimal("0"),
            "loss_disallowed":  line.loss_disallowed,
            # Razón localizada: generada aquí (capa de presentación)
            "disallowed_reason": (
                _fmt_disallowed_reason(line.fiscal_window_days, lang)
                if line.loss_disallowed else None
            ),
        }
        for line in report.sale_lines
    ]

    # Bloque 2: movimientos agregados (reemplaza el antiguo bloque de comisiones)
    movement_lines = _build_movement_lines(report.sale_lines, lang)

    # Bloque 3: dividendos
    dividend_lines = [
        {
            "security_name":   line.security_name,
            "isin":            line.isin,
            "market":          line.market,
            "pay_date":        _fmt_date(line.pay_date),
            "gross_eur":       _fmt_money(line.gross_eur),
            "withholding_eur": _fmt_money(line.withholding_eur),
            "net_eur":         _fmt_money(line.net_eur),
        }
        for line in report.dividend_lines
    ]

    return {
        "lang":                 lang,
        "labels":               lbl,
        "year":                 report.year,
        "generated_at":         datetime.now().strftime("%d/%m/%Y %H:%M"),
        "summary":              _build_tax_summary(report),
        "sale_lines":           sale_lines,
        "movement_lines":       movement_lines,
        "dividend_lines":       dividend_lines,
        "net_capital_positive": report.net_capital_result_eur >= Decimal("0"),
        "totals": {
            "gains":              _fmt_money(report.total_gains_eur),
            "losses_computable":  _fmt_money(report.total_losses_computable_eur),
            "losses_disallowed":  _fmt_money(report.total_losses_disallowed_eur),
            "net_capital":        _fmt_money(report.net_capital_result_eur),
            "div_gross":          _fmt_money(report.total_dividends_gross_eur),
            "div_withholding":    _fmt_money(report.total_dividends_withholding_eur),
            "div_net":            _fmt_money(report.total_dividends_net_eur),
        },
        "warnings": _build_warnings(report, lang),
    }


def render_tax_report_html(report: TaxReport, lang: str = "es") -> str:
    env = Environment(
        loader=FileSystemLoader(str(_TEMPLATE_DIR)),
        autoescape=select_autoescape(["html"]),
    )
    return env.get_template("tax_report.html").render(**_build_context(report, lang))
