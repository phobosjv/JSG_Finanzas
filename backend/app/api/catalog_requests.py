"""
api/catalog_requests.py
========================
Endpoints para usuarios normales:
  - Validar un ticker en Yahoo Finance (preview antes de solicitar).
  - Crear una solicitud de agregación de producto.
  - Enviar un mensaje libre al administrador.

GET  /api/catalog/validate-ticker?ticker=XXX  — preview sin persistencia.
POST /api/catalog/requests                     — crea la solicitud (201).
POST /api/catalog/messages                     — mensaje libre al admin (201).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.models import Security, User
from app.models.catalog_requests import (
    CatalogMessageRow,
    SecurityRequestRow,
    UserNotificationRow,
)
from app.schemas.catalog_requests import (
    AdminMessageReply,
    CatalogMessageCreate,
    CatalogMessageOut,
    SecurityRequestCreate,
    SecurityRequestOut,
)

log = logging.getLogger(__name__)

router = APIRouter(prefix="/catalog", tags=["catalog"])


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


# ---------------------------------------------------------------------------
#  Validación de ticker (Yahoo Finance)
# ---------------------------------------------------------------------------

@router.get("/validate-ticker")
def validate_ticker(
    ticker: str,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    """Devuelve una vista previa del ticker en Yahoo Finance.

    Busca primero con yf.Search (coincidencia exacta de símbolo); si no
    encuentra, intenta yf.Ticker.history para confirmar que el ticker
    existe y obtener el último precio.

    Respuesta: {ticker, name, currency, exchange, last_price, in_catalog}
    """
    ticker = ticker.strip().upper()
    if not ticker:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="El ticker no puede estar vacío",
        )

    # ¿Ya está en el catálogo?
    existing = db.scalar(
        select(Security).where(Security.yahoo_ticker == ticker)
    )
    in_catalog = existing is not None

    import yfinance as yf

    name: str | None = None
    currency: str | None = None
    exchange: str | None = None
    last_price: float | None = None

    # 1ª pasada: yf.Search (rápida, sin descargar histórico)
    try:
        search = yf.Search(ticker, max_results=10, enable_fuzzy_query=False)
        quotes = search.quotes or []
        for q in quotes:
            if (q.get("symbol") or "").upper() == ticker:
                name = q.get("shortname") or q.get("longname")
                currency = (q.get("currency") or "").upper() or None
                exchange = q.get("exchDisp") or q.get("exchange")
                break
    except Exception:
        pass

    # 2ª pasada: history para obtener último precio (y confirmar existencia)
    try:
        t = yf.Ticker(ticker)
        hist = t.history(period="5d", auto_adjust=False)
        if not hist.empty:
            last_price = float(round(hist["Close"].iloc[-1], 6))
            if currency is None:
                try:
                    currency = (getattr(t.fast_info, "currency", None) or "").upper() or None
                except Exception:
                    pass
        elif not in_catalog:
            # El ticker no existe en Yahoo y no está en catálogo → error
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No se encontró el ticker '{ticker}' en Yahoo Finance",
            )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Yahoo Finance no disponible: {exc}",
        )

    if last_price is None and not in_catalog:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No se encontró el ticker '{ticker}' en Yahoo Finance",
        )

    # Si no obtuvimos nombre por Search, usar el ticker como fallback
    if name is None:
        try:
            info = yf.Ticker(ticker).info
            name = info.get("longName") or info.get("shortName") or ticker
        except Exception:
            name = ticker

    return {
        "ticker": ticker,
        "name": name,
        "currency": currency,
        "exchange": exchange,
        "last_price": last_price,
        "in_catalog": in_catalog,
    }


# ---------------------------------------------------------------------------
#  Crear solicitud de usuario
# ---------------------------------------------------------------------------

def _make_request_out(req: SecurityRequestRow, username: str | None = None) -> SecurityRequestOut:
    return SecurityRequestOut(
        id=req.id,
        user_id=req.user_id,
        username=username,
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


@router.post("/requests", response_model=SecurityRequestOut, status_code=status.HTTP_201_CREATED)
def create_request(
    body: SecurityRequestCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Crea una solicitud de agregación de producto y notifica al usuario."""
    # Verificar que el mercado existe
    from app.models import MarketRow
    if db.get(MarketRow, body.market_id) is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"El mercado '{body.market_id}' no existe",
        )

    req = SecurityRequestRow(
        user_id=user.id,
        ticker=body.ticker,
        isin=body.isin,
        name=body.name,
        market_id=body.market_id,
        currency=body.currency,
        status="pending",
    )
    db.add(req)
    db.flush()  # obtener req.id antes del commit

    # Notificación in-app al usuario: solicitud pendiente de revisión
    notif = UserNotificationRow(
        user_id=user.id,
        type="request_pending",
        title=f"Solicitud pendiente: {body.ticker}",
        body=(
            f"Tu solicitud para agregar '{body.name}' ({body.ticker}) "
            "está pendiente de revisión por el administrador."
        ),
        related_id=req.id,
        related_type="security_request",
        is_read=False,
    )
    db.add(notif)
    db.commit()
    db.refresh(req)

    return _make_request_out(req, username=user.username)


# ---------------------------------------------------------------------------
#  Mensaje libre al administrador
# ---------------------------------------------------------------------------

@router.post("/messages", response_model=CatalogMessageOut, status_code=status.HTTP_201_CREATED)
def create_message(
    body: CatalogMessageCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Envía un mensaje libre al administrador."""
    msg = CatalogMessageRow(
        user_id=user.id,
        subject=body.subject,
        message=body.message,
        security_request_id=body.security_request_id,
        is_resolved=False,
    )
    db.add(msg)
    db.commit()
    db.refresh(msg)

    return CatalogMessageOut(
        id=msg.id,
        user_id=msg.user_id,
        username=user.username,
        subject=msg.subject,
        message=msg.message,
        security_request_id=msg.security_request_id,
        is_resolved=msg.is_resolved,
        admin_reply=msg.admin_reply,
        admin_reply_at=msg.admin_reply_at,
        created_at=msg.created_at,
    )
