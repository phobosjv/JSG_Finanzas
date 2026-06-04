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
# Tramos IRPF base del ahorro — valores por defecto (fallback hardcoded).
# En producción se sustituyen por los registros de la tabla tax_brackets.
# Formato: (max_amount | None, rate_as_decimal)
# ---------------------------------------------------------------------------
_BRACKETS: list[tuple[Decimal | None, Decimal]] = [
    (Decimal("6000"),   Decimal("19")),
    (Decimal("50000"),  Decimal("21")),
    (Decimal("200000"), Decimal("23")),
    (Decimal("300000"), Decimal("27")),
    (None,              Decimal("28")),
]

# Paleta de colores verde→rojo indexada por posición del tramo (0 = más bajo).
_COLOR_PALETTE = ["#4CAF50", "#8BC34A", "#FFC107", "#FF9800", "#F44336", "#D32F2F"]


def _bracket_color(index: int) -> str:
    """Devuelve el color del tramo según su posición (0 = primer/menor tramo)."""
    return _COLOR_PALETTE[min(index, len(_COLOR_PALETTE) - 1)]

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
        "card_net_sales_sub":      "Solo acciones/ETF/cripto (los fondos, aparte)",
        "card_funds":              "Resultado venta fondos",
        "card_funds_sub":          "Reembolsos de fondos de inversión",
        "card_dividends":          "Dividendos netos",
        "card_gross":              "Bruto",
        "card_withholding":        "Ret.",
        "card_est_tax":            "Cuota est.:",
        "card_commissions":        "Comisiones pagadas",
        "card_commissions_sub":    "Ya descontadas del coste de adquisición",
        "card_taxbase":            "Base imponible estimada",
        "card_marginal":           "Tramo marginal:",
        "card_cuota":              "Cuota estimada:",
        "brackets_title":          "Distribución por tramos",
        # Bloque 1: ganancias/pérdidas (agrupado por valor)
        "block1_title":            "1. Ganancias y pérdidas patrimoniales (venta de acciones)",
        "block1_empty":            "No se han registrado ventas de acciones en este ejercicio.",
        "block1_hint":             (
            "Una fila por valor y ejercicio. El resultado incluye todas las operaciones "
            "FIFO del valor; las comisiones ya están incorporadas en coste e importe de venta."
        ),
        "col_security":            "Valor",
        "col_isin":                "ISIN",
        "col_sell_year":           "Año venta",
        "col_shares":              "Acciones",
        "col_cost":                "Coste total (€)",
        "col_proceeds":            "Importe ventas (€)",
        "col_result":              "Resultado (€)",
        "flag_no_compute":         "⚠ NO COMPUTA (parcial)",
        "flag_no_compute_note":    "Parte de las pérdidas de este valor puede no ser computable este ejercicio (regla de recompra). Ver avisos.",
        "sum_gains":               "Ganancias del ejercicio",
        "sum_losses_computable":   "Pérdidas computables",
        "sum_losses_disallowed":   "Pérdidas marcadas (no computan este ejercicio)",
        "sum_net_capital":         "Saldo computable del ejercicio",
        # Bloque 2: detalle de movimientos
        "block2_title":            "2. Detalle de movimientos (compras y ventas del ejercicio)",
        "block2_hint":             (
            "Operaciones de compra y venta que han afectado al ejercicio, ordenadas por valor y fecha. "
            "Importes en euros (tipo BCE en la fecha de la operación). "
            "Subtotal = acciones × precio unitario (sin comisión). "
            "Total compra = subtotal + comisión. Total venta = subtotal − comisión."
        ),
        "block2_empty":            "No hay movimientos de compraventa en este ejercicio.",
        "col_type":                "Tipo",
        "col_date":                "Fecha",
        "col_unit_price":          "Precio unit. (€)",
        "col_subtotal":            "Subtotal (€)",
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
        # Bloque 4: fondos de inversión (reembolsos)
        "block4_title":            "4. Ganancias y pérdidas por venta de fondos de inversión",
        "block4_empty":            "No se han registrado ventas ni reembolsos de fondos en este ejercicio.",
        "block4_hint":             (
            "Una fila por fondo y ejercicio (los movimientos individuales no se "
            "detallan). El resultado va a la base del ahorro junto con el de las "
            "acciones; la retención del 19% la practica la gestora. Los traspasos "
            "entre fondos son fiscalmente neutros y no aparecen aquí."
        ),
        "col_redeem_year":         "Año reembolso",
        "col_units":               "Participaciones",
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
        "card_net_sales_sub":      "Shares/ETF/crypto only (funds shown separately)",
        "card_funds":              "Fund sales result",
        "card_funds_sub":          "Investment fund redemptions",
        "card_dividends":          "Net dividends",
        "card_gross":              "Gross",
        "card_withholding":        "Withh.",
        "card_est_tax":            "Est. tax:",
        "card_commissions":        "Commissions paid",
        "card_commissions_sub":    "Already deducted from acquisition cost",
        "card_taxbase":            "Estimated taxable base",
        "card_marginal":           "Marginal rate:",
        "card_cuota":              "Estimated tax:",
        "brackets_title":          "Distribution by tax bracket",
        "block1_title":            "1. Capital gains and losses (share sales)",
        "block1_empty":            "No share sales recorded for this fiscal year.",
        "block1_hint":             (
            "One row per security and year. Result includes all FIFO lots; "
            "commissions are already incorporated in cost and proceeds."
        ),
        "col_security":            "Security",
        "col_isin":                "ISIN",
        "col_sell_year":           "Sell year",
        "col_shares":              "Shares",
        "col_cost":                "Total cost (€)",
        "col_proceeds":            "Total proceeds (€)",
        "col_result":              "Result (€)",
        "flag_no_compute":         "⚠ NOT DEDUCTIBLE (partial)",
        "flag_no_compute_note":    "Some losses for this security may not be deductible (wash-sale rule). See notices.",
        "sum_gains":               "Gains for the year",
        "sum_losses_computable":   "Deductible losses",
        "sum_losses_disallowed":   "Flagged losses (not deductible this year)",
        "sum_net_capital":         "Net taxable capital result",
        "block2_title":            "2. Transaction details (buys and sells for the year)",
        "block2_hint":             (
            "Buy and sell transactions, sorted by security then date. "
            "All amounts in euros (ECB rate on transaction date). "
            "Subtotal = shares × unit price (excl. fee). "
            "Buy total = subtotal + fee. Sell total = subtotal − fee."
        ),
        "block2_empty":            "No buy/sell transactions for this fiscal year.",
        "col_type":                "Type",
        "col_date":                "Date",
        "col_unit_price":          "Unit price (€)",
        "col_subtotal":            "Subtotal (€)",
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
        "block4_title":            "4. Gains and losses from investment fund redemptions",
        "block4_empty":            "No fund sales or redemptions recorded for this fiscal year.",
        "block4_hint":             (
            "One row per fund and year (individual transactions are not detailed). "
            "The result goes to the savings tax base together with shares; the 19% "
            "withholding is applied by the management company. Fund-to-fund transfers "
            "are tax-neutral and do not appear here."
        ),
        "col_redeem_year":         "Redemption year",
        "col_units":               "Units",
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
# Bloque 1: pares FIFO agrupados por valor (una fila por security)
# ---------------------------------------------------------------------------

