"""
scheduler/jobs.py
=================
Trabajos nocturnos gestionados por APScheduler.

Arquitectura
------------
Cada job recibe una Session de SQLAlchemy y hace commit al final si todo
fue bien. Los errores de red o de la API externa se loggean y no abortan
el job: un fallo en un ticker no debe impedir actualizar los demas.

Jobs definidos
--------------
- update_price_history : descarga cierres historicos nuevos desde la
  fecha del ultimo dato hasta hoy para cada Security.
- update_snapshots     : recalcula min/max de rango e inserta el precio
  en vivo en price_snapshots.
- update_ecb_rates     : descarga los tipos EUR/USD del BCE para los
  dias que falten en ecb_rates.

Estos tres jobs se encadenan en ese orden (history → snapshots → rates)
porque los snapshots dependen de que el historico este actualizado.

Registro en APScheduler (se hace en main.py):
    scheduler.add_job(daily_update, "cron", hour=6, minute=30)
"""

from __future__ import annotations

import logging
import time
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select, func
from sqlalchemy.orm import Session
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from app.models import AppConfig, EcbRate, PriceHistory, PriceSnapshot, Security
from app.models.market import MarketRow
from app.providers.yahoo import YahooProvider
from app.providers.ecb import EcbProvider
from app.services.indicators import compute_ranges

log = logging.getLogger(__name__)

_yahoo = YahooProvider()
_ecb = EcbProvider()


# ---------------------------------------------------------------------------
#  Job principal: encadena los tres pasos
# ---------------------------------------------------------------------------

def daily_update(db: Session) -> None:
    """Punto de entrada del job nocturno."""
    log.info("Iniciando actualizacion diaria de mercado")
    update_price_history(db)
    update_snapshots(db)
    update_ecb_rates(db)
    log.info("Actualizacion diaria completada")


# ---------------------------------------------------------------------------
#  1. Historico de cotizaciones
# ---------------------------------------------------------------------------

def update_price_history(db: Session) -> None:
    securities = db.scalars(select(Security)).all()
    today = date.today()

    for sec in securities:
        try:
            _update_history_for_security(db, sec, today)
        except Exception:
            log.exception("Error actualizando historico de %s", sec.yahoo_ticker)
            db.rollback()
        # Pausa entre peticiones para evitar rate-limiting de yfinance
        # (especialmente relevante en el primer arranque con muchos valores nuevos).
        time.sleep(0.5)


def _update_history_for_security(
    db: Session, sec: Security, today: date
) -> None:
    # Ultima fecha almacenada para este valor
    last_date_str = db.scalar(
        select(func.max(PriceHistory.date)).where(
            PriceHistory.security_id == sec.id
        )
    )
    if last_date_str:
        last_date = date.fromisoformat(last_date_str)
        # Retrocedemos 6 días para refrescar la ventana reciente.
        # Motivo: si un día anterior se almacenó con auto_adjust=True
        # (yfinance ajustaba retroactivamente por dividendo) y ahora usamos
        # auto_adjust=False, el valor incorrecto quedaría congelado con
        # on_conflict_do_nothing. Al usar on_conflict_do_update para los
        # últimos 7 días sobreescribimos cualquier precio incorrecto.
        from_date = last_date - timedelta(days=6)
    else:
        # Sin historico: descargar 5 anos
        from_date = today - timedelta(days=5 * 365)

    if from_date > today:
        return  # ya al dia

    bars = _yahoo.fetch_history(sec.yahoo_ticker, from_date, today)
    if not bars:
        return

    for bar in bars:
        stmt = (
            sqlite_insert(PriceHistory)
            .values(
                security_id=sec.id,
                date=bar.date.isoformat(),
                close=bar.close,
                volume=bar.volume,
            )
            .on_conflict_do_update(
                index_elements=["security_id", "date"],
                set_={
                    "close": bar.close,
                    "volume": bar.volume,
                },
            )
        )
        db.execute(stmt)

    db.commit()
    log.debug(
        "Historico %s: %d barras desde %s",
        sec.yahoo_ticker, len(bars), from_date,
    )


# ---------------------------------------------------------------------------
#  2. Snapshots (precio en vivo + rangos)
# ---------------------------------------------------------------------------

def _fund_market_codes(db: Session) -> set[str]:
    """Códigos de mercados marcados como mercado de fondos."""
    return set(
        db.scalars(select(MarketRow.code).where(MarketRow.is_fund_market.is_(True)))
    )


def update_snapshots(db: Session, include_funds: bool = True) -> None:
    """
    Actualiza los snapshots de precio en vivo.

    Si include_funds es False, omite los valores de mercados de fondos: su NAV
    es diario y no cambia intradía, así que no tiene sentido consultarlo cada
    pocos minutos. El job nocturno siempre los incluye (include_funds=True).
    """
    securities = db.scalars(select(Security)).all()
    fund_codes = _fund_market_codes(db) if not include_funds else set()

    for sec in securities:
        if not include_funds and sec.market in fund_codes:
            continue
        try:
            _update_snapshot_for_security(db, sec)
        except Exception:
            log.exception("Error actualizando snapshot de %s", sec.yahoo_ticker)
            db.rollback()


