"""
services/pdf_generator.py
=========================
Convierte un TaxReport (producido por tax_report.py) en un PDF.

Estrategia: la plantilla Jinja2 'tax_report.html' define la forma; WeasyPrint
la convierte a PDF. Este modulo NO contiene logica fiscal -- esa esta toda en
tax_report.py y verificada. Aqui solo se formatean numeros y fechas para
presentacion y se invoca el render.

Decision de diseno: los importes Decimal se formatean a string AQUI, en la
frontera de presentacion, con el formato espanol (coma decimal, punto de
miles). La plantilla recibe texto ya listo y no hace aritmetica.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from app.services.tax_report import TaxReport

# Carpeta de plantillas (reports/templates junto a este paquete).
_TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "reports" / "templates"


# --------------------------------------------------------------------------
#  Formato de numeros y fechas (estilo espanol)
# --------------------------------------------------------------------------

def _fmt_money(value: Decimal) -> str:
    """
    Formatea un importe al estilo espanol: 1.234.567,89
    El signo negativo se conserva. Redondeo a 2 decimales solo aqui,
    en presentacion -- los calculos previos usaron precision completa.
    """
    q = value.quantize(Decimal("0.01"))
    # Formateo con separador de miles ',' y decimal '.', luego se intercambian
    s = f"{q:,.2f}"
    return s.replace(",", "X").replace(".", ",").replace("X", ".")


def _fmt_shares(value: Decimal) -> str:
    """Acciones: sin decimales si es entero, hasta 6 si hay fraccion."""
    if value == value.to_integral_value():
        return str(int(value))
    return f"{value:.6f}".rstrip("0").rstrip(".").replace(".", ",")


def _fmt_date(d) -> str:
    """Fecha en formato dd/mm/aaaa."""
    return d.strftime("%d/%m/%Y")


# --------------------------------------------------------------------------
#  Preparacion del contexto de plantilla
# --------------------------------------------------------------------------

def _build_context(report: TaxReport) -> dict:
    """Transforma el TaxReport en el diccionario que espera la plantilla."""

    sale_lines = []
    for line in report.sale_lines:
        sale_lines.append({
            "security_name": line.security_name,
            "isin": line.isin,
            "market": line.market,
            "buy_date": _fmt_date(line.buy_date),
            "sell_date": _fmt_date(line.sell_date),
            "shares": _fmt_shares(line.shares),
            "cost_eur": _fmt_money(line.cost_eur),
            "proceeds_eur": _fmt_money(line.proceeds_eur),
            "gain_eur": _fmt_money(line.gain_eur),
            "gain_positive": line.gain_eur >= Decimal("0"),
            "loss_disallowed": line.loss_disallowed,
            "disallowed_reason": line.disallowed_reason,
        })

    dividend_lines = []
    for line in report.dividend_lines:
        dividend_lines.append({
            "security_name": line.security_name,
            "isin": line.isin,
            "market": line.market,
            "pay_date": _fmt_date(line.pay_date),
            "gross_eur": _fmt_money(line.gross_eur),
            "withholding_eur": _fmt_money(line.withholding_eur),
            "net_eur": _fmt_money(line.net_eur),
        })

    return {
        "year": report.year,
        "generated_at": datetime.now().strftime("%d/%m/%Y %H:%M"),
        "sale_lines": sale_lines,
        "dividend_lines": dividend_lines,
        "net_capital_positive": report.net_capital_result_eur >= Decimal("0"),
        "totals": {
            "gains": _fmt_money(report.total_gains_eur),
            "losses_computable": _fmt_money(report.total_losses_computable_eur),
            "losses_disallowed": _fmt_money(report.total_losses_disallowed_eur),
            "net_capital": _fmt_money(report.net_capital_result_eur),
            "div_gross": _fmt_money(report.total_dividends_gross_eur),
            "div_withholding": _fmt_money(report.total_dividends_withholding_eur),
            "div_net": _fmt_money(report.total_dividends_net_eur),
        },
        "warnings": report.warnings,
    }


# --------------------------------------------------------------------------
#  API publica
# --------------------------------------------------------------------------

def render_tax_report_html(report: TaxReport) -> str:
    """Renderiza el informe a HTML (util para depurar o previsualizar)."""
    env = Environment(
        loader=FileSystemLoader(str(_TEMPLATE_DIR)),
        autoescape=select_autoescape(["html"]),
    )
    template = env.get_template("tax_report.html")
    return template.render(**_build_context(report))


def generate_tax_report_pdf(report: TaxReport, output_path: str | Path) -> Path:
    """
    Genera el PDF del informe fiscal y lo escribe en 'output_path'.
    Devuelve la ruta del fichero creado.

    Importado aqui dentro y no arriba: WeasyPrint arrastra dependencias
    nativas pesadas; importarlo solo cuando se genera un PDF acelera el
    arranque del resto de la aplicacion.
    """
    from weasyprint import HTML

    html = render_tax_report_html(report)
    output_path = Path(output_path)
    HTML(string=html).write_pdf(str(output_path))
    return output_path