def _build_sale_lines_grouped(
    sale_lines: list[SaleLine], mark_funds: bool = True
) -> list[dict]:
    """
    Agrega los pares FIFO en UNA fila por valor y ejercicio.

    Los bloques FIFO para el mismo valor se suman: acciones, coste total,
    importe de venta y resultado. Se marca la fila si algún par tiene
    'loss_disallowed' para que el usuario sepa que parte de su resultado
    puede estar afectado por la regla de recompra.

    'mark_funds': si True añade el sufijo «(F)» a los fondos. En la sección
    dedicada a fondos es redundante (todas las filas son fondos), así que se
    pasa False.
    """
    # key: (security_name, isin, sell_year)
    groups: dict = {}

    for line in sale_lines:
        key = (line.security_name, line.isin, line.sell_date.year)
        if key not in groups:
            groups[key] = {
                "security_name":  line.security_name,
                "isin":           line.isin,
                "sell_year":      line.sell_date.year,
                "shares":         Decimal("0"),
                "cost_eur":       Decimal("0"),
                "proceeds_eur":   Decimal("0"),
                "gain_eur":       Decimal("0"),
                "has_disallowed": False,
                "is_fund":        False,
            }
        g = groups[key]
        g["shares"]       += line.shares
        g["cost_eur"]     += line.cost_eur
        g["proceeds_eur"] += line.proceeds_eur
        g["gain_eur"]     += line.gain_eur
        if line.loss_disallowed:
            g["has_disallowed"] = True
        if line.is_fund:
            g["is_fund"] = True

    result = [
        {
            # Los fondos se marcan con «(F)»: retención del 19% gestionada por
            # la entidad (explicado en los avisos del informe).
            "security_name":  g["security_name"] + (" (F)" if (mark_funds and g["is_fund"]) else ""),
            "isin":           g["isin"],
            "sell_year":      str(g["sell_year"]),
            "shares":         _fmt_shares(g["shares"]),
            "cost_eur":       _fmt_money(g["cost_eur"]),
            "proceeds_eur":   _fmt_money(g["proceeds_eur"]),
            "gain_eur":       _fmt_money(g["gain_eur"]),
            "gain_positive":  g["gain_eur"] >= Decimal("0"),
            "has_disallowed": g["has_disallowed"],
            "is_fund":        g["is_fund"],
        }
        for g in groups.values()
    ]

    result.sort(key=lambda r: (r["security_name"], r["sell_year"]))
    return result


