"""
api/deps.py
===========
Dependencias FastAPI compartidas por todos los routers.

- get_db          : sesion SQLAlchemy por peticion.
- get_current_user: usuario autenticado; lanza 401 si no hay sesion valida.
- require_admin   : exige is_admin=True; lanza 403 si no.
"""

from __future__ import annotations

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.auth.session import get_current_user_id
from app.models import User


def get_current_user(
    request: Request,
    db: Session = Depends(get_db),
) -> User:
    user_id = get_current_user_id(request)
    user = db.scalar(select(User).where(User.id == user_id))
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuario no encontrado",
        )
    return user


def require_admin(user: User = Depends(get_current_user)) -> User:
    if not user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Se requiere rol de administrador",
        )
    return user
