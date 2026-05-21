"""
api/reports.py
==============
Informe fiscal IRPF.

GET /reports/tax/{year}/html  — informe en HTML (abrir en navegador, imprimir con Ctrl+P).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.models import User
from app.repositories.tax_report_input import build_tax_report_input
from app.services.tax_report import build_tax_report
from app.services.pdf_generator import render_tax_report_html

router = APIRouter(prefix="/reports", tags=["reports"])


@router.get("/tax/{year}/html")
def get_tax_report_html(
    year: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    sales, dividends = build_tax_report_input(db, user.id)
    report = build_tax_report(year, sales, dividends)
    html = render_tax_report_html(report)
    return Response(content=html, media_type="text/html")
