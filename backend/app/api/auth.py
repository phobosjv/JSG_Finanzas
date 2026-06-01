"""
api/auth.py
===========
Endpoints de autenticacion: login y logout.

POST /auth/login   — verifica credenciales, crea cookie de sesion.
POST /auth/logout  — borra la cookie de sesion.
GET  /auth/me      — devuelve el usuario de la sesion activa.
"""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Response, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.auth.security import hash_password, needs_rehash, verify_password
from app.auth.session import clear_session_cookie, create_session_cookie
from app.models import User, UserStatusLog
from app.schemas.auth import LoginRequest, SelfChangePasswordRequest, UserOut

router = APIRouter(prefix="/auth", tags=["auth"])

_DISABLED_MSG = "Contactar con el administrador"


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
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=_DISABLED_MSG,
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
