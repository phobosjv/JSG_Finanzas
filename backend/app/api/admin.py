"""
api/admin.py
============
Gestión de usuarios. Solo accesible para administradores (is_admin=True).

GET    /admin/users                — lista todos los usuarios.
POST   /admin/users                — crea un usuario (normal o admin).
PATCH  /admin/users/{id}/password  — cambia la contraseña de un usuario.
PATCH  /admin/users/{id}/role      — cambia el rol (admin/usuario). No sobre sí mismo.
DELETE /admin/users/{id}           — elimina un usuario (no puede ser el propio admin).
"""

from __future__ import annotations

import json
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_admin
from app.auth.security import hash_password
from app.models import DividendRow, Favorite, Position, Security, TransactionRow, User
from app.schemas.auth import ChangePasswordRequest, CreateUserRequest, UserAdminOut
from app.services.backup import (
    AdminImportResult,
    build_admin_export,
    validate_admin_backup,
)


class ChangeRoleRequest(BaseModel):
    is_admin: bool

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/users", response_model=list[UserAdminOut])
def list_users(
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    return db.scalars(select(User).order_by(User.id)).all()


@router.post("/users", response_model=UserAdminOut, status_code=status.HTTP_201_CREATED)
def create_user(
    body: CreateUserRequest,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
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


def _require_user(db: Session, user_id: int) -> User:
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Usuario no encontrado")
    return user


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
                (str(tx.date), tx.type, str(tx.shares), str(tx.price))
                for tx in db.scalars(
                    select(TransactionRow).where(TransactionRow.position_id == pos.id)
                ).all()
            }
            for tx_data in pos_data.get("transactions", []):
                key = (
                    str(tx_data["date"]),
                    tx_data["type"],
                    str(Decimal(str(tx_data["shares"]))),
                    str(Decimal(str(tx_data["price"]))),
                )
                if key in existing_txs:
                    continue
                db.add(TransactionRow(
                    position_id=pos.id,
                    type=tx_data["type"],
                    date=tx_data["date"],
                    shares=Decimal(str(tx_data["shares"])),
                    price=Decimal(str(tx_data["price"])),
                    fee=Decimal(str(tx_data.get("fee", "0"))),
                    currency=tx_data["currency"],
                    exchange_rate=Decimal(str(tx_data.get("exchange_rate", "1"))),
                ))
                result.transactions_added += 1

            existing_divs = {
                (str(div.date), str(div.gross_amount))
                for div in db.scalars(
                    select(DividendRow).where(DividendRow.position_id == pos.id)
                ).all()
            }
            for div_data in pos_data.get("dividends", []):
                key = (str(div_data["date"]), str(Decimal(str(div_data["gross_amount"]))))
                if key in existing_divs:
                    continue
                db.add(DividendRow(
                    position_id=pos.id,
                    date=div_data["date"],
                    shares_at_date=Decimal(str(div_data["shares_at_date"])),
                    gross_per_share=Decimal(str(div_data["gross_per_share"])),
                    gross_amount=Decimal(str(div_data["gross_amount"])),
                    withholding_tax=Decimal(str(div_data.get("withholding_tax", "0"))),
                    currency=div_data["currency"],
                    exchange_rate=Decimal(str(div_data.get("exchange_rate", "1"))),
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
