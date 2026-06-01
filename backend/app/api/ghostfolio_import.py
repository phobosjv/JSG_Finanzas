"""
api/ghostfolio_import.py
========================
Importación de exportaciones de Ghostfolio (JSON) para el usuario actual.

POST /portfolio/import-ghostfolio — acepta el fichero JSON exportado desde
Ghostfolio y crea las transacciones y dividendos que no existan aún.

Tipos importados: BUY → buy, SELL → sell, DIVIDEND → dividend.
Tipos ignorados:  FEE, INTEREST, ITEM, LIABILITY (se omiten sin error).

Si la operación es en USD, el tipo de cambio EUR/USD se resuelve
automáticamente desde ecb_rates (fallback: Yahoo Finance).
"""
from __future__ import annotations

import math
from decimal import Decimal, InvalidOperation

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.models import DividendRow, EcbRate, Position, Security, TransactionRow, User
from app.schemas.portfolio import CsvImportResult

router = APIRouter(prefix="/portfolio", tags=["portfolio"])

_IMPORTABLE_TYPES = {"BUY", "SELL", "DIVIDEND"}


def _resolve_exchange_rate(date_str: str, db: Session) -> Decimal | None:
    """Devuelve el tipo EUR/USD para la fecha dada o None si no se encuentra."""
    row = db.scalar(
        select(EcbRate)
        .where(EcbRate.date <= date_str)
        .order_by(EcbRate.date.desc())
        .limit(1)
    )
    if row is not None:
        return row.rate

    # Fallback Yahoo Finance EURUSD=X
    try:
        import yfinance as yf
        from datetime import date as date_type, timedelta
        d = date_type.fromisoformat(date_str)
        df = yf.Ticker("EURUSD=X").history(
            start=d.isoformat(),
            end=(d + timedelta(days=5)).isoformat(),
            auto_adjust=False,
            timeout=5,
        )
        df = df.dropna(subset=["Close"])
        if not df.empty:
            val = float(df["Close"].iloc[0])
            if not math.isnan(val) and val > 0:
                return Decimal(str(round(val, 6)))
    except Exception:
        pass

    return None


@router.post("/import-ghostfolio", response_model=CsvImportResult)
async def import_ghostfolio(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    try:
        data = await request.json()
    except Exception:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="JSON inválido")

    activities = data.get("activities") if isinstance(data, dict) else None
    if not isinstance(activities, list):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Formato no reconocido: falta la clave 'activities' o no es una lista",
        )

    transactions_added = 0
    dividends_added = 0
    skipped = 0
    errors: list[dict] = []

    for idx, act in enumerate(activities, start=1):
        act_type = (act.get("type") or "").upper()

        # Tipos no importables: silenciosamente omitidos (no son errores)
        if act_type not in _IMPORTABLE_TYPES:
            continue

        ticker = (act.get("symbol") or "").strip().upper()
        if not ticker:
            errors.append({"row": idx, "ticker": "?", "reason": "symbol vacío"})
            continue

        # Fecha: recortar la parte de tiempo ISO 8601
        raw_date = act.get("date") or ""
        date_str = raw_date[:10] if len(raw_date) >= 10 else ""
        if not date_str:
            errors.append({"row": idx, "ticker": ticker, "reason": "fecha inválida"})
            continue

        currency = (act.get("currency") or "EUR").upper()
        if currency not in ("EUR", "USD"):
            errors.append({"row": idx, "ticker": ticker,
                           "reason": f"divisa no soportada: {currency}"})
            continue

        # Tipo de cambio
        if currency == "EUR":
            exchange_rate = Decimal("1")
        else:
            rate = _resolve_exchange_rate(date_str, db)
            if rate is None:
                errors.append({"row": idx, "ticker": ticker,
                               "reason": f"no se encontró tipo EUR/USD para {date_str}"})
                continue
            exchange_rate = rate

        # Valores numéricos
        try:
            quantity   = Decimal(str(act.get("quantity") or 0))
            unit_price = Decimal(str(act.get("unitPrice") or 0))
            fee_val    = Decimal(str(act.get("fee") or 0))
            if quantity <= 0:
                raise ValueError("quantity debe ser > 0")
            if unit_price <= 0:
                raise ValueError("unitPrice debe ser > 0")
            if fee_val < 0:
                raise ValueError("fee no puede ser negativo")
        except (InvalidOperation, ValueError) as exc:
            errors.append({"row": idx, "ticker": ticker, "reason": str(exc)})
            continue

        # Buscar security
        sec = db.scalar(select(Security).where(Security.yahoo_ticker == ticker))
        if sec is None:
            errors.append({"row": idx, "ticker": ticker,
                           "reason": f"Ticker '{ticker}' no encontrado en el catálogo"})
            continue

        # Obtener o crear posición
        pos = db.scalar(
            select(Position).where(
                Position.user_id == user.id,
                Position.security_id == sec.id,
            )
        )
        if pos is None:
            pos = Position(user_id=user.id, security_id=sec.id)
            db.add(pos)
            db.flush()

        if act_type in ("BUY", "SELL"):
            existing_txs = {
                (tx.date, tx.type, tx.shares, tx.price, tx.fee)
                for tx in db.scalars(
                    select(TransactionRow).where(TransactionRow.position_id == pos.id)
                ).all()
            }
            tx_type = act_type.lower()
            key = (date_str, tx_type, quantity, unit_price, fee_val)
            if key in existing_txs:
                skipped += 1
                continue
            db.add(TransactionRow(
                position_id=pos.id,
                type=tx_type,
                date=date_str,
                shares=quantity,
                price=unit_price,
                fee=fee_val,
                currency=currency,
                exchange_rate=exchange_rate,
            ))
            transactions_added += 1

        else:  # DIVIDEND
            gross_amount = quantity * unit_price
            existing_divs = {
                (div.date, div.gross_amount)
                for div in db.scalars(
                    select(DividendRow).where(DividendRow.position_id == pos.id)
                ).all()
            }
            key = (date_str, gross_amount)
            if key in existing_divs:
                skipped += 1
                continue
            db.add(DividendRow(
                position_id=pos.id,
                date=date_str,
                shares_at_date=quantity,
                gross_per_share=unit_price,
                gross_amount=gross_amount,
                withholding_tax=fee_val,
                currency=currency,
                exchange_rate=exchange_rate,
            ))
            dividends_added += 1

    db.commit()
    return CsvImportResult(
        transactions_added=transactions_added,
        dividends_added=dividends_added,
        skipped=skipped,
        errors=errors,
    )
