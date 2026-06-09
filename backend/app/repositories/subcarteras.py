"""
repositories/subcarteras.py
============================
I/O puro para subcarteras. Sin lógica de negocio ni HTTP.
"""
from __future__ import annotations

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models import SubcarteraRow, SubcarteraPositionRow
from app.schemas.subcarteras import SubcarteraOut


# ---------------------------------------------------------------------------
# Helpers internos
# ---------------------------------------------------------------------------

def _position_ids_for(db: Session, subcartera_id: int) -> list[int]:
    """Devuelve los position_ids asignados a una subcartera, ordenados."""
    return list(
        db.scalars(
            select(SubcarteraPositionRow.position_id)
            .where(SubcarteraPositionRow.subcartera_id == subcartera_id)
            .order_by(SubcarteraPositionRow.position_id)
        ).all()
    )


def _to_out(db: Session, row: SubcarteraRow) -> SubcarteraOut:
    return SubcarteraOut(
        id=row.id,
        name=row.name,
        description=row.description,
        position_ids=_position_ids_for(db, row.id),
        created_at=row.created_at,
    )


# ---------------------------------------------------------------------------
# CRUD de subcarteras
# ---------------------------------------------------------------------------

def get_user_subcarteras(db: Session, user_id: int) -> list[SubcarteraOut]:
    """Todas las subcarteras del usuario, con sus position_ids."""
    rows = db.scalars(
        select(SubcarteraRow)
        .where(SubcarteraRow.user_id == user_id)
        .order_by(SubcarteraRow.created_at)
    ).all()
    return [_to_out(db, r) for r in rows]


def get_subcartera(db: Session, sc_id: int, user_id: int) -> SubcarteraRow | None:
    """Subcartera concreta del usuario o None."""
    return db.scalar(
        select(SubcarteraRow).where(
            SubcarteraRow.id == sc_id,
            SubcarteraRow.user_id == user_id,
        )
    )


def create_subcartera(
    db: Session, user_id: int, name: str, description: str | None
) -> SubcarteraOut:
    row = SubcarteraRow(user_id=user_id, name=name, description=description)
    db.add(row)
    db.flush()  # obtener id sin commit
    db.refresh(row)
    return _to_out(db, row)


def update_subcartera(
    db: Session,
    sc_id: int,
    user_id: int,
    *,
    name: str | None,
    description: str | None,
) -> SubcarteraOut | None:
    row = get_subcartera(db, sc_id, user_id)
    if row is None:
        return None
    if name is not None:
        row.name = name
    if description is not None:
        row.description = description
    db.flush()
    return _to_out(db, row)


def delete_subcartera(db: Session, sc_id: int, user_id: int) -> bool:
    """Elimina la subcartera. Devuelve True si existía, False si no."""
    row = get_subcartera(db, sc_id, user_id)
    if row is None:
        return False
    db.delete(row)
    db.flush()
    return True


# ---------------------------------------------------------------------------
# Gestión de posiciones en una subcartera
# ---------------------------------------------------------------------------

def add_position(db: Session, sc_id: int, position_id: int) -> None:
    """Añade la posición a la subcartera (idempotente: ignora duplicados)."""
    exists = db.scalar(
        select(SubcarteraPositionRow).where(
            SubcarteraPositionRow.subcartera_id == sc_id,
            SubcarteraPositionRow.position_id == position_id,
        )
    )
    if exists is None:
        db.add(SubcarteraPositionRow(subcartera_id=sc_id, position_id=position_id))
        db.flush()


def remove_position(db: Session, sc_id: int, position_id: int) -> None:
    """Elimina la posición de la subcartera (no-op si no estaba)."""
    db.execute(
        delete(SubcarteraPositionRow).where(
            SubcarteraPositionRow.subcartera_id == sc_id,
            SubcarteraPositionRow.position_id == position_id,
        )
    )
    db.flush()
