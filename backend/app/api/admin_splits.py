"""
api/admin_splits.py
===================
CRUD de splits/contrasplits por valor. Solo administradores.

GET    /admin/securities/{security_id}/splits  — lista los splits de un valor.
POST   /admin/securities/{security_id}/splits  — registra un nuevo split.
DELETE /admin/splits/{split_id}                — elimina un split.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_admin
from app.models import Security, SecuritySplit, User
from app.schemas.market_admin import SplitIn, SplitOut

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/securities/{security_id}/splits", response_model=list[SplitOut])
def list_splits(
    security_id: int,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    if db.get(Security, security_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Valor no encontrado")
    rows = db.scalars(
        select(SecuritySplit)
        .where(SecuritySplit.security_id == security_id)
        .order_by(SecuritySplit.ex_date)
    ).all()
    return rows


@router.post(
    "/securities/{security_id}/splits",
    response_model=SplitOut,
    status_code=status.HTTP_201_CREATED,
)
def create_split(
    security_id: int,
    body: SplitIn,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    if db.get(Security, security_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Valor no encontrado")
    row = SecuritySplit(
        security_id=security_id,
        ex_date=body.ex_date.isoformat(),
        ratio_num=body.ratio_num,
        ratio_den=body.ratio_den,
        notes=body.notes,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@router.delete("/splits/{split_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_split(
    split_id: int,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    row = db.get(SecuritySplit, split_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Split no encontrado")
    db.delete(row)
    db.commit()
