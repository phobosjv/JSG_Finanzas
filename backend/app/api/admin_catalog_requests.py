"""
api/admin_catalog_requests.py
==============================
Endpoints de administrador para gestionar solicitudes de catálogo y mensajes
de usuarios (v1.12.0, ampliado v1.13.0).

GET    /api/admin/catalog/requests?status=pending       — lista solicitudes.
GET    /api/admin/catalog/requests/pending-count        — nº solicitudes pendientes.
PATCH  /api/admin/catalog/requests/{id}/approve         — aprueba y crea el Security.
PATCH  /api/admin/catalog/requests/{id}/reject          — rechaza con notas opcionales.
GET    /api/admin/catalog/messages                      — lista mensajes de usuarios.
GET    /api/admin/catalog/messages/pending-count        — nº mensajes sin resolver.
POST   /api/admin/catalog/messages/{id}/reply           — responde al mensaje y notifica al usuario.
PATCH  /api/admin/catalog/messages/{id}/resolve         — marca mensaje como resuelto.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_admin
from app.models import MarketRow, Security, User
from app.models.catalog_requests import (
    CatalogMessageRow,
    SecurityRequestRow,
    UserNotificationRow,
)
from app.schemas.catalog_requests import (
    AdminMessageReply,
    CatalogMessageOut,
    RequestApprove,
    RequestReject,
    SecurityRequestOut,
)

log = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/catalog", tags=["admin"])


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _get_request_or_404(db: Session, request_id: int) -> SecurityRequestRow:
    req = db.get(SecurityRequestRow, request_id)
    if req is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Solicitud {request_id} no encontrada",
        )
    return req


def _build_request_out(req: SecurityRequestRow, db: Session) -> SecurityRequestOut:
    user = db.get(User, req.user_id)
    return SecurityRequestOut(
        id=req.id,
        user_id=req.user_id,
        username=user.username if user else None,
        ticker=req.ticker,
        isin=req.isin,
        name=req.name,
        market_id=req.market_id,
        currency=req.currency,
        status=req.status,
        security_id=req.security_id,
        reviewed_by=req.reviewed_by,
        reviewed_at=req.reviewed_at,
        notes=req.notes,
        created_at=req.created_at,
    )


def _delete_pending_notification(db: Session, user_id: int, request_id: int) -> None:
    """Elimina la notificación request_pending del usuario para esta solicitud."""
    db.execute(
        delete(UserNotificationRow).where(
            UserNotificationRow.user_id == user_id,
            UserNotificationRow.type == "request_pending",
            UserNotificationRow.related_id == request_id,
            UserNotificationRow.related_type == "security_request",
        )
    )


# ---------------------------------------------------------------------------
#  Listado de solicitudes
# ---------------------------------------------------------------------------

@router.get("/requests/pending-count")
def pending_requests_count(
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    count = db.scalar(
        select(func.count(SecurityRequestRow.id)).where(
            SecurityRequestRow.status == "pending"
        )
    ) or 0
    return {"count": count}


@router.get("/requests", response_model=list[SecurityRequestOut])
def list_requests(
    req_status: str = "pending",
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    """Lista solicitudes filtradas por status (pending|approved|rejected|all)."""
    q = select(SecurityRequestRow).order_by(SecurityRequestRow.created_at.desc())
    if req_status != "all":
        q = q.where(SecurityRequestRow.status == req_status)
    rows = db.scalars(q).all()
    return [_build_request_out(r, db) for r in rows]


# ---------------------------------------------------------------------------
#  Aprobar solicitud
# ---------------------------------------------------------------------------

@router.patch("/requests/{request_id}/approve", response_model=SecurityRequestOut)
def approve_request(
    request_id: int,
    body: RequestApprove,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    req = _get_request_or_404(db, request_id)
    if req.status != "pending":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"La solicitud ya está en estado '{req.status}'",
        )

    # Validar mercado destino (puede diferir del propuesto por el usuario)
    if db.get(MarketRow, body.market_id) is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"El mercado '{body.market_id}' no existe",
        )

    # Verificar que el ticker no esté ya en el catálogo
    existing = db.scalar(
        select(Security).where(Security.yahoo_ticker == req.ticker)
    )
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"El ticker '{req.ticker}' ya existe en el catálogo",
        )

    # Determinar divisa: usar la que viene del cuerpo si se indica, si no la de la solicitud
    currency = req.currency or "EUR"

    # Crear el Security en el catálogo
    sec = Security(
        name=req.name,
        isin=req.isin,
        yahoo_ticker=req.ticker,
        market=body.market_id,
        currency=currency,
    )
    db.add(sec)
    db.flush()

    # Actualizar la solicitud
    req.status = "approved"
    req.security_id = sec.id
    req.reviewed_by = admin.id
    req.reviewed_at = _now()
    req.notes = body.notes
    req.market_id = body.market_id  # actualizar al mercado final elegido por el admin

    # Sustituir notificación pending → approved
    _delete_pending_notification(db, req.user_id, req.id)
    db.add(UserNotificationRow(
        user_id=req.user_id,
        type="request_approved",
        title=f"Solicitud aprobada: {req.ticker}",
        body=(
            f"Tu solicitud para agregar '{req.name}' ({req.ticker}) "
            f"ha sido aprobada. Ya está disponible en el catálogo."
            + (f" Nota del administrador: {body.notes}" if body.notes else "")
        ),
        related_id=req.id,
        related_type="security_request",
        is_read=False,
    ))

    db.commit()
    db.refresh(req)
    return _build_request_out(req, db)


# ---------------------------------------------------------------------------
#  Rechazar solicitud
# ---------------------------------------------------------------------------

@router.patch("/requests/{request_id}/reject", response_model=SecurityRequestOut)
def reject_request(
    request_id: int,
    body: RequestReject,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    req = _get_request_or_404(db, request_id)
    if req.status != "pending":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"La solicitud ya está en estado '{req.status}'",
        )

    req.status = "rejected"
    req.reviewed_by = admin.id
    req.reviewed_at = _now()
    req.notes = body.notes

    _delete_pending_notification(db, req.user_id, req.id)
    db.add(UserNotificationRow(
        user_id=req.user_id,
        type="request_rejected",
        title=f"Solicitud rechazada: {req.ticker}",
        body=(
            f"Tu solicitud para agregar '{req.name}' ({req.ticker}) "
            "ha sido rechazada."
            + (f" Motivo: {body.notes}" if body.notes else "")
        ),
        related_id=req.id,
        related_type="security_request",
        is_read=False,
    ))

    db.commit()
    db.refresh(req)
    return _build_request_out(req, db)


# ---------------------------------------------------------------------------
#  Mensajes de usuarios
# ---------------------------------------------------------------------------

def _build_message_out(msg: CatalogMessageRow, db: Session) -> CatalogMessageOut:
    user = db.get(User, msg.user_id)
    return CatalogMessageOut(
        id=msg.id,
        user_id=msg.user_id,
        username=user.username if user else None,
        subject=msg.subject,
        message=msg.message,
        security_request_id=msg.security_request_id,
        is_resolved=msg.is_resolved,
        admin_reply=msg.admin_reply,
        admin_reply_at=msg.admin_reply_at,
        created_at=msg.created_at,
    )


@router.get("/messages/pending-count")
def pending_messages_count(
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    count = db.scalar(
        select(func.count(CatalogMessageRow.id)).where(
            CatalogMessageRow.is_resolved == False  # noqa: E712
        )
    ) or 0
    return {"count": count}


@router.get("/messages", response_model=list[CatalogMessageOut])
def list_messages(
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    rows = db.scalars(
        select(CatalogMessageRow).order_by(CatalogMessageRow.created_at.desc())
    ).all()
    return [_build_message_out(msg, db) for msg in rows]


@router.post("/messages/{message_id}/reply", response_model=CatalogMessageOut)
def reply_message(
    message_id: int,
    body: AdminMessageReply,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    """Responde al mensaje del usuario y crea una notificación in-app para él."""
    msg = db.get(CatalogMessageRow, message_id)
    if msg is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Mensaje {message_id} no encontrado",
        )
    if msg.admin_reply is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Este mensaje ya tiene una respuesta del administrador",
        )

    msg.admin_reply = body.reply
    msg.admin_reply_at = _now()
    msg.is_resolved = True

    db.add(UserNotificationRow(
        user_id=msg.user_id,
        type="message_reply",
        title="El administrador ha respondido a tu mensaje",
        body=body.reply,
        related_id=msg.id,
        related_type="catalog_message",
        is_read=False,
    ))
    db.commit()
    db.refresh(msg)
    return _build_message_out(msg, db)


@router.patch("/messages/{message_id}/resolve", status_code=status.HTTP_204_NO_CONTENT)
def resolve_message(
    message_id: int,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    msg = db.get(CatalogMessageRow, message_id)
    if msg is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Mensaje {message_id} no encontrado",
        )
    msg.is_resolved = True
    db.commit()
