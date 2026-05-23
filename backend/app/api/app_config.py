"""
api/app_config.py
=================
Endpoint público (sin autenticación) para obtener la configuración visible
de la aplicación, como el nombre personalizable.

GET /config — devuelve {app_name}.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.models import AppConfig

router = APIRouter(prefix="/config", tags=["config"])

_APP_NAME_DEFAULT = "FJS Finanzas"


@router.get("")
def get_public_config(db: Session = Depends(get_db)):
    row = db.get(AppConfig, "app_name")
    return {"app_name": row.value if row else _APP_NAME_DEFAULT}
