"""
api/markets.py
==============
Datos de mercado: historico de precios, snapshots y vistas combinadas.

GET /markets/list                   — lista de mercados (para pestañas dinámicas).
GET /markets/overview               — securities + snapshot + favorito (un call por pestaña).
GET /markets/index-quote            — cotización del índice de mercado.
GET /markets/index-history          — histórico del índice para el sparkline de cabecera.
GET /markets/{security_id}/history  — histórico de cierres de un valor.
GET /markets/{security_id}/snapshot — snapshot con indicadores.
POST /markets/{security_id}/refresh — fuerza actualización inmediata.
POST /markets/refresh-all           — fuerza actualización de todos (solo admin).
"""

from __future__ import annotations

import time
from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import outerjoin, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db, require_admin
from app.models import EcbRate, Favorite, MarketRow, PriceHistory, PriceSnapshot, Security, User
from app.schemas.market import (
    IndexQuote, PriceHistoryPoint, SecurityOverview, SnapshotOut,
)
from app.schemas.market_admin import MarketOut

router = APIRouter(prefix="/markets", tags=["markets"])
_INDEX_QUOTE_CACHE: dict[str, tuple[float, IndexQuote]] = {}
_INDEX_HIST_CACHE:  dict[str, tuple[float, list]]       = {}
_QUOTE_TTL = 900   # 15 min
_HIST_TTL  = 3600  # 1 hora


def _get_market_or_404(db: Session, code: str) -> MarketRow:
    m = db.get(MarketRow, code)
    if m is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Mercado desconocido")
    return m


# ---------------------------------------------------------------------------
#  Helper: carga securities + snapshots en una sola query (LEFT JOIN)
# ---------------------------------------------------------------------------

def _load_securities_with_snapshots(
    db: Session,
    user_id: int,
    market: str | None = None,
    favorites_only: bool = False,
) -> list[SecurityOverview]:
    """
    Une Security + PriceSnapshot + Favorite del usuario en un único SELECT.
    Evita el N+1 que supone llamar a db.get(PriceSnapshot) por cada Security.
    """
    j = outerjoin(Security, PriceSnapshot, Security.id == PriceSnapshot.security_id)
    query = (
        select(Security, PriceSnapshot)
        .select_from(j)
        .order_by(Security.name)
    )
    if market:
        query = query.where(Security.market == market)

    rows = db.execute(query).all()

    favs: dict[int, object] = {
        f.security_id: f.target_buy_price
        for f in db.scalars(
            select(Favorite).where(Favorite.user_id == user_id)
        ).all()
    }

    result = []
    for sec, snap in rows:
        is_fav = sec.id in favs
        if favorites_only and not is_fav:
            continue
        result.append(SecurityOverview(
            id=sec.id,
            name=sec.name,
            isin=sec.isin,
            yahoo_ticker=sec.yahoo_ticker,
            google_ticker=sec.google_ticker,
            market=sec.market,
            currency=sec.currency,
            last_price=snap.last_price if snap else None,
            daily_change_pct=snap.daily_change_pct if snap else None,
            min_1y=snap.min_1y if snap else None,
            min_2y=snap.min_2y if snap else None,
            min_5y=snap.min_5y if snap else None,
            max_1y=snap.max_1y if snap else None,
            last_dividend=snap.last_dividend if snap else None,
            is_favorite=is_fav,
            target_buy_price=favs.get(sec.id),
            updated_at=snap.updated_at if snap else None,
        ))
    return result


# ---------------------------------------------------------------------------
#  Lista de mercados (para que el frontend construya pestañas dinámicas)
# ---------------------------------------------------------------------------

