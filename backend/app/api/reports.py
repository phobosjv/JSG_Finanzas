"""
api/reports.py
==============
Informe fiscal IRPF.

GET /reports/tax/{year}/summary  — totales del ejercicio en JSON.
GET /reports/tax/{year}/html     — informe completo en HTML (Ctrl+P → PDF).
"""

from __future__ import annotations

from decimal import Decimal

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.models import TaxBracketRow, User
from app.repositories.tax_report_input import build_tax_report_input
from app.services.tax_report import build_tax_report
from app.services.pdf_generator import render_tax_report_html

router = APIRouter(prefix="/reports", tags=["reports"])


@router.get("/tax/{year}/summary")
def get_tax_report_summary(
    year: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    sales, dividends = build_tax_report_input(db, user.id)
    report = build_tax_report(year, sales, dividends)
    return {
        "year": report.year,
        "net_capital_result_eur":        float(report.net_capital_result_eur),
        "total_gains_eur":               float(report.total_gains_eur),
        "total_losses_computable_eur":   float(report.total_losses_computable_eur),
        "total_losses_disallowed_eur":   float(report.total_losses_disallowed_eur),
        "total_commission_eur":          float(report.total_commission_eur),
        "total_dividends_gross_eur":     float(report.total_dividends_gross_eur),
        "total_dividends_withholding_eur": float(report.total_dividends_withholding_eur),
        "total_dividends_net_eur":       float(report.total_dividends_net_eur),
        "warnings":                      report.warnings,
    }


@router.get("/tax/{year}/html")
def get_tax_report_html(
    year: int,
    lang: str = Query(default="es", pattern="^(es|en)$"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    sales, dividends = build_tax_report_input(db, user.id)
    report = build_tax_report(year, sales, dividends)

    # Cargar tramos configurados en BD; si la tabla está vacía usar los hardcodeados (fallback)
    bracket_rows = db.scalars(
        select(TaxBracketRow).order_by(TaxBracketRow.sort_order, TaxBracketRow.id)
    ).all()
    brackets = (
        [(r.max_amount, Decimal(str(r.rate))) for r in bracket_rows]
        if bracket_rows else None
    )

    html = render_tax_report_html(report, lang=lang, brackets=brackets)
    return Response(content=html, media_type="text/html")
