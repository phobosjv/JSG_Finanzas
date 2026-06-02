"""
api/csv_import.py
=================
Importación de operaciones de cartera desde un CSV parseado por el frontend.

POST /portfolio/import-csv — recibe una lista de filas (JSON) y crea las
transacciones y dividendos que no existan aún. Idempotente: reutiliza la
misma lógica de deduplicación que backup/import.

El CSV original lo parsea el frontend (sin librerías externas); este endpoint
recibe el resultado ya validado en formato JSON y aplica las validaciones
de negocio: ticker en catálogo, coherencia divisa/exchange_rate, FIFO, etc.
"""
from __future__ import annotations

import csv
import io
from decimal import Decimal

from fastapi import APIRouter, Depends, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.admin_markets import _get_supported_currencies
from app.api.deps import get_current_user, get_db
from app.models import DividendRow, Position, Security, TransactionRow, User
from app.schemas.portfolio import CsvImportBody, CsvImportResult

router = APIRouter(prefix="/portfolio", tags=["portfolio"])

# Columnas del CSV (mismas que la plantilla de importación → round-trip).
_CSV_COLUMNS = [
    "type", "ticker", "date", "shares", "price", "gross_per_share",
    "gross_amount", "fee", "withholding_tax", "currency", "exchange_rate",
]


