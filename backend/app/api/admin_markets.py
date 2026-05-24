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

import json
from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_admin
from app.models import AppConfig, MarketRow, Security, User
from app.schemas.market_admin import (
    AppNameUpdate, CatalogImportBody,
    MarketCreate, MarketOut, MarketReorderItem, MarketUpdate, SnapshotIntervalUpdate,
)

router = APIRouter(prefix="/admin", tags=["admin"])

_CONFIG_INTERVAL_KEY = "snapshot_interval_minutes"
_CONFIG_APP_NAME_KEY = "app_name"
_APP_NAME_DEFAULT    = "FJS Finanzas"


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


def _get_app_name(db: Session) -> str:
    row = db.get(AppConfig, _CONFIG_APP_NAME_KEY)
    return row.value if row else _APP_NAME_DEFAULT


# ---------------------------------------------------------------------------
#  Mercados
# ---------------------------------------------------------------------------

@router.get("/markets", response_model=list[MarketOut])
def list_markets(
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    return db.scalars(select(MarketRow).order_by(MarketRow.sort_order, MarketRow.code)).all()


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
        sort_order=body.sort_order,
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
    if body.sort_order is not None:
        market.sort_order = body.sort_order
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


@router.put("/markets/reorder", status_code=status.HTTP_204_NO_CONTENT)
def reorder_markets(
    body: list[MarketReorderItem],
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    """
    Actualiza el sort_order de varios mercados en una sola llamada.
    Recibe [{code, sort_order}, ...] y aplica el nuevo orden.
    Los códigos que no existan se ignoran silenciosamente.
    """
    for item in body:
        market = db.get(MarketRow, item.code)
        if market:
            market.sort_order = item.sort_order
    db.commit()


# ---------------------------------------------------------------------------
#  Exportación / importación del catálogo de mercados y valores
# ---------------------------------------------------------------------------

@router.get("/catalog/export")
def export_catalog(
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    """
    Exporta el catálogo completo de mercados y valores en JSON descargable.
    El fichero resultante puede importarse en otro servidor con POST /catalog/import.
    """
    markets = db.scalars(select(MarketRow).order_by(MarketRow.code)).all()
    securities = db.scalars(select(Security).order_by(Security.name)).all()

    payload = {
        "exported_at": date.today().isoformat(),
        "markets": [
            {
                "code": m.code,
                "name": m.name,
                "index_ticker": m.index_ticker,
                "currency": m.currency,
                "fiscal_window_days": m.fiscal_window_days,
            }
            for m in markets
        ],
        "securities": [
            {
                "name": s.name,
                "isin": s.isin,
                "yahoo_ticker": s.yahoo_ticker,
                "google_ticker": s.google_ticker,
                "market": s.market,
                "currency": s.currency,
            }
            for s in securities
        ],
    }

    json_bytes = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
    today = date.today().isoformat()
    return Response(
        content=json_bytes,
        media_type="application/json",
        headers={
            "Content-Disposition": f'attachment; filename="catalogo_valores_{today}.json"'
        },
    )


@router.post("/catalog/import")
def import_catalog(
    body: CatalogImportBody,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    """
    Importa un catálogo de mercados y valores desde JSON.

    Reglas de deduplicación:
    - Mercados: índice = code (PK). Si el código ya existe, se omite.
    - Valores  : índice = yahoo_ticker (UNIQUE global). Si el ticker ya
                 existe en cualquier mercado, se omite (no se mueve de mercado).

    Devuelve los contadores de importados / omitidos para dar feedback al admin.
    """
    markets_imported = 0
    markets_skipped = 0

    # — Paso 1: importar mercados (code = PK) —————————————————————————————
    for m in body.markets:
        code = m.code.strip().lower()
        if not code:
            markets_skipped += 1
            continue
        if db.get(MarketRow, code) is None:
            db.add(
                MarketRow(
                    code=code,
                    name=m.name.strip() or code,
                    index_ticker=m.index_ticker or None,
                    currency=(m.currency or "EUR").upper(),
                    fiscal_window_days=max(1, m.fiscal_window_days or 60),
                    created_at=datetime.now().isoformat(),
                )
            )
            markets_imported += 1
        else:
            markets_skipped += 1

    # flush para que los mercados recién importados sean visibles en el paso 2
    if markets_imported > 0:
        db.flush()

    # — Paso 2: importar valores (yahoo_ticker = UNIQUE global) ——————————
    existing_tickers: set[str] = set(
        db.scalars(select(Security.yahoo_ticker))
    )

    securities_imported = 0
    securities_skipped = 0
    securities_no_market = 0

    for s in body.securities:
        ticker = s.yahoo_ticker.strip().upper()
        if not ticker:
            securities_skipped += 1
            continue

        # Ya existe en la BD (en cualquier mercado)
        if ticker in existing_tickers:
            securities_skipped += 1
            continue

        # Moneda válida (solo EUR y USD soportadas por el motor de cálculo)
        currency = (s.currency or "EUR").upper()
        if currency not in ("EUR", "USD"):
            securities_skipped += 1
            continue

        # El mercado debe existir (en la BD original o recién importado)
        market_code = (s.market or "").strip().lower()
        if not market_code or db.get(MarketRow, market_code) is None:
            securities_no_market += 1
            continue

        db.add(
            Security(
                name=s.name.strip(),
                isin=s.isin or None,
                yahoo_ticker=ticker,
                google_ticker=s.google_ticker or None,
                market=market_code,
                currency=currency,
            )
        )
        existing_tickers.add(ticker)  # evitar duplicados dentro del mismo lote
        securities_imported += 1

    db.commit()

    return {
        "markets_imported":      markets_imported,
        "markets_skipped":       markets_skipped,
        "securities_imported":   securities_imported,
        "securities_skipped":    securities_skipped,
        "securities_no_market":  securities_no_market,
    }


# ---------------------------------------------------------------------------
#  Configuración global
# ---------------------------------------------------------------------------

@router.get("/config")
def get_config(
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    return {
        "snapshot_interval_minutes": _get_interval(db),
        "app_name": _get_app_name(db),
    }


@router.patch("/config/app-name")
def set_app_name(
    body: AppNameUpdate,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    row = db.get(AppConfig, _CONFIG_APP_NAME_KEY)
    if row is None:
        db.add(AppConfig(key=_CONFIG_APP_NAME_KEY, value=body.app_name))
    else:
        row.value = body.app_name
    db.commit()
    return {"app_name": body.app_name}


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
