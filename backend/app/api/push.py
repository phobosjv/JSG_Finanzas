"""
api/push.py
===========
Web Push Notifications: registro de suscripciones y entrega de la clave VAPID pública.

GET  /api/push/vapid-key  — devuelve la clave pública VAPID (sin auth)
POST /api/push/subscribe   — registra o actualiza la suscripción del dispositivo
DELETE /api/push/subscribe — elimina la suscripción del dispositivo actual
"""
from __future__ import annotations

import base64
import json
import logging

from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.models import AppConfig, PushSubscription, User

log = logging.getLogger(__name__)
router = APIRouter(prefix="/push", tags=["push"])

# ---------------------------------------------------------------------------
#  VAPID — generación y lectura de claves
# ---------------------------------------------------------------------------

_VAPID_PRIVATE_KEY = "vapid_private_key"
_VAPID_PUBLIC_KEY  = "vapid_public_key"
_VAPID_EMAIL       = "vapid_email"


def _generate_vapid_keys() -> tuple[str, str]:
    """Genera un par de claves VAPID (EC P-256). Devuelve (pem_privada, b64url_publica)."""
    from cryptography.hazmat.primitives.asymmetric.ec import generate_private_key, SECP256R1
    from cryptography.hazmat.primitives.serialization import (
        Encoding, PrivateFormat, PublicFormat, NoEncryption,
    )
    from cryptography.hazmat.backends import default_backend

    private_key = generate_private_key(SECP256R1(), default_backend())
    private_pem = private_key.private_bytes(
        Encoding.PEM, PrivateFormat.TraditionalOpenSSL, NoEncryption()
    ).decode()
    public_bytes = private_key.public_key().public_bytes(
        Encoding.X962, PublicFormat.UncompressedPoint
    )
    public_b64 = base64.urlsafe_b64encode(public_bytes).rstrip(b"=").decode()
    return private_pem, public_b64


def ensure_vapid_keys(db: Session) -> None:
    """Genera y almacena claves VAPID en app_config si no existen todavía."""
    if db.get(AppConfig, _VAPID_PUBLIC_KEY):
        return
    private_pem, public_b64 = _generate_vapid_keys()
    db.merge(AppConfig(key=_VAPID_PRIVATE_KEY, value=private_pem))
    db.merge(AppConfig(key=_VAPID_PUBLIC_KEY,  value=public_b64))
    db.merge(AppConfig(key=_VAPID_EMAIL,       value="mailto:admin@jsg-portfolio.com"))
    db.commit()
    log.info("Claves VAPID generadas y almacenadas.")


def get_vapid_private_key(db: Session) -> str | None:
    row = db.get(AppConfig, _VAPID_PRIVATE_KEY)
    return row.value if row else None


def get_vapid_public_key(db: Session) -> str | None:
    row = db.get(AppConfig, _VAPID_PUBLIC_KEY)
    return row.value if row else None


def get_vapid_email(db: Session) -> str:
    row = db.get(AppConfig, _VAPID_EMAIL)
    return row.value if row else "mailto:admin@jsg-portfolio.com"


# ---------------------------------------------------------------------------
#  Endpoints
# ---------------------------------------------------------------------------

@router.get("/vapid-key")
def vapid_public_key(db: Session = Depends(get_db)):
    """Clave pública VAPID para el frontend (sin autenticación)."""
    pub = get_vapid_public_key(db)
    return {"public_key": pub or ""}


@router.post("/subscribe", status_code=status.HTTP_204_NO_CONTENT)
def subscribe(
    body: dict,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    Registra o actualiza la suscripción push del dispositivo actual.
    body: { endpoint, keys: { p256dh, auth } }
    """
    endpoint = body.get("endpoint", "")
    keys = body.get("keys", {})
    p256dh = keys.get("p256dh", "")
    auth   = keys.get("auth", "")
    if not endpoint or not p256dh or not auth:
        return

    existing = db.scalar(
        select(PushSubscription).where(PushSubscription.endpoint == endpoint)
    )
    if existing:
        existing.user_id = user.id
        existing.p256dh  = p256dh
        existing.auth    = auth
    else:
        db.add(PushSubscription(
            user_id=user.id, endpoint=endpoint, p256dh=p256dh, auth=auth,
        ))
    db.commit()


@router.delete("/subscribe", status_code=status.HTTP_204_NO_CONTENT)
def unsubscribe(
    body: dict,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Elimina la suscripción push del dispositivo actual."""
    endpoint = body.get("endpoint", "")
    sub = db.scalar(
        select(PushSubscription).where(
            PushSubscription.endpoint == endpoint,
            PushSubscription.user_id == user.id,
        )
    )
    if sub:
        db.delete(sub)
        db.commit()
