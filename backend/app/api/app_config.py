"""
api/app_config.py
=================
Endpoints públicos (sin autenticación) para obtener la configuración visible
de la aplicación.

GET /config               — devuelve {app_name}.
GET /config/tax-brackets  — lista de tramos IRPF del ahorro (para la UI).
"""

import base64
import binascii

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.models import AppConfig, TaxBracketRow
from app.schemas.tax_bracket import TaxBracketOut

router = APIRouter(prefix="/config", tags=["config"])

_APP_NAME_DEFAULT = "JSG Soft."


def _get_supported_currencies_public(db) -> list[str]:
    """Versión pública del helper (sin import circular con admin_markets)."""
    row = db.get(AppConfig, "supported_currencies")
    raw = row.value if row else "USD"
    extras = [c.strip().upper() for c in raw.split(",")
              if c.strip() and c.strip().upper() != "EUR"]
    return ["EUR"] + extras


@router.get("")
def get_public_config(db: Session = Depends(get_db)):
    name = db.get(AppConfig, "app_name")
    logo_updated = db.get(AppConfig, "logo_updated_at")
    return {
        "app_name": name.value if name else _APP_NAME_DEFAULT,
        "has_logo": db.get(AppConfig, "logo_data") is not None,
        "logo_updated_at": logo_updated.value if logo_updated else None,
        "supported_currencies": _get_supported_currencies_public(db),
    }


@router.get("/logo")
def get_logo(db: Session = Depends(get_db)):
    """Devuelve el logotipo de la app con su Content-Type. 404 si no hay."""
    data = db.get(AppConfig, "logo_data")
    mime = db.get(AppConfig, "logo_mime")
    if data is None or mime is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sin logotipo")
    try:
        blob = base64.b64decode(data.value, validate=True)
    except (binascii.Error, ValueError):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Logotipo corrupto")
    return Response(
        content=blob,
        media_type=mime.value,
        headers={"Cache-Control": "public, max-age=300"},
    )


@router.get("/tax-brackets", response_model=list[TaxBracketOut])
def get_tax_brackets(db: Session = Depends(get_db)):
    """Lista pública de tramos IRPF ordenados por sort_order."""
    return db.scalars(
        select(TaxBracketRow).order_by(TaxBracketRow.sort_order, TaxBracketRow.id)
    ).all()
