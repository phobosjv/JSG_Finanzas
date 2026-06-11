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
from decimal import Decimal

from sqlalchemy import select, func
from sqlalchemy.orm import Session
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from app.models import (
    AppConfig, EcbRate, Favorite, Position, PriceHistory, PriceSnapshot,
    PushSubscription, RecurringPlanRow, Security, TransactionRow,
    User, UserStatusLog, UserNotificationRow,
)
from app.models.market import MarketRow
from app.providers.yahoo import YahooProvider
from app.providers.ecb import EcbProvider
from app.services.indicators import compute_ranges
from app.services.recurring import nth_contribution_date

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
    execute_due_recurring_plans(db)
    check_expired_users(db)
    log.info("Actualizacion diaria completada")


# ---------------------------------------------------------------------------
#  Detección y notificación de usuarios caducados
# ---------------------------------------------------------------------------

def check_expired_users(db: Session) -> int:
    """Detecta usuarios que han caducado (expires_at <= ahora, is_enabled=True).

    Para cada usuario caducado:
      - Lo deshabilita.
      - Registra el evento en UserStatusLog.
      - Crea notificaciones in-app para todos los admins activos.
      - Envía copia por email a los admins con email configurado.

    Devuelve el número de usuarios procesados.
    El job nocturno cubre el caso de usuarios que caducan sin haber intentado
    hacer login (el login ya gestiona el primer acceso tras la caducidad).
    """
    from app.services.email_notifications import get_app_name, notify_admins, notify_admins_inapp

    now = datetime.now(timezone.utc).replace(tzinfo=None)

    expired = db.scalars(
        select(User).where(
            User.expires_at.is_not(None),
            User.expires_at <= now,
            User.is_enabled == True,
            User.is_admin == False,
        )
    ).all()

    if not expired:
        return 0

    for user in expired:
        user.is_enabled = False
        db.add(UserStatusLog(
            user_id=user.id,
            actor_id=None,
            status="expired",
            annotation="Cuenta caducada automáticamente (job nocturno)",
            created_at=now,
        ))

    db.flush()

    app_label = get_app_name(db)
    for user in expired:
        exp_str = user.expires_at.strftime("%d/%m/%Y") if user.expires_at else "—"
        title = f"Cuenta caducada: {user.username}"
        body_text = (
            f"La cuenta del usuario '{user.username}' ha caducado "
            f"(fecha límite: {exp_str}). "
            f"Puedes renovar el acceso desde el panel de administración."
        )
        try:
            notify_admins_inapp(db, type_="user_expired", title=title, body=body_text)
            notify_admins(
                db,
                subject=f"[{app_label}] Cuenta caducada: {user.username}",
                body_html=(
                    f"<p>La cuenta del usuario <strong>{user.username}</strong> "
                    f"ha caducado el {exp_str}.</p>"
                    f"<p>Puedes renovar el acceso desde el "
                    f"panel de administración → Usuarios.</p>"
                ),
            )
        except Exception:
            log.exception("Error notificando caducidad de %s", user.username)

    db.commit()
    log.info("check_expired_users: %d usuario(s) caducado(s) procesado(s)", len(expired))
    return len(expired)


# ---------------------------------------------------------------------------
#  Aportaciones periódicas (DCA): ejecutar planes vencidos
# ---------------------------------------------------------------------------

def execute_due_recurring_plans(db: Session, today: date | None = None) -> int:
    """
    Crea las compras de los planes de aportación periódica cuyas fechas ya han
    llegado (<= hoy). Para cada aportación pendiente usa el precio del día (o el
    del día hábil anterior) y el tipo de cambio de esa fecha.

    Recupera de caídas (catch-up): si el scheduler no corrió en varios días,
    ejecuta todas las aportaciones vencidas de una vez. Un hueco permanente en
    el pasado (sin precio anterior) se salta para no bloquear el plan; una fecha
    de HOY aún sin precio se deja pendiente para la siguiente ejecución.

    Devuelve el número de compras creadas. Borra los planes ya completados.
    """
    today = today or date.today()
    plans = db.scalars(select(RecurringPlanRow)).all()
    created = 0

    for plan in plans:
        start = date.fromisoformat(plan.start_date)
        pos = db.get(Position, plan.position_id)
        if pos is None:
            db.delete(plan)
            continue
        sec = db.get(Security, pos.security_id)

        while plan.done_count < plan.total_count:
            nd = nth_contribution_date(start, plan.frequency, plan.done_count)
            if nd > today:
                break  # la próxima aportación aún no ha llegado
            nd_str = nd.isoformat()

            price_row = db.scalar(
                select(PriceHistory)
                .where(PriceHistory.security_id == sec.id, PriceHistory.date <= nd_str)
                .order_by(PriceHistory.date.desc())
            )
            if price_row is None or price_row.close <= Decimal("0"):
                if nd < today:
                    plan.done_count += 1  # hueco pasado sin precio: saltar
                    continue
                break  # hoy sin precio todavía: reintentar en la próxima pasada

            if sec.currency == "EUR":
                rate = Decimal("1")
            else:
                rate_row = db.scalar(
                    select(EcbRate)
                    .where(EcbRate.currency == sec.currency, EcbRate.date <= nd_str)
                    .order_by(EcbRate.date.desc())
                )
                if rate_row is None:
                    if nd < today:
                        plan.done_count += 1
                        continue
                    break
                rate = rate_row.rate

            db.add(TransactionRow(
                position_id=plan.position_id,
                type="buy",
                date=nd_str,
                shares=plan.amount_per_period / price_row.close,
                price=price_row.close,
                fee=plan.fee_per_period,
                currency=sec.currency,
                exchange_rate=rate,
            ))
            plan.done_count += 1
            created += 1

        if plan.done_count >= plan.total_count:
            db.delete(plan)

    db.commit()
    if created:
        log.info("Aportaciones periódicas creadas: %d", created)
    return created


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


