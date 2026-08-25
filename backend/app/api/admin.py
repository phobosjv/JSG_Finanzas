"""
api/admin.py
============
Gestión de usuarios. Solo accesible para administradores (is_admin=True).

GET    /admin/users                       — lista todos los usuarios.
POST   /admin/users                       — crea un usuario (normal o admin).
PATCH  /admin/users/{id}/password         — cambia la contraseña de un usuario.
PATCH  /admin/users/{id}/role             — cambia el rol (admin/usuario). No sobre sí mismo.
DELETE /admin/users/{id}                  — elimina un usuario (no puede ser el propio admin).
POST   /admin/force-history-update        — lanza update_price_history en segundo plano.
GET    /admin/force-history-update/status — estado del job en curso o del último ejecutado.
POST   /admin/notifications/send          — envía notificación personalizada a un usuario o a todos.
"""

from __future__ import annotations

import json
import logging
import threading as _threading
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_admin
from app.auth.security import hash_password
from app.models import (
    AppConfig, DividendRow, Favorite, MarketRow, Position, RecurringPlanRow,
    Security, SecuritySplit, SubcarteraRow, SubcarteraPositionRow,
    TaxBracketRow, TransactionRow, User, UserStatusLog,
)
from app.models.catalog_requests import UserNotificationRow
from app.schemas.catalog_requests import AdminNotificationSend
from app.schemas.auth import (
    ChangePasswordRequest, CreateUserRequest, UserAdminOut,
    UserStatusIn, UserExpiryIn, UserStatusLogOut, UserEmailIn,
)
from app.api.admin_markets import _get_supported_currencies
from app.api.backup import import_recurring_plans
from app.services.backup import (
    AdminImportResult,
    build_admin_export,
    validate_admin_backup,
)


log = logging.getLogger(__name__)


class ChangeRoleRequest(BaseModel):
    is_admin: bool

router = APIRouter(prefix="/admin", tags=["admin"])

# ---------------------------------------------------------------------------
#  Estado compartido del job de actualización forzada de historial
# ---------------------------------------------------------------------------

_history_job: dict = {
    "running": False,
    "started_at": None,
    "finished_at": None,
    "result": None,   # None | "ok" | "error: <mensaje>"
    "full": False,    # True si la ultima ejecucion fue reconstruccion completa
}
_history_job_lock = _threading.Lock()


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _log_status(
    db: Session,
    user_id: int,
    actor_id: int | None,
    status_str: str,
    annotation: str | None = None,
) -> None:
    db.add(UserStatusLog(
        user_id=user_id,
        actor_id=actor_id,
        status=status_str,
        annotation=annotation,
        created_at=_now(),
    ))


