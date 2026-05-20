"""
api/securities.py
=================
CRUD del catalogo de valores (Utilidades).

GET    /securities        — lista todos los valores.
POST   /securities        — da de alta un valor nuevo.
DELETE /securities/{id}   — elimina un valor (falla si tiene posiciones: RESTRICT).
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.models import Security, User
from app.schemas.security import SecurityCreate, SecurityOut

router = APIRouter(prefix="/securities", tags=["securities"])


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
    _user: User = Depends(get_current_user),
):
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
    _user: User = Depends(get_current_user),
):
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
    _user: User = Depends(get_current_user),
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
