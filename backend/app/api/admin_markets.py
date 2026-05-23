"""
api/admin_markets.py
====================
Gestión del catálogo de mercados. Solo administradores.

GET    /admin/markets            — lista todos los mercados.
POST   /admin/markets            — crea un mercado nuevo.
PATCH  /admin/markets/{code}     — actualiza un mercado existente.
DELETE /admin/markets/{code}     — elimina un mercado (solo si no tiene valores).

GET    /admin/config             — devuelve la configuración global (incluye intervalo).
PATCH  /admin/config/snapshot-interval — cambia el intervalo de actualización de snapshots.
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_admin
from app.models import AppConfig, MarketRow, Security, User
from app.schemas.market_admin import (
    MarketCreate, MarketOut, MarketUpdate, SnapshotIntervalUpdate,
)

router = APIRouter(prefix="/admin", tags=["admin"])

_CONFIG_INTERVAL_KEY = "snapshot_interval_minutes"


# ---------------------------------------------------------------------------
#  Helpers
# ---------------------------------------------------------------------------

def _require_market(db: Session, code: str) -> MarketRow:
    m = db.get(MarketRow, code)
    if m is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail=f"Mercado '{code}' no encontrado")
    return m


def _get_interval(db: Session) -> int:
    row = db.get(AppConfig, _CONFIG_INTERVAL_KEY)
    return int(row.value) if row else 5


# ---------------------------------------------------------------------------
#  Mercados
# ---------------------------------------------------------------------------

@router.get("/markets", response_model=list[MarketOut])
def list_markets(
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    return db.scalars(select(MarketRow).order_by(MarketRow.code)).all()


@router.post("/markets", response_model=MarketOut, status_code=status.HTTP_201_CREATED)
def create_market(
    body: MarketCreate,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    if db.get(MarketRow, body.code):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                            detail=f"El código de mercado '{body.code}' ya existe")
    market = MarketRow(
        code=body.code,
        name=body.name,
        index_ticker=body.index_ticker,
        currency=body.currency,
        fiscal_window_days=body.fiscal_window_days,
        created_at=datetime.now().isoformat(),
    )
    db.add(market)
    db.commit()
    db.refresh(market)
    return market


@router.patch("/markets/{code}", response_model=MarketOut)
def update_market(
    code: str,
    body: MarketUpdate,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    market = _require_market(db, code)
    if body.name is not None:
        market.name = body.name
    if body.index_ticker is not None:
        market.index_ticker = body.index_ticker
    if body.currency is not None:
        market.currency = body.currency
    if body.fiscal_window_days is not None:
        market.fiscal_window_days = body.fiscal_window_days
    db.commit()
    db.refresh(market)
    return market


@router.delete("/markets/{code}", status_code=status.HTTP_204_NO_CONTENT)
def delete_market(
    code: str,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    market = _require_market(db, code)
    # Impedir borrado si hay valores asignados a este mercado
    count = db.scalar(
        select(func.count(Security.id)).where(Security.market == code)
    )
    if count > 0:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"El mercado '{code}' tiene valores asignados; reasígnalos antes de eliminarlo",
        )
    db.delete(market)
    db.commit()


# ---------------------------------------------------------------------------
#  Configuración global
# ---------------------------------------------------------------------------

@router.get("/config")
def get_config(
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    interval = _get_interval(db)
    return {"snapshot_interval_minutes": interval}


@router.patch("/config/snapshot-interval")
def set_snapshot_interval(
    body: SnapshotIntervalUpdate,
    request: Request,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    row = db.get(AppConfig, _CONFIG_INTERVAL_KEY)
    if row is None:
        db.add(AppConfig(key=_CONFIG_INTERVAL_KEY, value=str(body.minutes)))
    else:
        row.value = str(body.minutes)
    db.commit()

    # Reprogramar el job en APScheduler sin reiniciar el servidor
    scheduler = getattr(request.app.state, "scheduler", None)
    if scheduler is not None:
        try:
            scheduler.reschedule_job(
                "snapshot_live",
                trigger="interval",
                minutes=body.minutes,
            )
        except Exception:
            pass  # El job no existe aún o el scheduler está parado; no es crítico

    return {"snapshot_interval_minutes": body.minutes}