def _compute_adjusted_totals(sale_lines: list[SaleLine]) -> dict:
    """
    Calcula ganancias y pérdidas clasificando el resultado NETO de cada valor,
    en lugar de hacerlo par a par FIFO.

    Motivación: si un valor se vendió dos veces en el ejercicio (una con
    pérdida de -2,84 € y otra con ganancia de +19,35 €), la visión por valor
    muestra un único resultado neto de +16,51 €.  Si se contabilizaran de
    forma independiente se mostraría una ganancia (+19,35) Y una pérdida
    (-2,84) que se contradicen con la fila única del Bloque 1.

    Algoritmo:
      1. Para los pares NO afectados por la regla de recompra, agrupa por
         valor y acumula el resultado neto.
      2. Cada valor contribuye al total de ganancias (si net > 0) o al total
         de pérdidas (si net < 0) con su resultado NETO.
      3. Los pares afectados por la regla de recompra se acumulan aparte
         (no cambia respecto al cálculo original).

    La suma `adj_gains + adj_losses_computable` == `net_capital_result_eur`
    es matemáticamente idéntica a la suma original, solo cambia la separación.
    """
    # Agrupa pares computables por valor
    sec_net: dict = {}
    dis_total = Decimal("0")

    for line in sale_lines:
        if line.loss_disallowed:
            dis_total += line.gain_eur
        else:
            key = (line.security_name, line.isin, line.sell_date.year)
            sec_net.setdefault(key, Decimal("0"))
            sec_net[key] += line.gain_eur

    adj_gains  = sum((v for v in sec_net.values() if v > Decimal("0")), Decimal("0"))
    adj_losses = sum((v for v in sec_net.values() if v < Decimal("0")), Decimal("0"))

    return {
        "gains":             adj_gains,
        "losses_computable": adj_losses,
        "losses_disallowed": dis_total,
        "net_capital":       adj_gains + adj_losses,
    }


# ---------------------------------------------------------------------------
# Bloque 2: movimientos agregados por valor+fecha (Compras y Ventas)
# ---------------------------------------------------------------------------