def _update_snapshot_for_security(db: Session, sec: Security) -> None:
    quote = _yahoo.fetch_live_quote(sec.yahoo_ticker)
    # Si no hay precio (mercado cerrado, festivo), conservar el snapshot anterior
    if quote.last_price is None:
        return

    # Rangos calculados desde el historico almacenado en BD
    rows = db.execute(
        select(PriceHistory.date, PriceHistory.close)
        .where(PriceHistory.security_id == sec.id)
        .order_by(PriceHistory.date)
    ).all()
    closes = [(date.fromisoformat(r.date), r.close) for r in rows]
    stats = compute_ranges(closes)

    # Si Yahoo proporcionó el timestamp del último trade, lo preferimos sobre
    # el datetime actual: refleja cuándo se actualizaron los precios EN ORIGEN.
    # Esto evita que se interprete como "actualizado ahora" cuando en realidad
    # los precios pueden ser de horas atrás (cierres EOD, mercado cerrado, etc.).
    updated_at_value = (
        quote.quote_time
        if quote.quote_time
        else datetime.now(timezone.utc).isoformat(timespec="seconds")
    )

    stmt = (
        sqlite_insert(PriceSnapshot)
        .values(
            security_id=sec.id,
            last_price=quote.last_price,
            prev_close=quote.prev_close,
            daily_change_pct=quote.daily_change_pct,
            min_1y=stats.min_1y,
            max_1y=stats.max_1y,
            min_2y=stats.min_2y,
            min_5y=stats.min_5y,
            last_dividend=quote.last_dividend,
            updated_at=updated_at_value,
        )
        .on_conflict_do_update(
            index_elements=["security_id"],
            set_={
                "last_price": quote.last_price,
                "prev_close": quote.prev_close,
                "daily_change_pct": quote.daily_change_pct,
                "min_1y": stats.min_1y,
                "max_1y": stats.max_1y,
                "min_2y": stats.min_2y,
                "min_5y": stats.min_5y,
                "last_dividend": quote.last_dividend,
                "updated_at": updated_at_value,
            },
        )
    )
    db.execute(stmt)
    db.commit()
    log.debug("Snapshot actualizado: %s → %s", sec.yahoo_ticker, quote.last_price)


# ---------------------------------------------------------------------------
#  3. Tipos de cambio BCE
# ---------------------------------------------------------------------------

def update_ecb_rates(db: Session) -> None:
    today = date.today()

    last_date_str = db.scalar(select(func.max(EcbRate.date)))
    if last_date_str:
        from_date = date.fromisoformat(last_date_str) + timedelta(days=1)
    else:
        from_date = today - timedelta(days=5 * 365)

    if from_date > today:
        return

    try:
        rates = _ecb.fetch_rates(from_date, today)
    except Exception:
        log.exception("Error descargando tipos BCE")
        return

    for date_str, rate in rates.items():
        stmt = (
            sqlite_insert(EcbRate)
            .values(date=date_str, rate=rate)
            .on_conflict_do_nothing()
        )
        db.execute(stmt)

    db.commit()
    log.info("Tipos BCE: %d nuevas entradas desde %s", len(rates), from_date)


# ---------------------------------------------------------------------------
#  4. Snapshots en vivo (job periódico cada N minutos, configurable por admin)
# ---------------------------------------------------------------------------

_FUNDS_REFRESH_KEY = "funds_live_refresh_at"


def _should_refresh_funds_live(db: Session, now: datetime) -> bool:
    """
    Los fondos solo se refrescan en el job en vivo una vez por hora de reloj
    (su NAV es diario). Devuelve True si en la hora actual aún no se han
    refrescado, comparando con el timestamp guardado en app_config.
    """
    row = db.get(AppConfig, _FUNDS_REFRESH_KEY)
    if row is None or not row.value:
        return True
    try:
        last = datetime.fromisoformat(row.value)
    except ValueError:
        return True
    # Refrescar si cambia la hora de reloj (o el día)
    return (last.date(), last.hour) != (now.date(), now.hour)


def _mark_funds_refreshed(db: Session, now: datetime) -> None:
    """Registra en app_config la marca de tiempo del último refresco de fondos."""
    row = db.get(AppConfig, _FUNDS_REFRESH_KEY)
    if row is None:
        db.add(AppConfig(key=_FUNDS_REFRESH_KEY, value=now.isoformat(timespec="seconds")))
    else:
        row.value = now.isoformat(timespec="seconds")
    db.commit()


def update_snapshots_live(db: Session) -> None:
    """
    Actualiza solo snapshots (sin histórico). Llamado cada N min durante el día.

    Los fondos (mercados is_fund_market) se actualizan como máximo una vez por
    hora de reloj: su valor liquidativo es diario y consultarlo cada pocos
    minutos solo añade carga inútil sobre Yahoo. El resto de valores (acciones,
    ETFs, cripto) se actualizan en cada ejecución.
    """
    now = datetime.now()
    include_funds = _should_refresh_funds_live(db, now)
    log.info("Actualizacion live de snapshots (fondos=%s)", include_funds)
    update_snapshots(db, include_funds=include_funds)
    if include_funds:
        _mark_funds_refreshed(db, now)
    log.info("Snapshots live completados")
