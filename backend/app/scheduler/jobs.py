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

from app.models import EcbRate, PriceHistory, PriceSnapshot, Security
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

def update_snapshots(db: Session) -> None:
    securities = db.scalars(select(Security)).all()

    for sec in securities:
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
            updated_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
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
                "updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
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

def update_snapshots_live(db: Session) -> None:
    """Actualiza solo snapshots (sin histórico). Llamado cada N min durante el día."""
    log.info("Actualizacion live de snapshots")
    update_snapshots(db)
    log.info("Snapshots live completados")
