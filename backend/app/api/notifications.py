"""
api/notifications.py
====================
Endpoints para gestionar notificaciones in-app del usuario (campana).

GET    /api/notifications         — lista notificaciones del usuario.
PATCH  /api/notifications/{id}/read  — marca como leída.
DELETE /api/notifications/{id}    — elimina la notificación.
POST   /api/notifications/{id}/reply — elimina + crea mensaje al admin.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.models import User
from app.models.catalog_requests import (
    CatalogMessageRow,
    UserNotificationRow,
)
from app.schemas.catalog_requests import NotificationReply, UserNotificationOut

router = APIRouter(prefix="/notifications", tags=["notifications"])


def _get_notif_or_403(db: Session, notif_id: int, user_id: int) -> UserNotificationRow:
    notif = db.get(UserNotificationRow, notif_id)
    if notif is None or notif.user_id != user_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Notificación no encontrada",
        )
    return notif


def _to_out(n: UserNotificationRow) -> UserNotificationOut:
    return UserNotificationOut(
        id=n.id,
        type=n.type,
        title=n.title,
        body=n.body,
        related_id=n.related_id,
        related_type=n.related_type,
        is_read=n.is_read,
        created_at=n.created_at,
    )


@router.get("", response_model=list[UserNotificationOut])
def list_notifications(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    rows = db.scalars(
        select(UserNotificationRow)
        .where(UserNotificationRow.user_id == user.id)
        .order_by(UserNotificationRow.created_at.desc())
    ).all()
    return [_to_out(n) for n in rows]


@router.patch("/{notif_id}/read", response_model=UserNotificationOut)
def mark_read(
    notif_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    notif = _get_notif_or_403(db, notif_id, user.id)
    notif.is_read = True
    db.commit()
    db.refresh(notif)
    return _to_out(notif)


@router.delete("/{notif_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_notification(
    notif_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    notif = _get_notif_or_403(db, notif_id, user.id)
    db.delete(notif)
    db.commit()


@router.post("/{notif_id}/reply", status_code=status.HTTP_204_NO_CONTENT)
def reply_and_dismiss(
    notif_id: int,
    body: NotificationReply,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Elimina la notificación y crea un mensaje al admin.

    Si la notificación está vinculada a una security_request, el mensaje
    queda enlazado a esa solicitud para que el admin tenga contexto.
    """
    notif = _get_notif_or_403(db, notif_id, user.id)

    security_request_id: int | None = None
    if notif.related_type == "security_request" and notif.related_id:
        security_request_id = notif.related_id

    msg = CatalogMessageRow(
        user_id=user.id,
        message=body.message,
        security_request_id=security_request_id,
        is_resolved=False,
    )
    db.add(msg)
    db.delete(notif)
    db.commit()