@router.get("/export-csv")
def export_csv(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    Exporta las operaciones del usuario a CSV, con las mismas columnas que la
    plantilla de importación (round-trip con /portfolio/import-csv).

    Incluye compras, ventas y dividendos. Los traspasos y los planes de
    aportación periódica NO se representan en CSV (formato plano): para fidelidad
    completa se usa el backup JSON.
    """
    positions = db.scalars(
        select(Position).where(Position.user_id == user.id)
    ).all()

    rows: list[dict] = []
    for pos in positions:
        ticker = pos.security.yahoo_ticker
        txs = db.scalars(
            select(TransactionRow)
            .where(TransactionRow.position_id == pos.id)
            .order_by(TransactionRow.date)
        ).all()
        for tx in txs:
            if tx.type not in ("buy", "sell"):
                continue  # transfer_in/out no son representables en CSV
            rows.append({
                "type": tx.type, "ticker": ticker, "date": str(tx.date),
                "shares": str(tx.shares), "price": str(tx.price),
                "gross_per_share": "", "gross_amount": "",
                "fee": str(tx.fee), "withholding_tax": "",
                "currency": tx.currency, "exchange_rate": str(tx.exchange_rate),
            })
        divs = db.scalars(
            select(DividendRow)
            .where(DividendRow.position_id == pos.id)
            .order_by(DividendRow.date)
        ).all()
        for d in divs:
            rows.append({
                "type": "dividend", "ticker": ticker, "date": str(d.date),
                "shares": str(d.shares_at_date), "price": "",
                "gross_per_share": str(d.gross_per_share),
                "gross_amount": str(d.gross_amount),
                "fee": "", "withholding_tax": str(d.withholding_tax),
                "currency": d.currency, "exchange_rate": str(d.exchange_rate),
            })

    # Orden estable por ticker y fecha para un fichero legible.
    rows.sort(key=lambda r: (r["ticker"], r["date"], r["type"]))

    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=_CSV_COLUMNS)
    writer.writeheader()
    writer.writerows(rows)

    from datetime import date as _date
    filename = f"finanzas_operaciones_{_date.today().isoformat()}.csv"
    return Response(
        content=buf.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/import-csv", response_model=CsvImportResult)
def import_csv(
    body: CsvImportBody,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    transactions_added = 0
    dividends_added = 0
    skipped = 0
    errors: list[dict] = []
    valid_currencies = set(_get_supported_currencies(db))

    for idx, row in enumerate(body.rows, start=1):
        ticker = (row.ticker or "").strip().upper()

        # 1. Ticker debe existir en el catálogo
        sec = db.scalar(select(Security).where(Security.yahoo_ticker == ticker))
        if sec is None:
            errors.append({"row": idx, "ticker": ticker,
                           "reason": f"Ticker '{ticker}' no encontrado en el catálogo"})
            continue

        # 2. Obtener o crear la posición del usuario para este valor
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

        # 3. Procesar según tipo
        if row.type in ("buy", "sell"):
            # Validaciones de negocio
            if row.price is None or row.price <= 0:
                errors.append({"row": idx, "ticker": ticker,
                               "reason": "price es obligatorio y debe ser > 0"})
                continue
            if row.shares <= 0:
                errors.append({"row": idx, "ticker": ticker,
                               "reason": "shares debe ser > 0"})
                continue
            if row.fee < 0:
                errors.append({"row": idx, "ticker": ticker,
                               "reason": "fee no puede ser negativo"})
                continue
            if row.currency not in valid_currencies:
                errors.append({"row": idx, "ticker": ticker,
                               "reason": f"divisa '{row.currency}' no soportada"})
                continue
            if row.currency == "EUR" and row.exchange_rate != Decimal("1"):
                errors.append({"row": idx, "ticker": ticker,
                               "reason": "currency='EUR' exige exchange_rate=1"})
                continue
            if row.currency != "EUR" and row.exchange_rate == Decimal("1"):
                errors.append({"row": idx, "ticker": ticker,
                               "reason": f"currency='{row.currency}' requiere exchange_rate distinto de 1"})
                continue

            # Deduplicación: misma clave que backup/import
            existing_txs = {
                (tx.date, tx.type, tx.shares, tx.price, tx.fee)
                for tx in db.scalars(
                    select(TransactionRow).where(TransactionRow.position_id == pos.id)
                ).all()
            }
            key = (row.date, row.type, row.shares, row.price, row.fee)
            if key in existing_txs:
                skipped += 1
                continue

            db.add(TransactionRow(
                position_id=pos.id,
                type=row.type,
                date=row.date,
                shares=row.shares,
                price=row.price,
                fee=row.fee,
                currency=row.currency,
                exchange_rate=row.exchange_rate,
            ))
            transactions_added += 1

        else:  # dividend
            # Validaciones de negocio
            if row.gross_per_share is None or row.gross_per_share <= 0:
                errors.append({"row": idx, "ticker": ticker,
                               "reason": "gross_per_share es obligatorio y debe ser > 0"})
                continue
            if row.shares <= 0:
                errors.append({"row": idx, "ticker": ticker,
                               "reason": "shares (shares_at_date) debe ser > 0"})
                continue
            if row.withholding_tax < 0:
                errors.append({"row": idx, "ticker": ticker,
                               "reason": "withholding_tax no puede ser negativo"})
                continue
            if row.currency not in valid_currencies:
                errors.append({"row": idx, "ticker": ticker,
                               "reason": f"divisa '{row.currency}' no soportada"})
                continue
            if row.currency == "EUR" and row.exchange_rate != Decimal("1"):
                errors.append({"row": idx, "ticker": ticker,
                               "reason": "currency='EUR' exige exchange_rate=1"})
                continue
            if row.currency != "EUR" and row.exchange_rate == Decimal("1"):
                errors.append({"row": idx, "ticker": ticker,
                               "reason": f"currency='{row.currency}' requiere exchange_rate distinto de 1"})
                continue

            # Calcular gross_amount si no se proporcionó
            gross_amount = row.gross_amount if row.gross_amount is not None \
                else row.shares * row.gross_per_share
            if gross_amount <= 0:
                errors.append({"row": idx, "ticker": ticker,
                               "reason": "gross_amount calculado debe ser > 0"})
                continue

            # Deduplicación: misma clave que backup/import
            existing_divs = {
                (div.date, div.gross_amount)
                for div in db.scalars(
                    select(DividendRow).where(DividendRow.position_id == pos.id)
                ).all()
            }
            key = (row.date, gross_amount)
            if key in existing_divs:
                skipped += 1
                continue

            db.add(DividendRow(
                position_id=pos.id,
                date=row.date,
                shares_at_date=row.shares,
                gross_per_share=row.gross_per_share,
                gross_amount=gross_amount,
                withholding_tax=row.withholding_tax,
                currency=row.currency,
                exchange_rate=row.exchange_rate,
            ))
            dividends_added += 1

    db.commit()
    return CsvImportResult(
        transactions_added=transactions_added,
        dividends_added=dividends_added,
        skipped=skipped,
        errors=errors,
    )
