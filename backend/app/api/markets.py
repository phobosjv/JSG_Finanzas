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

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from sqlalchemy import func, outerjoin, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db, require_admin
from app.models import EcbRate, Favorite, MarketRow, Position, PriceHistory, PriceSnapshot, Security, User
from app.schemas.market import (
    IndexQuote, PriceHistoryPoint, SecurityOverview, SnapshotOut,
)
from app.schemas.market_admin import MarketOut

router = APIRouter(prefix="/markets", tags=["markets"])
_INDEX_QUOTE_CACHE: dict[str, tuple[float, IndexQuote]] = {}
_INDEX_HIST_CACHE:  dict[str, tuple[float, list]]       = {}
_QUOTE_TTL = 900   # 15 min
_HIST_TTL  = 3600  # 1 hora

# Anti-rebote del refresco bajo demanda (en memoria; un solo worker uvicorn).
_LAST_LAZY_REFRESH:   dict[int, float] = {}   # security_id -> monotonic
_LAST_MOVERS_REFRESH: dict[str, float] = {}   # market_code -> monotonic
_LAZY_TTL          = 3600   # no re-pedir un valor suelto en <1 h
_MOVERS_TTL        = 900    # refrescar un mercado de movers como mucho cada 15 min
_MOVERS_MAX_SECS   = 250    # no escanear mercados gigantes bajo demanda


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

    market_types: dict[str, str] = {
        m.code: m.market_type
        for m in db.scalars(select(MarketRow)).all()
    }

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
            market_type=market_types.get(sec.market, "stock"),
            is_fund_market=market_types.get(sec.market) == "fund",
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
    background: BackgroundTasks,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    """
    Lanza en SEGUNDO PLANO un barrido completo (histórico + snapshots) de todo
    el catálogo (solo admin). No bloquea la petición ni hace ráfaga síncrona:
    el barrido va paced y corta ante rate-limit de Yahoo.
    """
    from app.scheduler.jobs import refresh_all_full
    n = db.scalar(select(func.count()).select_from(Security)) or 0
    background.add_task(refresh_all_full)
    return {"detail": f"Barrido de {n} valores iniciado en segundo plano"}


@router.post("/{market}/refresh-movers", status_code=status.HTTP_202_ACCEPTED)
def refresh_movers(
    market: str,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    """
    Refresco bajo demanda de los snapshots de un mercado (para Top movers), al
    abrir el Dashboard. Throttled (1×/15 min por mercado) y con tope de tamaño
    para no escanear catálogos enormes. Se ejecuta en segundo plano.
    """
    _get_market_or_404(db, market)
    now = time.monotonic()
    last = _LAST_MOVERS_REFRESH.get(market)
    if last is not None and now - last < _MOVERS_TTL:
        return {"scheduled": False, "reason": "throttled"}

    n = db.scalar(
        select(func.count()).select_from(Security).where(Security.market == market)
    ) or 0
    if n == 0:
        return {"scheduled": False, "reason": "empty"}
    if n > _MOVERS_MAX_SECS:
        return {"scheduled": False, "reason": "too_large"}

    _LAST_MOVERS_REFRESH[market] = now  # marcar antes para evitar duplicados
    from app.scheduler.jobs import refresh_market_snapshots
    background.add_task(refresh_market_snapshots, market)
    return {"scheduled": True, "count": n}


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


@router.post("/{security_id}/refresh-if-stale", status_code=status.HTTP_200_OK)
def refresh_if_stale(
    security_id: int,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    """
    Refresco PEREZOSO al examinar un valor: si no está en el conjunto activo
    (nadie lo posee ni lo sigue) y no se ha pedido en la última hora, refresca
    su snapshot en ese momento. No lo mete en la programación de cada N min.

    Si el valor es activo o se refrescó hace poco, no hace nada (lo cubren el
    job en vivo o el anti-rebote). Devuelve {refreshed: bool}.
    """
    sec = _require_security(db, security_id)

    # ¿Está en el conjunto activo? Entonces ya lo cubre el job en vivo.
    in_use = db.scalar(
        select(Position.id).where(Position.security_id == security_id).limit(1)
    ) or db.scalar(
        select(Favorite.security_id).where(Favorite.security_id == security_id).limit(1)
    )
    if in_use:
        return {"refreshed": False, "reason": "active"}

    now = time.monotonic()
    last = _LAST_LAZY_REFRESH.get(security_id)
    if last is not None and now - last < _LAZY_TTL:
        return {"refreshed": False, "reason": "recent"}

    _LAST_LAZY_REFRESH[security_id] = now
    from app.scheduler.jobs import _update_snapshot_for_security
    try:
        _update_snapshot_for_security(db, sec, with_dividends=False)
    except Exception:
        return {"refreshed": False, "reason": "error"}
    return {"refreshed": True}


def _require_security(db: Session, security_id: int) -> Security:
    sec = db.get(Security, security_id)
    if sec is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Valor no encontrado")
    return sec


# ---------------------------------------------------------------------------
#  Tipo de cambio EUR/{currency} para una fecha concreta
# ---------------------------------------------------------------------------

@router.get("/exchange-rate")
def get_exchange_rate(
    date_str: str = Query(..., alias="date", pattern=r"^\d{4}-\d{2}-\d{2}$"),
    currency: str = Query("USD", min_length=3, max_length=3),
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    """
    Devuelve el tipo de cambio EUR/{currency} para la fecha indicada.

    Estrategia:
      1. Para USD: busca en ecb_rates (caché BCE). Para otras divisas se salta este paso.
      2. Si no hay dato en caché, intenta Yahoo Finance (EUR{currency}=X).
      3. Si tampoco hay dato en Yahoo, devuelve rate=null.

    Respuesta: {rate, date, source}  donde source es "ecb"|"yahoo"|"not_found".
    """
    currency = currency.strip().upper()

    # EUR consigo misma: tipo 1 (no tiene sentido consultar EUREUR=X).
    if currency == "EUR":
        return {"rate": 1.0, "date": date_str, "source": "eur"}

    # 1. Caché BCE — multi-divisa (USD, GBP, JPY, CHF…)
    if currency != "EUR":
        row = db.scalar(
            select(EcbRate)
            .where(EcbRate.currency == currency, EcbRate.date <= date_str)
            .order_by(EcbRate.date.desc())
            .limit(1)
        )
        if row is not None:
            return {"rate": float(row.rate), "date": row.date, "source": "ecb"}

    # 2. Fallback: Yahoo Finance EUR{currency}=X
    try:
        from datetime import date as date_type, timedelta
        import yfinance as yf
        import math

        d = date_type.fromisoformat(date_str)
        df = yf.Ticker(f"EUR{currency}=X").history(
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