@router.get("/users", response_model=list[UserAdminOut])
def list_users(
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    users = db.scalars(select(User).order_by(User.id)).all()

    # Usuarios que tienen al menos una transacción — consulta única eficiente
    from sqlalchemy import distinct as _distinct
    user_ids_with_ops: set[int] = set(
        db.scalars(
            select(_distinct(Position.user_id))
            .join(TransactionRow, TransactionRow.position_id == Position.id)
        ).all()
    )

    result = []
    for u in users:
        out = UserAdminOut.model_validate(u)
        out.has_operations = u.id in user_ids_with_ops
        result.append(out)
    return result


@router.post("/users", response_model=UserAdminOut, status_code=status.HTTP_201_CREATED)
def create_user(
    body: CreateUserRequest,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    if db.scalar(select(User).where(User.username == body.username)):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"El usuario '{body.username}' ya existe",
        )
    user = User(
        username=body.username,
        password_hash=hash_password(body.password),
        is_admin=body.is_admin,
        email=body.email or None,
    )
    db.add(user)
    db.flush()  # obtener user.id antes del commit
    _log_status(db, user.id, actor_id=admin.id, status_str="registered")
    db.commit()
    db.refresh(user)
    return user


@router.patch("/users/{user_id}/password", response_model=UserAdminOut)
def change_password(
    user_id: int,
    body: ChangePasswordRequest,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    user = _require_user(db, user_id)
    user.password_hash = hash_password(body.password)
    db.commit()
    db.refresh(user)
    return user


@router.patch("/users/{user_id}/role", response_model=UserAdminOut)
def change_role(
    user_id: int,
    body: ChangeRoleRequest,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    if user_id == admin.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No puedes cambiar tu propio rol",
        )
    user = _require_user(db, user_id)
    user.is_admin = body.is_admin
    db.commit()
    db.refresh(user)
    return user


@router.delete("/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_user(
    user_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    if user_id == admin.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No puedes eliminar tu propia cuenta",
        )
    user = _require_user(db, user_id)
    db.delete(user)
    db.commit()


@router.patch("/users/{user_id}/status", response_model=UserAdminOut)
def set_user_status(
    user_id: int,
    body: UserStatusIn,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    user = _require_user(db, user_id)
    if user.id == admin.id and not body.enabled:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No puedes deshabilitar tu propia cuenta",
        )
    user.is_enabled = body.enabled
    _log_status(
        db, user.id, actor_id=admin.id,
        status_str="enabled" if body.enabled else "disabled",
        annotation=body.annotation,
    )
    db.commit()
    db.refresh(user)
    return user


@router.patch("/users/{user_id}/expiry", response_model=UserAdminOut)
def set_user_expiry(
    user_id: int,
    body: UserExpiryIn,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    user = _require_user(db, user_id)
    if body.expires_at is not None:
        user.expires_at = datetime(
            body.expires_at.year, body.expires_at.month, body.expires_at.day
        )
    else:
        user.expires_at = None
    db.commit()
    db.refresh(user)
    return user


@router.patch("/users/{user_id}/email", response_model=UserAdminOut)
def set_user_email(
    user_id: int,
    body: UserEmailIn,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    user = _require_user(db, user_id)
    user.email = body.email or None
    db.commit()
    db.refresh(user)
    return user


@router.get("/users/{user_id}/history", response_model=list[UserStatusLogOut])
def get_user_history(
    user_id: int,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    _require_user(db, user_id)
    logs = db.scalars(
        select(UserStatusLog)
        .where(UserStatusLog.user_id == user_id)
        .order_by(UserStatusLog.created_at.desc())
    ).all()
    return [
        UserStatusLogOut(
            id=log.id,
            status=log.status,
            annotation=log.annotation,
            created_at=log.created_at,
            actor_username=log.actor.username if log.actor else None,
        )
        for log in logs
    ]


def _require_user(db: Session, user_id: int) -> User:
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Usuario no encontrado")
    return user


# ---------------------------------------------------------------------------
#  Actualización forzada del historial de precios
# ---------------------------------------------------------------------------

@router.post("/force-history-update", status_code=status.HTTP_202_ACCEPTED)
def force_history_update(
    full: bool = Query(False),
    _admin: User = Depends(require_admin),
):
    """Lanza update_price_history + update_snapshots + update_ecb_rates en un
    hilo en segundo plano: las MISMAS tres tareas que el job nocturno.

    Los tipos del BCE van incluidos porque el gráfico de evolución convierte
    cada cierre pasado con el tipo vigente EN ESA FECHA; sin ellos, _history_series
    cae al tipo más reciente y distorsiona toda la serie de los valores en divisa.
    Es el escenario tras migrar de servidor: el backup admin NO exporta
    'price_history' ni 'ecb_rates', así que este botón es la via de recuperacion.

    'full=true' vuelve a descargar los 5 años de historico IGNORANDO lo que ya
    haya guardado. Es la unica via para reparar un historico TRUNCADO: el modo
    incremental arranca en la ultima fecha almacenada de cada valor, asi que
    nunca rellena hacia atras. Tarda bastante mas (baja 5 años por valor en vez
    de una ventana de 7 dias), por eso no es el modo por defecto.

    Devuelve 409 si ya hay una actualización en curso.
    El frontend puede consultar /admin/force-history-update/status para
    hacer polling hasta que 'running' sea False.
    """
    with _history_job_lock:
        if _history_job["running"]:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Ya hay una actualización en curso. Espera a que termine.",
            )
        _history_job.update(
            running=True,
            started_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
            finished_at=None,
            result=None,
            full=full,
        )

    def _run() -> None:
        from app.database import SessionLocal
        from app.scheduler.jobs import (
            update_price_history, update_snapshots, update_ecb_rates,
        )
        db = SessionLocal()
        try:
            update_price_history(db, full=full)
            update_snapshots(db)
            update_ecb_rates(db)
            with _history_job_lock:
                _history_job["result"] = "ok"
            log.info("force-history-update completado correctamente")
        except Exception as exc:
            log.exception("Error en force-history-update")
            with _history_job_lock:
                _history_job["result"] = f"error: {exc}"
        finally:
            db.close()
            with _history_job_lock:
                _history_job["running"] = False
                _history_job["finished_at"] = datetime.now(timezone.utc).isoformat(
                    timespec="seconds"
                )

    _threading.Thread(target=_run, daemon=True, name="force-history-update").start()
    return {"detail": "Actualización iniciada en segundo plano"}


@router.get("/force-history-update/status")
def get_history_update_status(_admin: User = Depends(require_admin)):
    """Estado del job de actualización forzada (en curso o último ejecutado)."""
    with _history_job_lock:
        return dict(_history_job)


# ---------------------------------------------------------------------------
#  Rellenar ISINs vacíos desde Yahoo (admin) — job en segundo plano
# ---------------------------------------------------------------------------

# El rellenado consulta Yahoo VALOR A VALOR (yfinance Ticker.isin), una llamada
# de red por valor. Con muchos valores tarda minutos: hacerlo dentro de la
# petición HTTP provoca timeouts en el navegador/proxy ("Failed to fetch") y,
# si se corta, no se guarda nada. Por eso se ejecuta en un hilo con commit
# INCREMENTAL (cada acierto se persiste al momento) y el frontend consulta el
# estado por polling. Mismo patrón que la actualización forzada de historial.

_isin_job: dict = {
    "running": False,
    "total": 0,            # valores sin ISIN al empezar (excluye cripto)
    "checked": 0,          # procesados hasta ahora
    "updated": 0,          # rellenados con éxito (ya persistidos)
    "updated_pass1": 0,    # rellenados por coincidencia exacta (Yahoo por ticker)
    "updated_pass2": 0,    # rellenados por búsqueda heurística (Business Insider por nombre)
    "not_found": [],       # tickers que siguen sin ISIN tras ambas pasadas
    "skipped_existing": [], # heurística encontró un ISIN, pero ya existía en la BBDD (descartado)
    "started_at": None,
    "finished_at": None,
    "result": None,        # None | "ok" | "error: <mensaje>"
}
_isin_job_lock = _threading.Lock()


def _isin_pending(db: Session) -> list[tuple[int, str, str]]:
    """(id, ticker, nombre) de los valores sin ISIN, EXCLUYENDO cripto."""
    rows = db.execute(
        select(Security.id, Security.yahoo_ticker, Security.name, MarketRow.market_type)
        .join(MarketRow, Security.market == MarketRow.code, isouter=True)
        .where((Security.isin.is_(None)) | (func.trim(Security.isin) == ""))
    ).all()
    # Las cripto no tienen ISIN: se excluyen. Mercado desconocido → se trata como acción.
    return [(r[0], r[1], r[2]) for r in rows if (r[3] or "stock") != "crypto"]


def _fill_isins_worker(db: Session, provider, *, bi_search=None, on_item=None) -> dict:
    """
    Rellena el ISIN de los valores que no lo tienen. Dos pasadas:

      Pasada 1 (exacta): 'provider.fetch_isin(ticker)' (Yahoo por ticker).
      Pasada 2 (heurística, opcional): 'bi_search(name, ticker)' (Business
        Insider por nombre), solo para los que la pasada 1 no resolvió.

    En AMBAS pasadas se acepta el ISIN únicamente si NO existe ya en la BBDD
    (evita asignar a un valor un ISIN que pertenece a otro: señal de coincidencia
    equivocada). Yahoo devuelve ocasionalmente un ISIN de otra empresa —p. ej.
    'SAN.MC' -> CA05973U1057, canadiense, cuando Santander es ES0113900J37— y
    '_normalize_isin' solo valida la FORMA, así que la colisión es la única
    señal disponible. Un ETF multi-listado (mismo ISIN en dos bolsas) queda sin
    rellenar en el segundo listing: es deliberado, preferimos el hueco al dato
    incorrecto, porque el worker nunca sobreescribe un ISIN ya asignado.

    Excluye las cripto (no tienen ISIN). Commit INCREMENTAL: cada ISIN se guarda
    al momento, así un corte/timeout no pierde lo ya hecho. Nunca sobreescribe un
    ISIN existente.

    'on_item(checked, updated, missing)' es un callback opcional de progreso.
    """
    pending = _isin_pending(db)
    existing: set[str] = set(
        db.scalars(
            select(Security.isin).where(
                Security.isin.is_not(None), func.trim(Security.isin) != ""
            )
        ).all()
    )

    checked = 0
    updated_p1 = 0
    updated_p2 = 0
    missing: list[str] = []                 # tickers aún sin ISIN (lista viva para el progreso)
    remaining: list[tuple[int, str, str]] = []  # tuplas pendientes de la pasada 2
    skipped_existing: list[str] = []

    def _report():
        if on_item is not None:
            on_item(checked, updated_p1 + updated_p2, list(missing))

    # ---- Pasada 1: coincidencia exacta por ticker (Yahoo) ----
    for sid, ticker, name in pending:
        isin = provider.fetch_isin(ticker)
        checked += 1
        if isin and isin not in existing:
            sec = db.get(Security, sid)
            sec.isin = isin
            db.commit()
            updated_p1 += 1
            existing.add(isin)
        else:
            if isin:
                # Yahoo devolvio un ISIN que ya pertenece a otro valor: misma
                # senal de coincidencia equivocada que aplica la pasada 2. Se
                # descarta y el valor pasa a la pasada 2, por si la busqueda
                # por nombre da con el correcto.
                skipped_existing.append(ticker)
            missing.append(ticker)
            remaining.append((sid, ticker, name))
        _report()

    # ---- Pasada 2: búsqueda heurística por nombre (Business Insider) ----
    if bi_search is not None:
        for sid, ticker, name in remaining:
            isin = bi_search(name, ticker)
            checked += 1
            if isin and isin not in existing:
                sec = db.get(Security, sid)
                sec.isin = isin
                db.commit()
                updated_p2 += 1
                existing.add(isin)
                missing.remove(ticker)
            elif isin:  # encontrado pero ya existe en la BBDD → no se asigna
                skipped_existing.append(ticker)
            _report()

    return {
        "checked": checked,
        "updated": updated_p1 + updated_p2,
        "updated_pass1": updated_p1,
        "updated_pass2": updated_p2,
        "not_found": missing,
        "skipped_existing": skipped_existing,
    }


@router.post("/securities/fill-isins", status_code=status.HTTP_202_ACCEPTED)
def fill_missing_isins(_admin: User = Depends(require_admin)):
    """
    Lanza en segundo plano el rellenado de ISINs vacíos desde Yahoo.

    Devuelve 202 de inmediato (evita el timeout "Failed to fetch" del navegador)
    y 409 si ya hay un proceso en curso. El frontend consulta
    GET /admin/securities/fill-isins/status para ver el progreso y, si falla,
    cuántos se rellenaron antes del fallo (el commit es incremental).
    """
    with _isin_job_lock:
        if _isin_job["running"]:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Ya hay un rellenado de ISINs en curso. Espera a que termine.",
            )
        _isin_job.update(
            running=True, total=0, checked=0, updated=0,
            updated_pass1=0, updated_pass2=0, not_found=[], skipped_existing=[],
            started_at=_now().isoformat(timespec="seconds"),
            finished_at=None, result=None,
        )

    def _run() -> None:
        from app.database import SessionLocal
        from app.providers.yahoo import YahooProvider
        from app.providers.business_insider import search_isin_by_name

        db = SessionLocal()
        try:
            with _isin_job_lock:
                _isin_job["total"] = len(_isin_pending(db))

            def _progress(checked: int, updated: int, missing: list[str]) -> None:
                with _isin_job_lock:
                    _isin_job["checked"] = checked
                    _isin_job["updated"] = updated
                    _isin_job["not_found"] = missing

            res = _fill_isins_worker(
                db, YahooProvider(), bi_search=search_isin_by_name, on_item=_progress
            )
            with _isin_job_lock:
                _isin_job["updated_pass1"] = res["updated_pass1"]
                _isin_job["updated_pass2"] = res["updated_pass2"]
                _isin_job["skipped_existing"] = res["skipped_existing"]
                _isin_job["not_found"] = res["not_found"]
                _isin_job["result"] = "ok"
            log.info(
                "fill-isins completado: %s rellenados (pasada 1: %s, pasada 2: %s)",
                res["updated"], res["updated_pass1"], res["updated_pass2"],
            )
        except Exception as exc:
            log.exception("Error en fill-isins")
            with _isin_job_lock:
                _isin_job["result"] = f"error: {exc}"
        finally:
            db.close()
            with _isin_job_lock:
                _isin_job["running"] = False
                _isin_job["finished_at"] = _now().isoformat(timespec="seconds")

    _threading.Thread(target=_run, daemon=True, name="fill-isins").start()
    return {"detail": "Rellenado de ISINs iniciado en segundo plano"}


@router.get("/securities/fill-isins/status")
def fill_isins_status(_admin: User = Depends(require_admin)):
    """Estado del job de rellenado de ISINs (en curso o último ejecutado)."""
    with _isin_job_lock:
        return {**_isin_job, "not_found": list(_isin_job["not_found"])}


# ---------------------------------------------------------------------------
#  Backup completo (admin)
# ---------------------------------------------------------------------------

def _decimal_default(obj):
    if isinstance(obj, Decimal):
        return str(obj)
    raise TypeError(f"Object of type {type(obj)} is not JSON serializable")


@router.get("/backup/export")
def admin_export_backup(
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    """Exporta todos los usuarios, el catálogo de valores y todas las carteras."""
    users_data = [
        {
            "username": u.username,
            "password_hash": u.password_hash,
            "is_admin": u.is_admin,
            "is_enabled": u.is_enabled,
            "email": u.email,
            "expires_at": u.expires_at.isoformat() if u.expires_at else None,
            "created_at": u.created_at.isoformat() if u.created_at else None,
            "last_login_at": u.last_login_at.isoformat() if u.last_login_at else None,
        }
        for u in db.scalars(select(User).order_by(User.id)).all()
    ]

    # Configuración global (app_config): nombre de app, logo, divisas, umbral de
    # polvo, intervalo de snapshots, config de email (con secretos) y claves
    # VAPID. Se exporta tal cual para reproducir el sitio 1:1 (secretos en claro
    # — el fichero debe custodiarse).
    app_config_data = [
        {"key": c.key, "value": c.value}
        for c in db.scalars(select(AppConfig).order_by(AppConfig.key)).all()
    ]

    # Tramos IRPF configurables.
    tax_brackets_data = [
        {
            "min_amount": str(b.min_amount),
            "max_amount": str(b.max_amount) if b.max_amount is not None else None,
            "rate": str(b.rate),
            "sort_order": b.sort_order,
        }
        for b in db.scalars(
            select(TaxBracketRow).order_by(TaxBracketRow.sort_order, TaxBracketRow.id)
        ).all()
    ]

    # Splits globales, referenciados por ticker (portable entre servidores).
    security_splits_data = [
        {
            "security_ticker": sp.security.yahoo_ticker,
            "ex_date": sp.ex_date,
            "ratio_num": sp.ratio_num,
            "ratio_den": sp.ratio_den,
            "notes": sp.notes,
        }
        for sp in db.scalars(
            select(SecuritySplit).order_by(SecuritySplit.security_id, SecuritySplit.ex_date)
        ).all()
    ]

    markets_data = [
        {
            "code": m.code,
            "name": m.name,
            "index_ticker": m.index_ticker,
            "currency": m.currency,
            "fiscal_window_days": m.fiscal_window_days,
            "sort_order": m.sort_order,
            "yahoo_exchange": m.yahoo_exchange,
            "market_type": m.market_type,
            "is_fund_market": m.is_fund_market,
        }
        for m in db.scalars(select(MarketRow).order_by(MarketRow.code)).all()
    ]

    securities_data = [
        {
            "yahoo_ticker": s.yahoo_ticker,
            "name": s.name,
            "isin": s.isin,
            "google_ticker": s.google_ticker,
            "currency": s.currency,
            "market": s.market,
        }
        for s in db.scalars(select(Security).order_by(Security.id)).all()
    ]

    portfolios_data = []
    for user in db.scalars(select(User).order_by(User.id)).all():
        positions = db.scalars(
            select(Position).where(Position.user_id == user.id)
        ).all()

        positions_data = []
        for pos in positions:
            sec: Security = pos.security
            txs = db.scalars(
                select(TransactionRow)
                .where(TransactionRow.position_id == pos.id)
                .order_by(TransactionRow.date)
            ).all()
            divs = db.scalars(
                select(DividendRow)
                .where(DividendRow.position_id == pos.id)
                .order_by(DividendRow.date)
            ).all()
            plans = db.scalars(
                select(RecurringPlanRow).where(RecurringPlanRow.position_id == pos.id)
            ).all()
            positions_data.append({
                "security_ticker": sec.yahoo_ticker,
                "notes": pos.notes,
                "target_sell_price": str(pos.target_sell_price) if pos.target_sell_price else None,
                "recurring_plans": [
                    {
                        "amount_per_period": str(p.amount_per_period),
                        "fee_per_period": str(p.fee_per_period),
                        "frequency": p.frequency,
                        "start_date": p.start_date,
                        "total_count": p.total_count,
                        "done_count": p.done_count,
                        "currency": p.currency,
                    }
                    for p in plans
                ],
                "transactions": [
                    {
                        "type": tx.type,
                        "date": str(tx.date),
                        "shares": str(tx.shares),
                        "price": str(tx.price),
                        "fee": str(tx.fee),
                        "currency": tx.currency,
                        "exchange_rate": str(tx.exchange_rate),
                        "transfer_group_id": tx.transfer_group_id,
                    }
                    for tx in txs
                ],
                "dividends": [
                    {
                        "date": str(div.date),
                        "shares_at_date": str(div.shares_at_date),
                        "gross_per_share": str(div.gross_per_share),
                        "gross_amount": str(div.gross_amount),
                        "withholding_tax": str(div.withholding_tax),
                        "currency": div.currency,
                        "exchange_rate": str(div.exchange_rate),
                    }
                    for div in divs
                ],
            })

        favs = db.scalars(
            select(Favorite).where(Favorite.user_id == user.id)
        ).all()
        favorites_data = [
            {
                "security_ticker": fav.security.yahoo_ticker,
                "target_buy_price": str(fav.target_buy_price) if fav.target_buy_price else None,
            }
            for fav in favs
        ]

        # Subcarteras del usuario. Las posiciones se referencian por ticker
        # (portable): un usuario tiene una sola posición por valor.
        pos_id_to_ticker = {p.id: p.security.yahoo_ticker for p in positions}
        subcarteras_data = []
        for sub in db.scalars(
            select(SubcarteraRow)
            .where(SubcarteraRow.user_id == user.id)
            .order_by(SubcarteraRow.id)
        ).all():
            member_ids = db.scalars(
                select(SubcarteraPositionRow.position_id).where(
                    SubcarteraPositionRow.subcartera_id == sub.id
                )
            ).all()
            subcarteras_data.append({
                "name": sub.name,
                "description": sub.description,
                "position_tickers": [
                    pos_id_to_ticker[pid] for pid in member_ids
                    if pid in pos_id_to_ticker
                ],
            })

        portfolios_data.append({
            "username": user.username,
            "positions": positions_data,
            "favorites": favorites_data,
            "subcarteras": subcarteras_data,
        })

    payload = build_admin_export(
        users_data, securities_data, portfolios_data, markets_data,
        app_config=app_config_data,
        tax_brackets=tax_brackets_data,
        security_splits=security_splits_data,
    )
    json_bytes = json.dumps(payload, ensure_ascii=False, indent=2, default=_decimal_default).encode("utf-8")
    return Response(
        content=json_bytes,
        media_type="application/json",
        headers={
            "Content-Disposition": (
                f'attachment; filename="finanzas_admin_backup_{payload["exported_at"][:10]}.json"'
            )
        },
    )


@router.post("/backup/import")
async def admin_import_backup(
    request: Request,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    """
    Importa un backup completo. Idempotente:
    - Usuarios: crea si el username no existe; omite si ya existe.
    - Valores: crea si el yahoo_ticker no existe; actualiza metadatos si existe.
    - Carteras: añade transacciones/dividendos/favoritos no existentes.
    """
    try:
        data = await request.json()
    except Exception:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="JSON inválido")

    errors = validate_admin_backup(data)
    if errors:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=errors)

    result = AdminImportResult()

    def _parse_dt(raw):
        """ISO string → datetime, o None si no viene / no parsea."""
        if not raw:
            return None
        try:
            return datetime.fromisoformat(raw)
        except (ValueError, TypeError):
            return None

    # --- Usuarios ---
    # Crear los que falten (con todos los campos); a los existentes se les
    # actualiza email/is_enabled/expires_at desde el backup (no se toca la
    # contraseña ni is_admin de un usuario que ya existe).
    for u_data in data.get("users", []):
        username = u_data.get("username", "")
        existing = db.scalar(select(User).where(User.username == username))
        if existing:
            changed = False
            if "email" in u_data and existing.email != u_data.get("email"):
                existing.email = u_data.get("email"); changed = True
            if "is_enabled" in u_data and existing.is_enabled != bool(u_data["is_enabled"]):
                existing.is_enabled = bool(u_data["is_enabled"]); changed = True
            if "expires_at" in u_data:
                new_exp = _parse_dt(u_data.get("expires_at"))
                if existing.expires_at != new_exp:
                    existing.expires_at = new_exp; changed = True
            if changed:
                result.users_updated += 1
            else:
                result.users_skipped += 1
        else:
            db.add(User(
                username=username,
                password_hash=u_data["password_hash"],
                is_admin=u_data.get("is_admin", False),
                is_enabled=bool(u_data.get("is_enabled", True)),
                email=u_data.get("email"),
                expires_at=_parse_dt(u_data.get("expires_at")),
                created_at=_parse_dt(u_data.get("created_at")) or datetime.now(),
                last_login_at=_parse_dt(u_data.get("last_login_at")),
            ))
            result.users_created += 1
    db.flush()

    # --- Configuración global (app_config): upsert de cada clave ---
    for c_data in data.get("app_config", []):
        key = c_data.get("key")
        if not key:
            continue
        value = c_data.get("value")
        if value is None:
            continue
        cfg = db.get(AppConfig, key)
        if cfg is None:
            db.add(AppConfig(key=key, value=value))
        else:
            cfg.value = value
        result.config_keys += 1
    db.flush()

    # Divisas soportadas: se recalculan DESPUÉS de importar app_config, para que
    # las transacciones en divisas del backup validen contra la lista restaurada.
    valid_currencies = set(_get_supported_currencies(db))

    # --- Tramos IRPF: replace-all si el backup los trae ---
    tax_brackets = data.get("tax_brackets")
    if tax_brackets:
        for old in db.scalars(select(TaxBracketRow)).all():
            db.delete(old)
        db.flush()
        for b_data in tax_brackets:
            try:
                db.add(TaxBracketRow(
                    min_amount=Decimal(str(b_data["min_amount"])),
                    max_amount=(
                        Decimal(str(b_data["max_amount"]))
                        if b_data.get("max_amount") is not None else None
                    ),
                    rate=Decimal(str(b_data["rate"])),
                    sort_order=int(b_data.get("sort_order", 0)),
                ))
                result.tax_brackets_set += 1
            except (KeyError, TypeError, InvalidOperation, ValueError) as exc:
                result.errors.append(f"Tramo IRPF omitido: {exc}")
        db.flush()

    # --- Mercados (antes que los valores, que dependen de ellos) ---
    # Solo se crean los que falten (el código es PK); deriva market_type si no
    # viene (backups admin anteriores a v1.7.8).
    from datetime import datetime as _dt
    for m_data in data.get("markets", []):
        code = (m_data.get("code") or "").strip().lower()
        if not code or db.get(MarketRow, code) is not None:
            continue
        mt = m_data.get("market_type")
        if mt not in ("stock", "fund", "etf", "crypto"):
            if m_data.get("is_fund_market"):
                mt = "fund"
            elif "etf" in code:
                mt = "etf"
            elif "crypto" in code:
                mt = "crypto"
            else:
                mt = "stock"
        db.add(MarketRow(
            code=code,
            name=(m_data.get("name") or code).strip(),
            index_ticker=m_data.get("index_ticker") or None,
            currency=(m_data.get("currency") or "EUR").upper(),
            fiscal_window_days=max(1, m_data.get("fiscal_window_days") or 60),
            sort_order=m_data.get("sort_order", 0),
            yahoo_exchange=m_data.get("yahoo_exchange") or None,
            market_type=mt,
            is_fund_market=(mt == "fund"),
            created_at=_dt.now().isoformat(),
        ))
    db.flush()

    # --- Valores (catálogo) ---
    for s_data in data.get("securities", []):
        ticker = s_data.get("yahoo_ticker", "")
        sec = db.scalar(select(Security).where(Security.yahoo_ticker == ticker))
        if sec is None:
            db.add(Security(
                yahoo_ticker=ticker,
                name=s_data["name"],
                isin=s_data.get("isin"),
                google_ticker=s_data.get("google_ticker"),
                currency=s_data["currency"],
                market=s_data["market"],
            ))
            result.securities_created += 1
        else:
            sec.name = s_data["name"]
            sec.isin = s_data.get("isin")
            sec.google_ticker = s_data.get("google_ticker")
            sec.currency = s_data["currency"]
            sec.market = s_data["market"]
            result.securities_updated += 1
    db.flush()

    # --- Splits globales: upsert por (security, ex_date) ---
    for sp_data in data.get("security_splits", []):
        ticker = sp_data.get("security_ticker", "")
        sec = db.scalar(select(Security).where(Security.yahoo_ticker == ticker))
        if sec is None:
            result.errors.append(f"Split omitido: valor '{ticker}' no encontrado.")
            continue
        ex_date = sp_data.get("ex_date")
        try:
            ratio_num = int(sp_data["ratio_num"])
            ratio_den = int(sp_data["ratio_den"])
            if not ex_date or ratio_num <= 0 or ratio_den <= 0:
                raise ValueError("ex_date/ratio inválidos")
        except (KeyError, TypeError, ValueError) as exc:
            result.errors.append(f"Split omitido en '{ticker}': {exc}")
            continue
        existing_sp = db.scalar(
            select(SecuritySplit).where(
                SecuritySplit.security_id == sec.id,
                SecuritySplit.ex_date == ex_date,
            )
        )
        if existing_sp is None:
            db.add(SecuritySplit(
                security_id=sec.id,
                ex_date=ex_date,
                ratio_num=ratio_num,
                ratio_den=ratio_den,
                notes=sp_data.get("notes"),
            ))
            result.splits_added += 1
        else:
            existing_sp.ratio_num = ratio_num
            existing_sp.ratio_den = ratio_den
            existing_sp.notes = sp_data.get("notes")
    db.flush()

    # --- Carteras por usuario ---
    for portfolio in data.get("portfolios", []):
        username = portfolio.get("username", "")
        user = db.scalar(select(User).where(User.username == username))
        if user is None:
            result.errors.append(f"Usuario '{username}' no encontrado; se omite su cartera.")
            continue

        for pos_data in portfolio.get("positions", []):
            ticker = pos_data.get("security_ticker", "")
            sec = db.scalar(select(Security).where(Security.yahoo_ticker == ticker))
            if sec is None:
                result.positions_skipped += 1
                result.errors.append(f"Valor '{ticker}' no encontrado; se omite la posición.")
                continue

            result.positions_found += 1
            pos = db.scalar(
                select(Position).where(
                    Position.user_id == user.id,
                    Position.security_id == sec.id,
                )
            )
            if pos is None:
                pos = Position(
                    user_id=user.id,
                    security_id=sec.id,
                    notes=pos_data.get("notes"),
                    target_sell_price=(
                        Decimal(str(pos_data["target_sell_price"]))
                        if pos_data.get("target_sell_price") else None
                    ),
                )
                db.add(pos)
                db.flush()

            existing_txs = {
                (tx.date, tx.type, tx.shares, tx.price, tx.fee)
                for tx in db.scalars(
                    select(TransactionRow).where(TransactionRow.position_id == pos.id)
                ).all()
            }
            for tx_data in pos_data.get("transactions", []):
                try:
                    tx_shares = Decimal(str(tx_data["shares"]))
                    tx_price  = Decimal(str(tx_data["price"]))
                    tx_fee    = Decimal(str(tx_data.get("fee", "0")))
                    tx_rate   = Decimal(str(tx_data.get("exchange_rate", "1")))
                    if tx_shares <= 0:
                        raise ValueError("shares debe ser > 0")
                    if tx_price <= 0:
                        raise ValueError("price debe ser > 0")
                    if tx_fee < 0:
                        raise ValueError("fee no puede ser negativo")
                    if tx_rate <= 0:
                        raise ValueError("exchange_rate debe ser > 0")
                    if tx_data["type"] not in ("buy", "sell", "transfer_in", "transfer_out"):
                        raise ValueError("type debe ser 'buy', 'sell', 'transfer_in' o 'transfer_out'")
                    if tx_data["currency"] not in valid_currencies:
                        raise ValueError(f"currency '{tx_data['currency']}' no está soportada")
                    if tx_data["currency"] != "EUR" and tx_rate == Decimal("1"):
                        raise ValueError(
                            f"currency='{tx_data['currency']}' con exchange_rate=1 es incoherente"
                        )
                    if tx_data["currency"] == "EUR" and tx_rate != Decimal("1"):
                        raise ValueError("currency='EUR' exige exchange_rate=1")
                except (KeyError, TypeError, InvalidOperation, ValueError) as exc:
                    result.errors.append(
                        f"Transacción omitida en '{ticker}': {exc}"
                    )
                    continue
                key = (tx_data["date"], tx_data["type"], tx_shares, tx_price, tx_fee)
                if key in existing_txs:
                    continue
                db.add(TransactionRow(
                    position_id=pos.id,
                    type=tx_data["type"],
                    date=tx_data["date"],
                    shares=tx_shares,
                    price=tx_price,
                    fee=tx_fee,
                    currency=tx_data["currency"],
                    exchange_rate=tx_rate,
                    transfer_group_id=tx_data.get("transfer_group_id"),
                ))
                result.transactions_added += 1

            existing_divs = {
                (div.date, div.gross_amount)
                for div in db.scalars(
                    select(DividendRow).where(DividendRow.position_id == pos.id)
                ).all()
            }
            for div_data in pos_data.get("dividends", []):
                try:
                    div_shares = Decimal(str(div_data["shares_at_date"]))
                    div_gps    = Decimal(str(div_data["gross_per_share"]))
                    div_gross  = Decimal(str(div_data["gross_amount"]))
                    div_wht    = Decimal(str(div_data.get("withholding_tax", "0")))
                    div_rate   = Decimal(str(div_data.get("exchange_rate", "1")))
                    if div_shares <= 0:
                        raise ValueError("shares_at_date debe ser > 0")
                    if div_gps <= 0:
                        raise ValueError("gross_per_share debe ser > 0")
                    if div_gross <= 0:
                        raise ValueError("gross_amount debe ser > 0")
                    if div_wht < 0:
                        raise ValueError("withholding_tax no puede ser negativo")
                    if div_rate <= 0:
                        raise ValueError("exchange_rate debe ser > 0")
                    if div_data["currency"] not in valid_currencies:
                        raise ValueError(f"currency '{div_data['currency']}' no está soportada")
                    if div_data["currency"] != "EUR" and div_rate == Decimal("1"):
                        raise ValueError(f"currency='{div_data['currency']}' con exchange_rate=1 es incoherente")
                    if div_data["currency"] == "EUR" and div_rate != Decimal("1"):
                        raise ValueError("currency='EUR' exige exchange_rate=1")
                except (KeyError, TypeError, InvalidOperation, ValueError) as exc:
                    result.errors.append(
                        f"Dividendo omitido en '{ticker}': {exc}"
                    )
                    continue
                key = (div_data["date"], div_gross)
                if key in existing_divs:
                    continue
                db.add(DividendRow(
                    position_id=pos.id,
                    date=div_data["date"],
                    shares_at_date=div_shares,
                    gross_per_share=div_gps,
                    gross_amount=div_gross,
                    withholding_tax=div_wht,
                    currency=div_data["currency"],
                    exchange_rate=div_rate,
                ))
                result.dividends_added += 1

            # Planes de aportación periódica (v1.7.8)
            import_recurring_plans(db, pos.id, pos_data.get("recurring_plans"))

        # Favoritos
        for fav_data in portfolio.get("favorites", []):
            ticker = fav_data.get("security_ticker", "")
            sec = db.scalar(select(Security).where(Security.yahoo_ticker == ticker))
            if sec is None:
                continue
            existing_fav = db.scalar(
                select(Favorite).where(
                    Favorite.user_id == user.id,
                    Favorite.security_id == sec.id,
                )
            )
            if existing_fav is None:
                db.add(Favorite(
                    user_id=user.id,
                    security_id=sec.id,
                    target_buy_price=(
                        Decimal(str(fav_data["target_buy_price"]))
                        if fav_data.get("target_buy_price") else None
                    ),
                ))
                result.favorites_added += 1

        # Subcarteras del usuario (upsert por nombre; enlaza posiciones por
        # ticker). Requiere que las posiciones ya existan (creadas arriba).
        db.flush()
        for sub_data in portfolio.get("subcarteras", []):
            name = (sub_data.get("name") or "").strip()
            if not name:
                continue
            sub = db.scalar(
                select(SubcarteraRow).where(
                    SubcarteraRow.user_id == user.id,
                    SubcarteraRow.name == name,
                )
            )
            if sub is None:
                sub = SubcarteraRow(
                    user_id=user.id,
                    name=name,
                    description=sub_data.get("description"),
                )
                db.add(sub)
                db.flush()
                result.subcarteras_added += 1
            for ticker in sub_data.get("position_tickers", []):
                sec = db.scalar(select(Security).where(Security.yahoo_ticker == ticker))
                if sec is None:
                    continue
                pos = db.scalar(
                    select(Position).where(
                        Position.user_id == user.id,
                        Position.security_id == sec.id,
                    )
                )
                if pos is None:
                    continue
                link = db.get(SubcarteraPositionRow, (sub.id, pos.id))
                if link is None:
                    db.add(SubcarteraPositionRow(
                        subcartera_id=sub.id, position_id=pos.id
                    ))

    db.commit()
    return result.to_dict()


# ---------------------------------------------------------------------------
#  Notificaciones personalizadas (admin → usuario o broadcast)
# ---------------------------------------------------------------------------

@router.post("/notifications/send")
def send_admin_notification(
    body: AdminNotificationSend,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """Envía una notificación personalizada a un usuario concreto o a todos.

    Si body.user_id es None → broadcast a todos los usuarios activos (is_enabled).
    Devuelve {sent: N}.
    """
    if body.user_id is not None:
        target = db.get(User, body.user_id)
        if target is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Usuario no encontrado",
            )
        targets = [target]
    else:
        targets = db.scalars(
            select(User).where(User.is_enabled.is_(True))
        ).all()

    now = _now()
    for u in targets:
        db.add(UserNotificationRow(
            user_id=u.id,
            type="admin_message",
            title=body.title,
            body=body.body,
            created_at=now,
        ))
    db.commit()
    return {"sent": len(targets)}
