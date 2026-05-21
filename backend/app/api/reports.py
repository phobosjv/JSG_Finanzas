"""
api/reports.py
==============
Generacion del informe fiscal IRPF en PDF.

GET /reports/tax/{year}         — descarga el PDF del informe fiscal.
GET /reports/tax/{year}/json    — mismos datos en JSON (para previsualizar).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.models import User
from app.repositories.tax_report_input import build_tax_report_input
from app.services.tax_report import build_tax_report
from app.services.pdf_generator import generate_tax_report_pdf, render_tax_report_html

router = APIRouter(prefix="/reports", tags=["reports"])


@router.get("/tax/{year}")
def download_tax_report(
    year: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    import tempfile, os
    sales, dividends = build_tax_report_input(db, user.id)
    report = build_tax_report(year, sales, dividends)
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        tmp_path = tmp.name
    try:
        generate_tax_report_pdf(report, tmp_path)
        with open(tmp_path, "rb") as f:
            pdf_bytes = f.read()
    finally:
        os.unlink(tmp_path)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="informe_fiscal_{year}.pdf"'
        },
    )


@router.get("/tax/{year}/html")
def preview_tax_report(
    year: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    sales, dividends = build_tax_report_input(db, user.id)
    report = build_tax_report(year, sales, dividends)
    html = render_tax_report_html(report)
    return Response(content=html, media_type="text/html")
