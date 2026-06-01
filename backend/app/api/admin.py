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
"""

from __future__ import annotations

import json
import logging
import threading as _threading
from datetime import date as date_type, datetime, timezone
from decimal import Decimal, InvalidOperation

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_admin
from app.auth.security import hash_password
from app.models import DividendRow, Favorite, Position, Security, TransactionRow, User, UserStatusLog
from app.schemas.auth import (
    ChangePasswordRequest, CreateUserRequest, UserAdminOut,
    UserStatusIn, UserExpiryIn, UserStatusLogOut,
)
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
def force_history_update(_admin: User = Depends(require_admin)):
    """Lanza update_price_history + update_snapshots en un hilo en segundo plano.

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
        )

    def _run() -> None:
        from app.database import SessionLocal
        from app.scheduler.jobs import update_price_history, update_snapshots
        db = SessionLocal()
        try:
            update_price_history(db)
            update_snapshots(db)
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
        }
        for u in db.scalars(select(User).order_by(User.id)).all()
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
            positions_data.append({
                "security_ticker": sec.yahoo_ticker,
                "notes": pos.notes,
                "target_sell_price": str(pos.target_sell_price) if pos.target_sell_price else None,
                "transactions": [
                    {
                        "type": tx.type,
                        "date": str(tx.date),
                        "shares": str(tx.shares),
                        "price": str(tx.price),
                        "fee": str(tx.fee),
                        "currency": tx.currency,
                        "exchange_rate": str(tx.exchange_rate),
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

        portfolios_data.append({
            "username": user.username,
            "positions": positions_data,
            "favorites": favorites_data,
        })

    payload = build_admin_export(users_data, securities_data, portfolios_data)
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

    # --- Usuarios ---
    for u_data in data.get("users", []):
        username = u_data.get("username", "")
        existing = db.scalar(select(User).where(User.username == username))
        if existing:
            result.users_skipped += 1
        else:
            db.add(User(
                username=username,
                password_hash=u_data["password_hash"],
                is_admin=u_data.get("is_admin", False),
            ))
            result.users_created += 1
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
                    if tx_data["type"] not in ("buy", "sell"):
                        raise ValueError("type debe ser 'buy' o 'sell'")
                    if tx_data["currency"] not in ("EUR", "USD"):
                        raise ValueError("currency debe ser 'EUR' o 'USD'")
                    if tx_data["currency"] == "USD" and tx_rate == Decimal("1"):
                        raise ValueError(
                            "currency='USD' con exchange_rate=1 es incoherente: "
                            "el tipo EUR/USD del BCE nunca es exactamente 1."
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
                    if div_data["currency"] not in ("EUR", "USD"):
                        raise ValueError("currency debe ser 'EUR' o 'USD'")
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

    db.commit()
    return result.to_dict()
