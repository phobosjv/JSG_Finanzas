"""
api/app_config.py
=================
Endpoints públicos (sin autenticación) para obtener la configuración visible
de la aplicación.

GET /config               — devuelve {app_name}.
GET /config/tax-brackets  — lista de tramos IRPF del ahorro (para la UI).
"""

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.models import AppConfig, TaxBracketRow
from app.schemas.tax_bracket import TaxBracketOut

router = APIRouter(prefix="/config", tags=["config"])

_APP_NAME_DEFAULT = "FJS Finanzas"


@router.get("")
def get_public_config(db: Session = Depends(get_db)):
    row = db.get(AppConfig, "app_name")
    return {"app_name": row.value if row else _APP_NAME_DEFAULT}


@router.get("/tax-brackets", response_model=list[TaxBracketOut])
def get_tax_brackets(db: Session = Depends(get_db)):
    """Lista pública de tramos IRPF ordenados por sort_order."""
    return db.scalars(
        select(TaxBracketRow).order_by(TaxBracketRow.sort_order, TaxBracketRow.id)
    ).all()