# Pausa entre snapshots para no saturar Yahoo (rate-limiting / 429).
_SNAPSHOT_SLEEP = 0.3


def _active_security_ids(db: Session) -> set[int]:
    """
    Valores "en uso": los que algún usuario posee (positions) o sigue
    (favorites). Solo estos se actualizan en el job en vivo de cada N minutos;
    el resto del catálogo se refresca en el barrido nocturno o bajo demanda.
    """
    pos_ids = db.scalars(select(Position.security_id).distinct()).all()
    fav_ids = db.scalars(select(Favorite.security_id).distinct()).all()
    return set(pos_ids) | set(fav_ids)


def _is_rate_limited(exc: Exception) -> bool:
    """Heurística: ¿la excepción de yfinance indica rate-limit/baneo de Yahoo?"""
    msg = str(exc).lower()
    return "429" in msg or "too many requests" in msg or "rate limit" in msg


_BATCH_CHUNK = 40   # tickers por petición en el modo batch (yf.download)


def update_snapshots(
    db: Session,
    include_funds: bool = True,
    only_ids: set[int] | None = None,
    with_dividends: bool = True,
    batch: bool = False,
) -> None:
    """
    Actualiza los snapshots de precio en vivo.

    - include_funds=False omite los mercados de fondos (NAV diario; no cambia
      intradía). El job nocturno los incluye.
    - only_ids: si se indica, solo se actualizan esos valores (conjunto activo
      del job en vivo). None = todo el catálogo (barrido nocturno).
    - with_dividends: el path en vivo lo pone a False para no hacer la petición
      extra de dividendos a Yahoo; se capturan en el barrido nocturno.
    - batch: agrupa los tickers en una sola petición (yf.download) por lote.
      Solo válido con with_dividends=False (el batch no trae dividendos). Lo usa
      el job en vivo para minimizar las peticiones a Yahoo.

    Si Yahoo responde rate-limit (429) se interrumpe la pasada para no insistir.
    """
    q = select(Security)
    if only_ids is not None:
        if not only_ids:
            return
        q = q.where(Security.id.in_(only_ids))
    securities = db.scalars(q).all()
    fund_codes = _fund_market_codes(db) if not include_funds else set()
    targets = [s for s in securities if include_funds or s.market not in fund_codes]

    if batch and not with_dividends:
        for i in range(0, len(targets), _BATCH_CHUNK):
            chunk = targets[i:i + _BATCH_CHUNK]
            quotes = _yahoo.fetch_live_quotes([s.yahoo_ticker for s in chunk])
            for sec in chunk:
                quote = quotes.get(sec.yahoo_ticker)
                if quote is None or quote.last_price is None:
                    continue
                try:
                    _apply_quote_to_snapshot(db, sec, quote, with_dividends=False)
                except Exception:
                    db.rollback()
                    log.exception("Error guardando snapshot de %s", sec.yahoo_ticker)
            time.sleep(_SNAPSHOT_SLEEP)
        return

    # Path individual (barrido nocturno / dividendos / sin batch)
    for sec in targets:
        try:
            _update_snapshot_for_security(db, sec, with_dividends=with_dividends)
        except Exception as exc:
            db.rollback()
            if _is_rate_limited(exc):
                log.warning(
                    "Yahoo rate-limit al actualizar %s; se interrumpe la pasada de snapshots",
                    sec.yahoo_ticker,
                )
                break
            log.exception("Error actualizando snapshot de %s", sec.yahoo_ticker)
        time.sleep(_SNAPSHOT_SLEEP)