def _build_movement_lines(sale_lines: list[SaleLine], lang: str) -> list[dict]:
    """
    Agrega los pares FIFO (SaleLine) en filas de movimiento (compra/venta).

    Reglas de agrupación:
      VENTAS  → agrupa por (valor, fecha_venta, isin, divisa).
                Una venta que consume varios lotes FIFO se muestra como
                una sola fila (misma operación de venta).
      COMPRAS → agrupa por (valor, fecha_compra, precio_unitario, isin, divisa).
                Dos compras distintas el mismo día con el MISMO precio se
                agrupan; dos compras el mismo día con precios distintos
                generan filas independientes.
                Un lote de compra parcialmente consumido por varias ventas
                se re-agrupa en una sola fila (mismo precio, misma fecha).

    Todos los importes en euros; "Divisa" muestra la divisa nativa del valor.

    Columnas:
      Precio unit.  = precio de mercado por acción (sin comisión)
      Subtotal      = acciones × precio unitario (sin comisión)
      Comisión      = comisión pagada/cobrada
      Total compra  = subtotal + comisión (lo que se pagó)
      Total venta   = subtotal − comisión (lo que se recibió neto)

    Ordenación: nombre del valor → fecha → compras antes que ventas.
    """
    lbl = _LABELS.get(lang, _LABELS["es"])

    # sell: (name, sell_date, isin, currency) -> {shares, gross, net, fee}
    sells: dict = {}
    # buy:  (name, buy_date, unit_cost_key, isin, currency) -> {shares, cost_no_fee, cost_total, fee}
    # La clave incluye el precio unitario (redondeado a 6 decimales) para separar
    # lotes del mismo día comprados a distinto precio, y a la vez agrupar
    # consumos parciales del mismo lote (tienen exactamente el mismo precio unitario).
    buys: dict = {}

    _Q = Decimal("0.000001")  # precisión para la clave de precio unitario

    for line in sale_lines:
        # SELL
        sk = (line.security_name, line.sell_date, line.isin, line.currency)
        if sk not in sells:
            sells[sk] = {
                "shares": Decimal("0"),
                "gross":  Decimal("0"),
                "net":    Decimal("0"),
                "fee":    Decimal("0"),
            }
        sells[sk]["shares"] += line.shares
        sells[sk]["gross"]  += line.proceeds_eur + line.sell_fee_eur
        sells[sk]["net"]    += line.proceeds_eur
        sells[sk]["fee"]    += line.sell_fee_eur

        # BUY — precio unitario del lote (sin comisión) como parte de la clave
        cost_no_fee_line = line.cost_eur - line.buy_fee_eur
        unit_cost_key = (
            (cost_no_fee_line / line.shares).quantize(_Q)
            if line.shares else Decimal("0")
        )
        bk = (line.security_name, line.buy_date, unit_cost_key, line.isin, line.currency)
        if bk not in buys:
            buys[bk] = {
                "shares":       Decimal("0"),
                "cost_no_fee":  Decimal("0"),
                "cost_total":   Decimal("0"),
                "fee":          Decimal("0"),
                "unit_cost":    unit_cost_key,   # guardado para ordenar
            }
        buys[bk]["shares"]      += line.shares
        buys[bk]["cost_no_fee"] += cost_no_fee_line
        buys[bk]["cost_total"]  += line.cost_eur
        buys[bk]["fee"]         += line.buy_fee_eur

    movements: list[dict] = []

    for (name, dt, isin, currency), data in sells.items():
        shares = data["shares"]
        gross  = data["gross"]
        net    = data["net"]
        fee    = data["fee"]
        unit_p = gross / shares if shares else Decimal("0")
        movements.append({
            "type_label":    lbl["type_sell"],
            "is_sell":       True,
            "_sort_key":     (name, dt, True, Decimal("0")),
            "date":          _fmt_date(dt),
            "security_name": name,
            "isin":          isin or "—",
            "shares":        _fmt_shares(shares),
            "unit_price":    _fmt_money(unit_p),
            "subtotal":      _fmt_money(gross),
            "fee":           _fmt_money(fee),
            "currency":      currency,
            "total":         _fmt_money(net),
        })

    for (name, dt, ukey, isin, currency), data in buys.items():
        shares      = data["shares"]
        cost_no_fee = data["cost_no_fee"]
        cost_total  = data["cost_total"]
        fee         = data["fee"]
        unit_p = cost_no_fee / shares if shares else Decimal("0")
        movements.append({
            "type_label":    lbl["type_buy"],
            "is_sell":       False,
            # Compras del mismo día ordenadas de menor a mayor precio unitario
            "_sort_key":     (name, dt, False, ukey),
            "date":          _fmt_date(dt),
            "security_name": name,
            "isin":          isin or "—",
            "shares":        _fmt_shares(shares),
            "unit_price":    _fmt_money(unit_p),
            "subtotal":      _fmt_money(cost_no_fee),
            "fee":           _fmt_money(fee),
            "currency":      currency,
            "total":         _fmt_money(cost_total),
        })

    # Ordenar: valor → fecha → compras(False) antes que ventas(True) → precio unit. asc
    movements.sort(key=lambda m: m["_sort_key"])

    for m in movements:
        del m["_sort_key"]

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

