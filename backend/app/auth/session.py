"""
auth/session.py
===============
Cookie de sesion firmada con itsdangerous (TimestampSigner).

Formato de la cookie
---------------------
El valor de la cookie es un token firmado que contiene el user_id
serializado como string. La firma incluye un timestamp, lo que permite
expirar tokens sin guardar estado en servidor.

Flujo
-----
  Login exitoso   → create_session_cookie() → Set-Cookie al cliente
  Cada peticion   → get_current_user_id()   → verifica firma y vigencia
  Logout          → clear_session_cookie()  → Set-Cookie con Max-Age=0

Por que itsdangerous y no JWT
------------------------------
JWT requiere libreria extra y serializa claims en base64 legible.
itsdangerous firma cualquier payload con HMAC-SHA1 usando la SECRET_KEY
de la app. Es suficiente para una app personal de uso privado y evita
una dependencia mas.

Seguridad de la cookie
-----------------------
- httponly=True  : JavaScript no puede leer la cookie (protege XSS).
- samesite=lax   : Protege CSRF en la mayoria de flujos.
- secure         : Controlado por settings.cookie_secure (false por defecto;
                   activar solo si se despliega con HTTPS).
"""

from __future__ import annotations

from itsdangerous import BadSignature, SignatureExpired, TimestampSigner
from fastapi import Cookie, HTTPException, Request, Response, status

from app.config import get_settings

_COOKIE_NAME = "session"


def _signer() -> TimestampSigner:
    return TimestampSigner(get_settings().secret_key)


def create_session_cookie(response: Response, user_id: int) -> None:
    """Firma user_id y lo escribe como cookie en la respuesta."""
    settings = get_settings()
    token = _signer().sign(str(user_id)).decode()
    max_age = settings.access_token_expire_minutes * 60
    response.set_cookie(
        key=_COOKIE_NAME,
        value=token,
        httponly=True,
        samesite="lax",
        secure=settings.cookie_secure,
        max_age=max_age,
    )


def clear_session_cookie(response: Response) -> None:
    """Elimina la cookie de sesion del cliente."""
    response.delete_cookie(key=_COOKIE_NAME, httponly=True, samesite="lax")


def get_current_user_id(request: Request) -> int:
    """
    Extrae y verifica el user_id de la cookie de sesion.
    Lanza HTTP 401 si la cookie falta, es invalida o ha expirado.
    """
    token = request.cookies.get(_COOKIE_NAME)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="No autenticado",
        )
    settings = get_settings()
    max_age = settings.access_token_expire_minutes * 60
    try:
        user_id_bytes = _signer().unsign(token, max_age=max_age)
        return int(user_id_bytes.decode())
    except SignatureExpired:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Sesion expirada",
        )
    except (BadSignature, ValueError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token de sesion invalido",
        )