def refresh_market_snapshots(market_code: str, with_dividends: bool = False) -> int:
    """
    Refresca en SEGUNDO PLANO (sesión propia) los snapshots de un mercado.
    Usado por el refresco bajo demanda de Top movers al abrir el Dashboard.
    Paced + corte ante rate-limit. Devuelve cuántos se intentaron.
    """
    from app.database import SessionLocal
    db = SessionLocal()
    n = 0
    try:
        secs = db.scalars(select(Security).where(Security.market == market_code)).all()
        # Batch (yf.download) por lotes: 1 petición por cada _BATCH_CHUNK tickers.
        for i in range(0, len(secs), _BATCH_CHUNK):
            chunk = secs[i:i + _BATCH_CHUNK]
            quotes = _yahoo.fetch_live_quotes([s.yahoo_ticker for s in chunk])
            for sec in chunk:
                quote = quotes.get(sec.yahoo_ticker)
                if quote is None or quote.last_price is None:
                    continue
                try:
                    _apply_quote_to_snapshot(db, sec, quote, with_dividends=False)
                    n += 1
                except Exception:
                    db.rollback()
            time.sleep(_SNAPSHOT_SLEEP)
    finally:
        db.close()
    return n


def refresh_all_full() -> None:
    """Barrido completo (histórico + snapshots) en SEGUNDO PLANO, sesión propia."""
    from app.database import SessionLocal
    db = SessionLocal()
    try:
        update_price_history(db)
        update_snapshots(db, include_funds=True, with_dividends=True)
    finally:
        db.close()


def _update_snapshot_for_security(
    db: Session, sec: Security, with_dividends: bool = True
) -> None:
    quote = _yahoo.fetch_live_quote(sec.yahoo_ticker, with_dividends=with_dividends)
    # Si no hay precio (mercado cerrado, festivo), conservar el snapshot anterior
    if quote.last_price is None:
        return
    _apply_quote_to_snapshot(db, sec, quote, with_dividends)


def _apply_quote_to_snapshot(
    db: Session, sec: Security, quote, with_dividends: bool
) -> None:
    """Calcula rangos desde el histórico en BD y hace upsert del snapshot con
    el 'quote' ya obtenido (sea individual o de un lote)."""
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

    # En el path en vivo no se consulta el dividendo (with_dividends=False) para
    # ahorrar una petición a Yahoo: conservamos el último dividendo ya guardado
    # (lo captura el barrido nocturno) en lugar de sobrescribirlo con None.
    if with_dividends:
        last_dividend_value = quote.last_dividend
    else:
        existing = db.get(PriceSnapshot, sec.id)
        last_dividend_value = existing.last_dividend if existing else None

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
            max_2y=stats.max_2y,
            min_5y=stats.min_5y,
            max_5y=stats.max_5y,
            last_dividend=last_dividend_value,
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
                "max_2y": stats.max_2y,
                "min_5y": stats.min_5y,
                "max_5y": stats.max_5y,
                "last_dividend": last_dividend_value,
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

    # ¿Hay ya divisas distintas de USD? Tras actualizar desde una versión
    # anterior (solo USD), max(date) es reciente; si arrancáramos desde ahí, las
    # demás divisas no tendrían histórico. En ese caso hacemos backfill completo.
    has_other = db.scalar(
        select(EcbRate.currency).where(EcbRate.currency != "USD").limit(1)
    )
    last_date_str = db.scalar(select(func.max(EcbRate.date)))
    if last_date_str and has_other:
        from_date = date.fromisoformat(last_date_str) + timedelta(days=1)
    else:
        from_date = today - timedelta(days=5 * 365)

    if from_date > today:
        return

    try:
        rates = _ecb.fetch_all_rates(from_date, today)
    except Exception:
        log.exception("Error descargando tipos BCE")
        return

    for (date_str, currency), rate in rates.items():
        stmt = (
            sqlite_insert(EcbRate)
            .values(date=date_str, currency=currency, rate=rate)
            .on_conflict_do_nothing()
        )
        db.execute(stmt)

    db.commit()
    log.info("Tipos BCE (multi-divisa): %d entradas desde %s", len(rates), from_date)


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
    active = _active_security_ids(db)
    log.info(
        "Actualizacion live de snapshots (activos=%d, fondos=%s)",
        len(active), include_funds,
    )
    # Solo el conjunto activo (poseídos/favoritos), sin dividendos y por lotes
    # (yf.download) para minimizar las peticiones a Yahoo.
    update_snapshots(db, include_funds=include_funds, only_ids=active, with_dividends=False, batch=True)
    if include_funds:
        _mark_funds_refreshed(db, now)
    log.info("Snapshots live completados")
    try:
        check_push_alerts(db)
    except Exception:
        log.exception("Error en check_push_alerts (no crítico)")


# ---------------------------------------------------------------------------
#  5. Alertas push — comprobar precios y enviar notificaciones push
# ---------------------------------------------------------------------------

