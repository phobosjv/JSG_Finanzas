"""
api/securities.py
=================
CRUD del catalogo de valores. Lectura para todos los usuarios autenticados;
escritura (POST/PATCH/DELETE) solo para administradores.

GET    /securities        — lista todos los valores.
GET    /securities/{id}   — devuelve un valor.
POST   /securities        — da de alta un valor nuevo (admin).
PATCH  /securities/{id}   — actualiza un valor (admin).
DELETE /securities/{id}   — elimina un valor (admin; falla si tiene posiciones: RESTRICT).
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db, require_admin
from app.api.admin_markets import _get_supported_currencies
from app.models import MarketRow, Security, User
from app.schemas.security import SecurityCreate, SecurityOut

router = APIRouter(prefix="/securities", tags=["securities"])


def _validate_market(db: Session, code: str) -> None:
    if db.get(MarketRow, code) is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"El mercado '{code}' no existe en el catálogo de mercados",
        )


def _validate_currency(db: Session, currency: str) -> None:
    if currency not in _get_supported_currencies(db):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"La divisa '{currency}' no está entre las soportadas (configúrala en Admin)",
        )


@router.get("", response_model=list[SecurityOut])
def list_securities(
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    return db.scalars(select(Security).order_by(Security.name)).all()


@router.post("", response_model=SecurityOut, status_code=status.HTTP_201_CREATED)
def create_security(
    body: SecurityCreate,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    _validate_market(db, body.market)
    _validate_currency(db, body.currency)
    sec = Security(**body.model_dump())
    db.add(sec)
    try:
        db.commit()
        db.refresh(sec)
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"El ticker '{body.yahoo_ticker}' ya existe",
        )
    return sec


@router.get("/{security_id}", response_model=SecurityOut)
def get_security(
    security_id: int,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    sec = db.get(Security, security_id)
    if sec is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No encontrado")
    return sec


@router.patch("/{security_id}", response_model=SecurityOut)
def update_security(
    security_id: int,
    body: SecurityCreate,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    _validate_market(db, body.market)
    _validate_currency(db, body.currency)
    sec = db.get(Security, security_id)
    if sec is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No encontrado")
    for k, v in body.model_dump().items():
        setattr(sec, k, v)
    try:
        db.commit()
        db.refresh(sec)
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"El ticker '{body.yahoo_ticker}' ya existe",
        )
    return sec


@router.delete("/{security_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_security(
    security_id: int,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    sec = db.get(Security, security_id)
    if sec is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No encontrado")
    db.delete(sec)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="El valor tiene posiciones o historico asociado y no se puede eliminar",
        )