def _build_tax_summary(
    report: TaxReport,
    brackets: list[tuple[Decimal | None, Decimal]] | None = None,
    sales_net_eur: Decimal | None = None,
    fund_net_eur: Decimal | None = None,
) -> dict:
    """
    Calcula el resumen fiscal para la primera página del informe.

    Base imponible estimada = max(0, resultado_neto_ventas) + dividendos_netos,
    donde resultado_neto_ventas agrega acciones Y fondos (ambos van a la base
    del ahorro). 'sales_net_eur' / 'fund_net_eur' permiten desglosar ese
    resultado en la tarjeta de acciones y la tarjeta de fondos por separado;
    si no se pasan, se asume todo a ventas (compatibilidad).

    Cada componente de ganancia (ventas de acciones, fondos, dividendos) lleva
    una cuota estimada propia = importe positivo × tipo efectivo
    (cuota_total / base). Es orientativa: reparte la cuota progresiva total de
    forma proporcional al peso de cada componente.

    Si se proporcionan 'brackets' (cargados de la BD), se usan en lugar de los
    valores por defecto hardcodeados.
    """
    active_brackets = brackets if brackets is not None else _BRACKETS

    # Desglose del resultado de ventas (combinado para la base, separado para
    # las tarjetas). Si no se pasa, todo va a "ventas" y nada a "fondos".
    if sales_net_eur is None:
        sales_net_eur = report.net_capital_result_eur
        fund_net_eur = Decimal("0")
    if fund_net_eur is None:
        fund_net_eur = Decimal("0")

    base = (
        max(Decimal("0"), report.net_capital_result_eur)
        + report.total_dividends_net_eur
    )
    base = max(Decimal("0"), base)

    estimated_tax = Decimal("0")
    marginal = int(active_brackets[0][1]) if active_brackets else 19
    segments: list[dict] = []
    remaining = base
    prev = Decimal("0")

    for i, (limit, rate) in enumerate(active_brackets):
        rate_dec = Decimal(str(rate))
        slice_amt = (
            min(remaining, limit - prev) if limit is not None else remaining
        )
        if slice_amt > Decimal("0"):
            estimated_tax += slice_amt * rate_dec / Decimal("100")
            pct = float(slice_amt / base * 100) if base > Decimal("0") else 0.0
            segments.append(
                {
                    "rate":   int(rate_dec),
                    "amount": _fmt_money(slice_amt),
                    "pct":    f"{pct:.4f}",
                    "color":  _bracket_color(i),
                }
            )
            marginal = int(rate_dec)
        remaining -= slice_amt
        if limit is not None:
            prev = limit
        if remaining <= Decimal("0"):
            break

    # Tipo efectivo: reparte la cuota total entre los componentes positivos.
    eff_rate = (estimated_tax / base) if base > Decimal("0") else Decimal("0")
    div_net = report.total_dividends_net_eur
    sales_tax = max(Decimal("0"), sales_net_eur) * eff_rate
    fund_tax  = max(Decimal("0"), fund_net_eur) * eff_rate
    div_tax   = max(Decimal("0"), div_net) * eff_rate

    return {
        # "net_capital" sigue siendo el resultado de ventas COMBINADO (base);
        # "net_sales"/"fund_net" lo desglosan para las tarjetas.
        "net_capital":          _fmt_money(report.net_capital_result_eur),
        "net_capital_positive": report.net_capital_result_eur >= Decimal("0"),
        "net_sales":            _fmt_money(sales_net_eur),
        "net_sales_positive":   sales_net_eur >= Decimal("0"),
        "sales_tax":            _fmt_money(sales_tax),
        "fund_net":             _fmt_money(fund_net_eur),
        "fund_net_positive":    fund_net_eur >= Decimal("0"),
        "fund_tax":             _fmt_money(fund_tax),
        "div_gross":            _fmt_money(report.total_dividends_gross_eur),
        "div_withholding":      _fmt_money(report.total_dividends_withholding_eur),
        "div_net":              _fmt_money(div_net),
        "div_net_positive":     div_net >= Decimal("0"),
        "div_tax":              _fmt_money(div_tax),
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

def _build_context(
    report: TaxReport,
    lang: str = "es",
    brackets: list[tuple[Decimal | None, Decimal]] | None = None,
) -> dict:
    lbl = _LABELS.get(lang, _LABELS["es"])

    # Las ventas de fondos van en una sección propia (Bloque 4, tras dividendos)
    # y NO se detallan movimiento a movimiento. Los Bloques 1 y 2 quedan solo
    # con acciones/ETF/cripto. Fiscalmente, ambos resultados van a la base del
    # ahorro (el resumen ejecutivo los sigue agregando).
    stock_sales = [s for s in report.sale_lines if not s.is_fund]
    fund_sales  = [s for s in report.sale_lines if s.is_fund]

    # Bloque 1: una fila por valor (agrupado), con flag si hay pérdidas no computables
    sale_lines = _build_sale_lines_grouped(stock_sales)

    # Bloque 2: movimientos detallados (una fila por operación/fecha, con subtotal)
    movement_lines = _build_movement_lines(stock_sales, lang)

    # Bloque 4: reembolsos de fondos, agregados por fondo (sin detalle de movimientos)
    fund_lines = _build_sale_lines_grouped(fund_sales, mark_funds=False)

    # Bloque 3: dividendos
    dividend_lines = [
        {
            "security_name":   line.security_name + (" (F)" if line.is_fund else ""),
            "isin":            line.isin,
            "market":          line.market,
            "pay_date":        _fmt_date(line.pay_date),
            "gross_eur":       _fmt_money(line.gross_eur),
            "withholding_eur": _fmt_money(line.withholding_eur),
            "net_eur":         _fmt_money(line.net_eur),
            "is_fund":         line.is_fund,
        }
        for line in report.dividend_lines
    ]

    # Resultado neto por separado: acciones (Bloque 1) y fondos (Bloque 4).
    # El resumen ejecutivo usa el desglose para la tarjeta de ventas y la de
    # fondos; la base imponible los sigue agregando.
    stock_adj = _compute_adjusted_totals(stock_sales)
    fund_adj  = _compute_adjusted_totals(fund_sales)

    return {
        "lang":                 lang,
        "labels":               lbl,
        "year":                 report.year,
        "generated_at":         datetime.now().strftime("%d/%m/%Y %H:%M"),
        "summary":              _build_tax_summary(
            report, brackets=brackets,
            sales_net_eur=stock_adj["net_capital"],
            fund_net_eur=fund_adj["net_capital"],
        ),
        "sale_lines":           sale_lines,
        "movement_lines":       movement_lines,
        "dividend_lines":       dividend_lines,
        "fund_lines":           fund_lines,
        "net_capital_positive": report.net_capital_result_eur >= Decimal("0"),
        "fund_net_positive":    fund_adj["net_capital"] >= Decimal("0"),
        "totals": {
            # Totales usando el resultado NETO por valor (coherente con la tabla del Bloque 1).
            # Si un valor tuvo pérdida y ganancia, el neto positivo cuenta solo como ganancia.
            **{k: _fmt_money(v) for k, v in stock_adj.items()},
            "div_gross":          _fmt_money(report.total_dividends_gross_eur),
            "div_withholding":    _fmt_money(report.total_dividends_withholding_eur),
            "div_net":            _fmt_money(report.total_dividends_net_eur),
        },
        "fund_totals": {
            k: _fmt_money(v) for k, v in fund_adj.items()
        },
        "warnings": _build_warnings(report, lang),
    }


def render_tax_report_html(
    report: TaxReport,
    lang: str = "es",
    brackets: list[tuple[Decimal | None, Decimal]] | None = None,
) -> str:
    env = Environment(
        loader=FileSystemLoader(str(_TEMPLATE_DIR)),
        autoescape=select_autoescape(["html"]),
    )
    return env.get_template("tax_report.html").render(
        **_build_context(report, lang=lang, brackets=brackets)
    )