def _compute_user_alert_keys(db: Session, user_id: int) -> list[str]:
    """
    Devuelve las claves activas de alertas para el usuario:
    - "buy:{security_id}" si last_price <= target_buy_price en favorites
    - "sell:{security_id}" si last_price >= target_sell_price en positions
    """
    from decimal import Decimal
    keys: list[str] = []

    # Alertas de compra — fuente: favorites.target_buy_price
    favs = db.scalars(select(Favorite).where(Favorite.user_id == user_id)).all()
    for fav in favs:
        if fav.target_buy_price is None:
            continue
        snap = db.get(PriceSnapshot, fav.security_id)
        if snap and snap.last_price is not None:
            if Decimal(str(snap.last_price)) <= fav.target_buy_price:
                keys.append(f"buy:{fav.security_id}")

    # Alertas de venta — fuente: positions.target_sell_price
    positions = db.scalars(select(Position).where(Position.user_id == user_id)).all()
    for pos in positions:
        if pos.target_sell_price is None:
            continue
        snap = db.get(PriceSnapshot, pos.security_id)
        if snap and snap.last_price is not None:
            if Decimal(str(snap.last_price)) >= pos.target_sell_price:
                keys.append(f"sell:{pos.security_id}")

    return sorted(set(keys))


def _build_push_payload(db: Session, alert_keys: list[str]) -> dict:
    """Construye el payload JSON de la notificación push."""
    import json

    lines: list[str] = []
    for key in alert_keys[:5]:            # máximo 5 en el texto
        kind, sec_id_str = key.split(":")
        sec_id = int(sec_id_str)
        sec = db.get(Security, sec_id)
        snap = db.get(PriceSnapshot, sec_id)
        name = sec.name if sec else sec_id_str
        price_str = f" ({float(snap.last_price):.2f})" if snap and snap.last_price else ""
        tipo = "Comprar" if kind == "buy" else "Vender"
        lines.append(f"{tipo}: {name}{price_str}")

    n = len(alert_keys)
    title = f"JSG Portfolio — {'alerta' if n == 1 else f'{n} alertas'} de precio"
    body  = "\n".join(lines)
    if n > 5:
        body += f"\n(+{n - 5} más)"

    # La URL de destino: si es una sola alerta, ir directamente al valor
    url = "/markets"
    if n == 1:
        sec_id = int(alert_keys[0].split(":")[1])
        url = f"/securities/{sec_id}"

    return {"title": title, "body": body, "url": url}


def check_push_alerts(db: Session) -> None:
    """
    Para cada suscripción push activa:
    1. Calcula las alertas activas del usuario.
    2. Compara con las últimas notificadas (last_notified_keys).
    3. Si hay alertas nuevas → envía push y actualiza last_notified_keys.
    """
    import json as _json
    from app.api.push import get_vapid_private_key, get_vapid_email

    private_key = get_vapid_private_key(db)
    if not private_key:
        return

    vapid_claims = {"sub": get_vapid_email(db)}

    subs = db.scalars(select(PushSubscription)).all()
    if not subs:
        return

    # Agrupar suscripciones por usuario para calcular alertas una vez
    by_user: dict[int, list[PushSubscription]] = {}
    for sub in subs:
        by_user.setdefault(sub.user_id, []).append(sub)

    for user_id, user_subs in by_user.items():
        current_keys = _compute_user_alert_keys(db, user_id)
        current_set  = set(current_keys)

        for sub in user_subs:
            last_set: set[str] = set()
            if sub.last_notified_keys:
                try:
                    last_set = set(_json.loads(sub.last_notified_keys))
                except Exception:
                    last_set = set()

            new_keys = sorted(current_set - last_set)
            if not new_keys:
                # Actualizar la lista de activas (pueden haber desaparecido)
                if set(last_set) != current_set:
                    sub.last_notified_keys = _json.dumps(current_keys)
                continue

            # Hay alertas nuevas → enviar push
            payload = _build_push_payload(db, new_keys)
            try:
                from pywebpush import webpush
                webpush(
                    subscription_info={
                        "endpoint": sub.endpoint,
                        "keys": {"p256dh": sub.p256dh, "auth": sub.auth},
                    },
                    data=_json.dumps(payload).encode(),
                    vapid_private_key=private_key,
                    vapid_claims=vapid_claims,
                    content_type="application/json",
                )
                sub.last_notified_keys = _json.dumps(current_keys)
                log.info("Push enviado a user %d (%d alertas nuevas)", user_id, len(new_keys))
            except Exception as exc:
                log.warning("Push fallido (user=%d): %s", user_id, exc)
                # Si el endpoint ya no existe (HTTP 410), borrar la suscripción
                err_str = str(exc).lower()
                if "410" in err_str or "unsubscribe" in err_str or "gone" in err_str:
                    db.delete(sub)

    db.commit()
