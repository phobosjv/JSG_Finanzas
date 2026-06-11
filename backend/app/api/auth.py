"""
api/auth.py
===========
Endpoints de autenticacion: login y logout.

POST /auth/login              — verifica credenciales, crea cookie de sesion.
POST /auth/logout             — borra la cookie de sesion.
GET  /auth/me                 — devuelve el usuario de la sesion activa.
POST /auth/request-renewal    — usuario caducado solicita renovación de acceso.
"""

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.auth.security import hash_password, needs_rehash, verify_password
from app.auth.session import clear_session_cookie, create_session_cookie
from app.models import User, UserStatusLog
from app.models.catalog_requests import CatalogMessageRow
from app.schemas.auth import LoginRequest, RenewalRequest, SelfChangePasswordRequest, UserOut
from app.services.email_notifications import get_app_name, notify_admins, notify_admins_inapp

log = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])

_DISABLED_MSG = "Contactar con el administrador"
_EXPIRED_MSG  = "account_expired"


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


@router.post("/login", response_model=UserOut)
def login(body: LoginRequest, response: Response, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.username == body.username))
    if user is None or not verify_password(body.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenciales incorrectas",
        )

    # Comprobar caducidad: si expires_at ha pasado, deshabilitar automáticamente
    if user.expires_at is not None and _now() >= user.expires_at:
        if user.is_enabled:
            user.is_enabled = False
            db.add(UserStatusLog(
                user_id=user.id,
                actor_id=None,
                status="expired",
                annotation="Cuenta caducada automáticamente",
                created_at=_now(),
            ))
            db.commit()
            # Notificar a los admins del primer intento de login tras la caducidad
            _notify_admins_user_expired(db, user)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=_EXPIRED_MSG,
        )

    # Comprobar que la cuenta está habilitada
    if not user.is_enabled:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=_DISABLED_MSG,
        )

    # Actualizar hash si el algoritmo ha sido marcado obsoleto
    if needs_rehash(user.password_hash):
        user.password_hash = hash_password(body.password)
        db.commit()

    # Registrar fecha de último acceso
    user.last_login_at = _now()
    db.commit()

    create_session_cookie(response, user.id)
    return user


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(response: Response):
    clear_session_cookie(response)


@router.get("/me", response_model=UserOut)
def me(current_user: User = Depends(get_current_user)):
    return current_user


@router.patch("/password", status_code=status.HTTP_204_NO_CONTENT)
def change_own_password(
    body: SelfChangePasswordRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if not verify_password(body.current_password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Contraseña actual incorrecta",
        )
    user.password_hash = hash_password(body.new_password)
    db.commit()


@router.post("/request-renewal", status_code=status.HTTP_200_OK)
def request_renewal(body: RenewalRequest, db: Session = Depends(get_db)):
    """Usuario caducado solicita al administrador la renovación de su acceso.

    Siempre devuelve 200 (no revela si el usuario existe) pero solo notifica
    a los admins si el usuario existe y su cuenta ha caducado.
    """
    user = db.scalar(select(User).where(User.username == body.username))

    # Solo procesamos usuarios no-admin con expires_at en el pasado
    now = _now()
    if (
        user is not None
        and not user.is_admin
        and user.expires_at is not None
        and user.expires_at <= now
    ):
        # Idempotencia: ignorar si ya hay una solicitud pendiente sin resolver
        already_pending = db.scalar(
            select(CatalogMessageRow).where(
                CatalogMessageRow.user_id == user.id,
                CatalogMessageRow.subject == "Solicitud de renovación de acceso",
                CatalogMessageRow.is_resolved == False,  # noqa: E712
            )
        )
        if not already_pending:
            exp_str = user.expires_at.strftime("%d/%m/%Y")
            title = f"Solicitud de renovación: {user.username}"
            body_text = (
                f"El usuario '{user.username}' solicita renovar su acceso "
                f"(cuenta caducada el {exp_str}). "
                f"Puedes actualizar su fecha de caducidad desde el panel de administración."
            )
            app_label = get_app_name(db)
            try:
                notify_admins_inapp(db, type_="renewal_request", title=title, body=body_text)
                db.add(CatalogMessageRow(
                    user_id=user.id,
                    subject="Solicitud de renovación de acceso",
                    message=body_text,
                ))
                db.commit()  # Persistir antes de la llamada remota (email puede fallar)
                notify_admins(
                    db,
                    subject=f"[{app_label}] Solicitud de renovación: {user.username}",
                    body_html=(
                        f"<p>El usuario <strong>{user.username}</strong> solicita renovar su "
                        f"acceso. Su cuenta caducó el {exp_str}.</p>"
                        f"<p>Puedes renovar el acceso desde el panel de administración → Usuarios.</p>"
                    ),
                )
            except Exception:
                log.exception("Error notificando renovación de %s", user.username)

    return {"ok": True}


# ---------------------------------------------------------------------------
#  Helpers internos
# ---------------------------------------------------------------------------

def _notify_admins_user_expired(db: Session, user: User) -> None:
    """Notifica a los admins (in-app + email) cuando una cuenta caduca en login."""
    exp_str = user.expires_at.strftime("%d/%m/%Y") if user.expires_at else "—"
    title = f"Cuenta caducada: {user.username}"
    body_text = (
        f"La cuenta del usuario '{user.username}' ha caducado "
        f"(fecha límite: {exp_str}). "
        f"Puedes renovar el acceso desde el panel de administración."
    )
    app_label = get_app_name(db)
    try:
        notify_admins_inapp(db, type_="user_expired", title=title, body=body_text)
        db.commit()  # Persistir antes de la llamada remota (email puede fallar)
        notify_admins(
            db,
            subject=f"[{app_label}] Cuenta caducada: {user.username}",
            body_html=(
                f"<p>La cuenta del usuario <strong>{user.username}</strong> "
                f"ha caducado el {exp_str}.</p>"
                f"<p>Puedes renovar el acceso desde el panel de administración → Usuarios.</p>"
            ),
        )
    except Exception:
        log.exception("Error notificando caducidad de %s a los admins", user.username)
