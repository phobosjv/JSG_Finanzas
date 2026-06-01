"""
api/backup.py
=============
Exportación e importación de la cartera del usuario en formato JSON.

GET  /backup/export  — descarga un fichero JSON con todas las posiciones,
                       transacciones y dividendos del usuario.
POST /backup/import  — carga un JSON previamente exportado. Es idempotente:
                       no duplica transacciones ni dividendos ya existentes.
"""
from __future__ import annotations

import json
from decimal import Decimal, InvalidOperation

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.api.admin_markets import _get_supported_currencies
from app.models import DividendRow, Position, Security, TransactionRow, User
from app.services.backup import ImportResult, build_export, validate_backup

router = APIRouter(prefix="/backup", tags=["backup"])


# ---------------------------------------------------------------------------
#  Export
# ---------------------------------------------------------------------------

def _decimal_default(obj):
    if isinstance(obj, Decimal):
        return str(obj)
    raise TypeError(f"Object of type {type(obj)} is not JSON serializable")


@router.get("/export")
def export_backup(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
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
            "security_name": sec.name,
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

    payload = build_export(positions_data)
    json_bytes = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
    return Response(
        content=json_bytes,
        media_type="application/json",
        headers={
            "Content-Disposition": f'attachment; filename="finanzas_backup_{payload["exported_at"][:10]}.json"'
        },
    )


# ---------------------------------------------------------------------------
#  Import
# ---------------------------------------------------------------------------

@router.post("/import")
async def import_backup(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    try:
        data = await request.json()
    except Exception:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="JSON inválido")

    errors = validate_backup(data)
    if errors:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=errors)

    result = ImportResult()
    valid_currencies = set(_get_supported_currencies(db))

    for pos_data in data.get("positions", []):
        ticker = pos_data.get("security_ticker", "")
        sec = db.scalar(select(Security).where(Security.yahoo_ticker == ticker))
        if sec is None:
            result.positions_skipped += 1
            result.errors.append(f"Valor '{ticker}' no encontrado en el catálogo; se omite.")
            continue

        result.positions_found += 1

        # Obtener o crear la posición
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
            db.flush()  # obtiene pos.id sin commit

        # Transacciones existentes: la clave incluye fecha, tipo, acciones,
        # precio Y comisión. Se usan objetos Decimal (no str) para que dos
        # Decimal iguales pero con distinta representación (p. ej. "10" vs
        # "10.0") se reconozcan como duplicados correctamente.
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
                if tx_data["currency"] not in valid_currencies:
                    raise ValueError(f"currency '{tx_data['currency']}' no está soportada")
                # Coherencia divisa/cambio: USD con rate=1 es incoherente y
                # romperá la carga de la cartera (el repositorio lo rechaza).
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

        # Dividendos existentes: clave con fecha y bruto total (Decimal).
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

    db.commit()
    return result.to_dict()
