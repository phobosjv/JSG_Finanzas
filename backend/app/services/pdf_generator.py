"""
services/pdf_generator.py
=========================
Renderiza un TaxReport a HTML usando Jinja2.

El HTML resultante se sirve directamente al navegador; el usuario imprime
a PDF con Ctrl+P. No se usa WeasyPrint ni ninguna dependencia nativa.

Formato de números: estilo español (coma decimal, punto de miles).
Los Decimal se convierten a cadena AQUÍ, en la frontera de presentación;
la plantilla recibe texto listo y no hace aritmética.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from app.services.tax_report import TaxReport

_TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "reports" / "templates"


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


def _build_context(report: TaxReport) -> dict:
    sale_lines = [
        {
            "security_name": line.security_name,
            "isin":          line.isin,
            "market":        line.market,
            "buy_date":      _fmt_date(line.buy_date),
            "sell_date":     _fmt_date(line.sell_date),
            "shares":        _fmt_shares(line.shares),
            "cost_eur":      _fmt_money(line.cost_eur),
            "proceeds_eur":  _fmt_money(line.proceeds_eur),
            "gain_eur":      _fmt_money(line.gain_eur),
            "gain_positive": line.gain_eur >= Decimal("0"),
            "loss_disallowed":  line.loss_disallowed,
            "disallowed_reason": line.disallowed_reason,
        }
        for line in report.sale_lines
    ]

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
        "year":                 report.year,
        "generated_at":         datetime.now().strftime("%d/%m/%Y %H:%M"),
        "sale_lines":           sale_lines,
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
        "warnings": report.warnings,
    }


def render_tax_report_html(report: TaxReport) -> str:
    env = Environment(
        loader=FileSystemLoader(str(_TEMPLATE_DIR)),
        autoescape=select_autoescape(["html"]),
    )
    return env.get_template("tax_report.html").render(**_build_context(report))
