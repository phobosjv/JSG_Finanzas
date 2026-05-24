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
# Resumen ejecutivo: base imponible + tramos IRPF
# ---------------------------------------------------------------------------

def _build_tax_summary(report: TaxReport) -> dict:
    """
    Calcula el resumen fiscal para la primera página del informe.

    Base imponible estimada = max(0, resultado_neto_ventas) + dividendos_netos.
    Nota: esta es una estimación simplificada; el cálculo definitivo
    corresponde a Hacienda y puede diferir.
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

    commission_lines = [
        {
            "security_name": line.security_name,
            "isin":          line.isin,
            "buy_fee_eur":   _fmt_money(line.buy_fee_eur),
            "sell_fee_eur":  _fmt_money(line.sell_fee_eur),
            "total_fee_eur": _fmt_money(line.total_fee_eur),
        }
        for line in report.commission_lines
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
        "summary":              _build_tax_summary(report),
        "sale_lines":           sale_lines,
        "commission_lines":     commission_lines,
        "dividend_lines":       dividend_lines,
        "net_capital_positive": report.net_capital_result_eur >= Decimal("0"),
        "totals": {
            "gains":              _fmt_money(report.total_gains_eur),
            "losses_computable":  _fmt_money(report.total_losses_computable_eur),
            "losses_disallowed":  _fmt_money(report.total_losses_disallowed_eur),
            "net_capital":        _fmt_money(report.net_capital_result_eur),
            "commission_buy":     _fmt_money(report.total_buy_fee_eur),
            "commission_sell":    _fmt_money(report.total_sell_fee_eur),
            "commission_total":   _fmt_money(report.total_commission_eur),
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