@router.get("/list", response_model=list[MarketOut])
def list_markets(
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    return db.scalars(select(MarketRow).order_by(MarketRow.sort_order, MarketRow.code)).all()


# ---------------------------------------------------------------------------
#  Vista combinada (usada por cada pestaña del explorador de mercados)
# ---------------------------------------------------------------------------

@router.get("/overview", response_model=list[SecurityOverview])
def get_overview(
    market: str | None = Query(None),
    favorites_only: bool = Query(False),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    Devuelve la lista de valores con snapshot y estado de favorito en una sola llamada.
    - market=ibex35|continuo|nasdaq filtra por mercado.
    - favorites_only=true devuelve solo los favoritos del usuario (para la pestaña Favoritos).
    """
    return _load_securities_with_snapshots(db, user.id, market=market, favorites_only=favorites_only)


# ---------------------------------------------------------------------------
#  Cotización e histórico del índice de mercado
# ---------------------------------------------------------------------------

@router.get("/index-quote", response_model=IndexQuote | None)
def get_index_quote(
    market: str = Query(...),
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    market_row = _get_market_or_404(db, market)
    if not market_row.index_ticker:
        return None

    now = time.time()
    cached = _INDEX_QUOTE_CACHE.get(market)
    if cached and now - cached[0] < _QUOTE_TTL:
        return cached[1]

    try:
        from app.providers.yahoo import YahooProvider
        quote = YahooProvider().fetch_live_quote(market_row.index_ticker)
        data = IndexQuote(
            name=market_row.name,
            ticker=market_row.index_ticker,
            last_price=quote.last_price,
            daily_change_pct=quote.daily_change_pct,
        )
        _INDEX_QUOTE_CACHE[market] = (now, data)
        return data
    except Exception:
        return None


@router.get("/index-history")
def get_index_history(
    market: str = Query(...),
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    market_row = _get_market_or_404(db, market)
    if not market_row.index_ticker:
        return []

    now = time.time()
    cached = _INDEX_HIST_CACHE.get(market)
    if cached and now - cached[0] < _HIST_TTL:
        return cached[1]

    from app.providers.yahoo import YahooProvider
    try:
        bars = YahooProvider().fetch_history(
            market_row.index_ticker,
            date.today() - timedelta(days=365),
            date.today(),
        )
        data = [{"date": b.date.isoformat(), "close": float(b.close)} for b in bars]
        _INDEX_HIST_CACHE[market] = (now, data)
        return data
    except Exception:
        return []


# ---------------------------------------------------------------------------
#  Top movers (mayores subidas/bajadas del día por mercado)
# ---------------------------------------------------------------------------

@router.get("/top-movers", response_model=list[SecurityOverview])
def get_top_movers(
    market: str = Query(...),
    n: int = Query(5, ge=1, le=20),
    direction: str = Query("up"),  # "up" | "down"
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    Devuelve los N valores con mayor subida (direction=up) o bajada (direction=down)
    del mercado indicado, según daily_change_pct del snapshot.
    """
    rows = _load_securities_with_snapshots(db, user.id, market=market)
    # Excluir los que no tienen variación diaria
    rows = [r for r in rows if r.daily_change_pct is not None]
    # Filtro estricto: solo subidas reales (>0) o bajadas reales (<0)
    if direction == "up":
        rows = [r for r in rows if float(r.daily_change_pct) > 0]
    else:
        rows = [r for r in rows if float(r.daily_change_pct) < 0]
    reverse = direction != "down"
    rows.sort(key=lambda r: float(r.daily_change_pct), reverse=reverse)
    return rows[:n]


# ---------------------------------------------------------------------------
#  Histórico y snapshot de un valor individual
# ---------------------------------------------------------------------------

@router.get("/{security_id}/history", response_model=list[PriceHistoryPoint])
def get_history(
    security_id: int,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    _require_security(db, security_id)
    rows = db.scalars(
        select(PriceHistory)
        .where(PriceHistory.security_id == security_id)
        .order_by(PriceHistory.date)
    ).all()
    return rows


@router.get("/{security_id}/snapshot", response_model=SnapshotOut)
def get_snapshot(
    security_id: int,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    _require_security(db, security_id)
    snap = db.get(PriceSnapshot, security_id)
    if snap is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Snapshot no disponible aún; el scheduler lo actualiza cada noche",
        )
    return snap


@router.post("/refresh-all", status_code=status.HTTP_202_ACCEPTED)
def refresh_all(
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    """Fuerza actualización de histórico y snapshot para todos los valores del catálogo (solo admin)."""
    from app.scheduler.jobs import _update_history_for_security, _update_snapshot_for_security
    secs = db.scalars(select(Security)).all()
    for sec in secs:
        try:
            _update_history_for_security(db, sec, date.today())
            _update_snapshot_for_security(db, sec)
        except Exception:
            pass
    return {"detail": f"Actualizados {len(secs)} valores"}


@router.post("/{security_id}/refresh", status_code=status.HTTP_202_ACCEPTED)
def refresh_security(
    security_id: int,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    sec = _require_security(db, security_id)
    from app.scheduler.jobs import _update_history_for_security, _update_snapshot_for_security
    _update_history_for_security(db, sec, date.today())
    _update_snapshot_for_security(db, sec)
    return {"detail": f"Actualizado {sec.yahoo_ticker}"}


def _require_security(db: Session, security_id: int) -> Security:
    sec = db.get(Security, security_id)
    if sec is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Valor no encontrado")
    return sec


# ---------------------------------------------------------------------------
#  Tipo de cambio EUR/USD para una fecha concreta
# ---------------------------------------------------------------------------

@router.get("/exchange-rate")
def get_exchange_rate(
    date_str: str = Query(..., alias="date", pattern=r"^\d{4}-\d{2}-\d{2}$"),
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    """
    Devuelve el tipo de cambio EUR/USD para la fecha indicada.

    Estrategia:
      1. Busca en ecb_rates el registro más reciente con fecha <= date.
      2. Si no hay dato en BD, intenta obtenerlo de Yahoo Finance (EURUSD=X).
      3. Si tampoco hay dato en Yahoo, devuelve rate=null.

    Respuesta: {rate, date, source}  donde source es "ecb"|"yahoo"|"not_found".
    """
    # 1. Buscar en la caché BCE
    row = db.scalar(
        select(EcbRate)
        .where(EcbRate.date <= date_str)
        .order_by(EcbRate.date.desc())
        .limit(1)
    )
    if row is not None:
        return {"rate": float(row.rate), "date": row.date, "source": "ecb"}

    # 2. Fallback: Yahoo Finance EURUSD=X
    try:
        from datetime import date as date_type, timedelta
        from decimal import Decimal
        import yfinance as yf
        import math

        d = date_type.fromisoformat(date_str)
        df = yf.Ticker("EURUSD=X").history(
            start=d.isoformat(),
            end=(d + timedelta(days=5)).isoformat(),
            auto_adjust=False,
            timeout=5,
        )
        df = df.dropna(subset=["Close"])
        if not df.empty:
            rate_val = float(df["Close"].iloc[0])
            yahoo_date = df.index[0].date().isoformat()
            if not math.isnan(rate_val) and rate_val > 0:
                return {"rate": round(rate_val, 6), "date": yahoo_date, "source": "yahoo"}
    except Exception:
        pass

    return {"rate": None, "source": "not_found"}
