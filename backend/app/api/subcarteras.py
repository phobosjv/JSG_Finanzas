"""
api/subcarteras.py
==================
Gestión de subcarteras: agrupaciones personalizadas de posiciones por usuario.

GET    /subcarteras                              — listar subcarteras del usuario
POST   /subcarteras                              — crear subcartera
PATCH  /subcarteras/{id}                         — actualizar nombre/descripción
DELETE /subcarteras/{id}                         — eliminar subcartera
POST   /subcarteras/{id}/positions/{pos_id}      — añadir posición
DELETE /subcarteras/{id}/positions/{pos_id}      — quitar posición
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.models import Position, User
from app.repositories import subcarteras as repo
from app.schemas.subcarteras import SubcarteraCreate, SubcarteraOut, SubcarteraUpdate

router = APIRouter(prefix="/subcarteras", tags=["subcarteras"])


def _require_subcartera(db: Session, sc_id: int, user_id: int):
    """404 si la subcartera no existe o no pertenece al usuario."""
    sc = repo.get_subcartera(db, sc_id, user_id)
    if sc is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Subcartera no encontrada",
        )
    return sc


def _require_position_owner(db: Session, position_id: int, user_id: int) -> None:
    """403 si la posición no pertenece al usuario."""
    pos = db.scalar(
        select(Position).where(
            Position.id == position_id,
            Position.user_id == user_id,
        )
    )
    if pos is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Posición no encontrada o no pertenece al usuario",
        )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("", response_model=list[SubcarteraOut])
def list_subcarteras(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Todas las subcarteras del usuario con sus position_ids."""
    return repo.get_user_subcarteras(db, user.id)


@router.post("", response_model=SubcarteraOut, status_code=status.HTTP_201_CREATED)
def create_subcartera(
    body: SubcarteraCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    out = repo.create_subcartera(db, user.id, body.name, body.description)
    db.commit()
    return out


@router.patch("/{sc_id}", response_model=SubcarteraOut)
def update_subcartera(
    sc_id: int,
    body: SubcarteraUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _require_subcartera(db, sc_id, user.id)
    out = repo.update_subcartera(
        db, sc_id, user.id, name=body.name, description=body.description
    )
    db.commit()
    return out


@router.delete("/{sc_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_subcartera(
    sc_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    found = repo.delete_subcartera(db, sc_id, user.id)
    if not found:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Subcartera no encontrada",
        )
    db.commit()


@router.post(
    "/{sc_id}/positions/{position_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def add_position(
    sc_id: int,
    position_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _require_subcartera(db, sc_id, user.id)
    _require_position_owner(db, position_id, user.id)
    repo.add_position(db, sc_id, position_id)
    db.commit()


@router.delete(
    "/{sc_id}/positions/{position_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def remove_position(
    sc_id: int,
    position_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _require_subcartera(db, sc_id, user.id)
    repo.remove_position(db, sc_id, position_id)
    db.commit()
