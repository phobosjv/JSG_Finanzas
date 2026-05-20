"""
api/portfolio.py
================
Gestion de posiciones, transacciones y dividendos del usuario.

GET    /portfolio                                     — resumen de cartera (posiciones abiertas).
GET    /portfolio/closed                              — posiciones cerradas (shares == 0).
POST   /portfolio/positions                           — crear posicion para un valor.
GET    /portfolio/{position_id}/transactions          — transacciones.
POST   /portfolio/{position_id}/transactions          — nueva transaccion.
DELETE /portfolio/{position_id}/transactions/{tx_id}  — borrar transaccion.
GET    /portfolio/{position_id}/dividends             — dividendos.
POST   /portfolio/{position_id}/dividends             — nuevo dividendo.
DELETE /portfolio/{position_id}/dividends/{div_id}    — borrar dividendo.
"""

from __future__ import annotations

from datetime import date as date_type
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from collections import defaultdict

from app.models import DividendRow, EcbRate, Position, PriceHistory, PriceSnapshot, Security, TransactionRow, User
from app.repositories.portfolio_repository import PortfolioRepository
from app.schemas.portfolio import (
    ClosedPositionSummary,
    DividendCreate, DividendOut,
    PositionCreate, PositionOut,
    PositionSummary,
    TransactionCreate, TransactionOut,
)
from app.services.calculations import Transaction, compute_position, daily_change, value_position

router = APIRouter(prefix="/portfolio", tags=["portfolio"])


# ---------------------------------------------------------------------------
#  Helper de cálculo compartido
# ---------------------------------------------------------------------------

def _build_position_summary(pos: Position, repo: PortfolioRepository, db) -> PositionSummary | None:
    """
    Construye el PositionSummary para una posición ABIERTA (shares > 0).
    Devuelve None si la posición está cerrada.
    """
    sec: Security = pos.security
    txs  = repo.transactions_for_position(pos.id)
    divs = repo.dividends_for_position(pos.id)
    result = compute_position(txs, divs)

    if result.is_closed:
        return None

    shares = result.current_shares
    avg_cost_eur = result.invested_eur / shares if shares > 0 else Decimal("0")
    cost_eur = result.invested_eur

    snap: PriceSnapshot | None = db.get(PriceSnapshot, sec.id)
    current_price   = snap.last_price       if snap else None
    max_1y          = snap.max_1y           if snap else None

    if sec.currency == "USD":
        rate_row = db.scalar(select(EcbRate).order_by(EcbRate.date.desc()))
        current_rate = rate_row.rate if rate_row else Decimal("1")
    else:
        current_rate = Decimal("1")
    daily_chg_pct   = snap.daily_change_pct if snap else None

    if current_price is None:
        market_value_eur  = Decimal("0")
        unrealized_pnl_eur = Decimal("0")
        unrealized_pnl_pct = Decimal("0")
        daily_chg_eur      = None
    else:
        v = value_position(result, current_price, current_rate)
        market_value_eur   = v["market_value_eur"]
        unrealized_pnl_eur = v["unrealized_gain_eur"]
        unrealized_pnl_pct = v["unrealized_gain_pct"]

        if snap and snap.prev_close:
            dc = daily_change(shares, current_price, snap.prev_close, current_rate)
            daily_chg_eur = dc["daily_change_eur"]
        else:
            daily_chg_eur = None

    dividends_eur    = result.dividends_net_eur
    realized_pnl_eur = result.realized_gain_eur
    total_profit_eur = unrealized_pnl_eur + realized_pnl_eur + dividends_eur
    fees_eur         = sum((tx.fee / tx.exchange_rate for tx in txs), Decimal("0"))

    return PositionSummary(
        position_id=pos.id,
        security_id=sec.id,
        yahoo_ticker=sec.yahoo_ticker,
        name=sec.name,
        currency=sec.currency,
        shares=shares,
        avg_cost_eur=avg_cost_eur,
        cost_eur=cost_eur,
        current_price=current_price,
        market_value_eur=market_value_eur,
        unrealized_pnl_eur=unrealized_pnl_eur,
        unrealized_pnl_pct=unrealized_pnl_pct,
        daily_change_pct=daily_chg_pct,
        daily_change_eur=daily_chg_eur,
        dividends_eur=dividends_eur,
        realized_pnl_eur=realized_pnl_eur,
        total_profit_eur=total_profit_eur,
        fees_eur=fees_eur,
        target_sell_price=pos.target_sell_price,
        max_1y=max_1y,
        notes=pos.notes,
    )


# ---------------------------------------------------------------------------
#  Crear posición
# ---------------------------------------------------------------------------

@router.post("/positions", response_model=PositionOut, status_code=status.HTTP_201_CREATED)
def create_position(
    body: PositionCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Crea una posición para el usuario. Si ya existe, la devuelve (idempotente)."""
    if db.get(Security, body.security_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Valor no encontrado")

    existing = db.scalar(
        select(Position).where(
            Position.user_id == user.id,
            Position.security_id == body.security_id,
        )
    )
    if existing:
        return existing

    pos = Position(
        user_id=user.id,
        security_id=body.security_id,
        target_sell_price=body.target_sell_price,
        notes=body.notes,
    )
    db.add(pos)
    db.commit()
    db.refresh(pos)
    return pos


# ---------------------------------------------------------------------------
#  Resumen de cartera — posiciones abiertas
# ---------------------------------------------------------------------------

@router.get("", response_model=list[PositionSummary])
def get_portfolio(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    positions = db.scalars(
        select(Position).where(Position.user_id == user.id)
    ).all()
    repo = PortfolioRepository(db)
    result = []
    for pos in positions:
        summary = _build_position_summary(pos, repo, db)
        if summary is not None:
            result.append(summary)
    return result


# ---------------------------------------------------------------------------
#  Historial de valor de cartera (para gráfico de líneas en Portfolio)
# ---------------------------------------------------------------------------

@router.get("/history")
def get_portfolio_history(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    Valor histórico aproximado de la cartera (posiciones abiertas).
    Usa las acciones actuales para cada fecha histórica — no recalcula la
    composición en cada momento, por lo que es una aproximación válida para
    mostrar la tendencia del valor.
    """
    positions = db.scalars(
        select(Position).where(Position.user_id == user.id)
    ).all()
    repo = PortfolioRepository(db)

    open_pos: list[tuple[Security, Decimal, str]] = []
    for pos in positions:
        txs  = repo.transactions_for_position(pos.id)
        divs = repo.dividends_for_position(pos.id)
        result = compute_position(txs, divs)
        if not result.is_closed:
            first_buy = min(
                (tx.date.isoformat() for tx in txs if tx.type == "buy"),
                default=None,
            )
            open_pos.append((pos.security, result.current_shares, first_buy))

    if not open_pos:
        return []

    rate_row = db.scalar(select(EcbRate).order_by(EcbRate.date.desc()))
    current_rate = rate_row.rate if rate_row else Decimal("1")

    date_totals: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))

    for sec, shares, first_buy in open_pos:
        rate = current_rate if sec.currency == "USD" else Decimal("1")
        query = select(PriceHistory).where(PriceHistory.security_id == sec.id)
        if first_buy:
            query = query.where(PriceHistory.date >= first_buy)
        rows = db.scalars(query.order_by(PriceHistory.date)).all()
        for row in rows:
            date_totals[row.date] += shares * row.close / rate

    return [
        {"date": d, "value": float(date_totals[d])}
        for d in sorted(date_totals)
    ]


# ---------------------------------------------------------------------------
#  Resumen de una posición por security_id (para SecurityDetail)
# ---------------------------------------------------------------------------

@router.get("/by-security/{security_id}", response_model=PositionSummary | None)
def get_position_by_security(
    security_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    Devuelve el PositionSummary de la posición ABIERTA del usuario para ese valor,
    o null si no existe o está cerrada. Evita cargar toda la cartera en SecurityDetail.
    """
    pos = db.scalar(
        select(Position).where(
            Position.user_id == user.id,
            Position.security_id == security_id,
        )
    )
    if pos is None:
        return None
    repo = PortfolioRepository(db)
    return _build_position_summary(pos, repo, db)


# ---------------------------------------------------------------------------
#  Posiciones cerradas
# ---------------------------------------------------------------------------

@router.get("/closed", response_model=list[ClosedPositionSummary])
def get_closed_positions(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    positions = db.scalars(
        select(Position).where(Position.user_id == user.id)
    ).all()
    repo = PortfolioRepository(db)
    result = []

    for pos in positions:
        sec: Security = pos.security
        txs  = repo.transactions_for_position(pos.id)
        divs = repo.dividends_for_position(pos.id)
        if not txs:
            continue
        computed = compute_position(txs, divs)
        if not computed.is_closed:
            continue

        shares_sold = sum(
            (tx.shares for tx in txs if tx.type == "sell"), Decimal("0")
        )
        cost_eur     = sum((m.cost_eur     for m in computed.sale_matches), Decimal("0"))
        proceeds_eur = sum((m.proceeds_eur for m in computed.sale_matches), Decimal("0"))

        fees_eur = sum((tx.fee / tx.exchange_rate for tx in txs), Decimal("0"))

        result.append(ClosedPositionSummary(
            position_id=pos.id,
            security_id=sec.id,
            yahoo_ticker=sec.yahoo_ticker,
            name=sec.name,
            shares_sold=shares_sold,
            cost_eur=cost_eur,
            proceeds_eur=proceeds_eur,
            realized_pnl_eur=computed.realized_gain_eur,
            dividends_eur=computed.dividends_net_eur,
            total_profit_eur=computed.realized_gain_eur + computed.dividends_net_eur,
            fees_eur=fees_eur,
        ))

    return result


# ---------------------------------------------------------------------------
#  Precio objetivo de venta (PATCH)
# ---------------------------------------------------------------------------

@router.patch("/{position_id}/notes", response_model=PositionOut)
def update_notes(
    position_id: int,
    body: dict,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    pos = _require_position(db, position_id, user.id)
    pos.notes = body.get("notes") or None
    db.commit()
    db.refresh(pos)
    return pos


@router.patch("/{position_id}/target-sell", response_model=PositionOut)
def update_target_sell(
    position_id: int,
    body: dict,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    pos = _require_position(db, position_id, user.id)
    price = body.get("target_sell_price")
    pos.target_sell_price = Decimal(str(price)) if price is not None else None
    db.commit()
    db.refresh(pos)
    return pos


# ---------------------------------------------------------------------------
#  Transacciones
# ---------------------------------------------------------------------------

@router.get("/{position_id}/transactions", response_model=list[TransactionOut])
def list_transactions(
    position_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _require_position(db, position_id, user.id)
    rows = db.scalars(
        select(TransactionRow)
        .where(TransactionRow.position_id == position_id)
        .order_by(TransactionRow.date)
    ).all()
    return rows


@router.post(
    "/{position_id}/transactions",
    response_model=TransactionOut,
    status_code=status.HTTP_201_CREATED,
)
def add_transaction(
    position_id: int,
    body: TransactionCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _require_position(db, position_id, user.id)

    if body.type == "sell":
        repo = PortfolioRepository(db)
        existing_txs = repo.transactions_for_position(position_id)
        new_tx = Transaction(
            type="sell",
            date=date_type.fromisoformat(body.date),
            shares=body.shares,
            price=body.price,
            fee=body.fee,
            exchange_rate=body.exchange_rate,
        )
        try:
            compute_position(existing_txs + [new_tx], [])
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc))

    row = TransactionRow(position_id=position_id, **body.model_dump())
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@router.patch(
    "/{position_id}/transactions/{tx_id}",
    response_model=TransactionOut,
)
def update_transaction(
    position_id: int,
    tx_id: int,
    body: TransactionCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _require_position(db, position_id, user.id)
    tx = db.scalar(
        select(TransactionRow).where(
            TransactionRow.id == tx_id,
            TransactionRow.position_id == position_id,
        )
    )
    if tx is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No encontrado")

    # Validar que la posición sigue siendo coherente con esta transacción editada.
    # Se consultan TransactionRow (tienen .id) en lugar de usar el repositorio,
    # que devuelve Transaction (dataclass puro, sin .id).
    if body.type == "sell":
        other_rows = db.scalars(
            select(TransactionRow).where(
                TransactionRow.position_id == position_id,
                TransactionRow.id != tx_id,
            )
        ).all()
        other_txs = [
            Transaction(
                type=r.type,
                date=date_type.fromisoformat(r.date),
                shares=r.shares,
                price=r.price,
                fee=r.fee,
                exchange_rate=r.exchange_rate,
            )
            for r in other_rows
        ]
        new_tx = Transaction(
            type="sell",
            date=date_type.fromisoformat(body.date),
            shares=body.shares,
            price=body.price,
            fee=body.fee,
            exchange_rate=body.exchange_rate,
        )
        try:
            compute_position(other_txs + [new_tx], [])
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc))

    for field, value in body.model_dump().items():
        setattr(tx, field, value)
    db.commit()
    db.refresh(tx)
    return tx


@router.delete(
    "/{position_id}/transactions/{tx_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_transaction(
    position_id: int,
    tx_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _require_position(db, position_id, user.id)
    tx = db.scalar(
        select(TransactionRow).where(
            TransactionRow.id == tx_id,
            TransactionRow.position_id == position_id,
        )
    )
    if tx is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No encontrado")
    db.delete(tx)
    db.commit()


# ---------------------------------------------------------------------------
#  Dividendos
# ---------------------------------------------------------------------------

@router.get("/{position_id}/dividends", response_model=list[DividendOut])
def list_dividends(
    position_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _require_position(db, position_id, user.id)
    rows = db.scalars(
        select(DividendRow)
        .where(DividendRow.position_id == position_id)
        .order_by(DividendRow.date)
    ).all()
    return rows


@router.post(
    "/{position_id}/dividends",
    response_model=DividendOut,
    status_code=status.HTTP_201_CREATED,
)
def add_dividend(
    position_id: int,
    body: DividendCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _require_position(db, position_id, user.id)
    row = DividendRow(position_id=position_id, **body.model_dump())
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@router.patch(
    "/{position_id}/dividends/{div_id}",
    response_model=DividendOut,
)
def update_dividend(
    position_id: int,
    div_id: int,
    body: DividendCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _require_position(db, position_id, user.id)
    div = db.scalar(
        select(DividendRow).where(
            DividendRow.id == div_id,
            DividendRow.position_id == position_id,
        )
    )
    if div is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No encontrado")
    for field, value in body.model_dump().items():
        setattr(div, field, value)
    db.commit()
    db.refresh(div)
    return div


@router.delete(
    "/{position_id}/dividends/{div_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_dividend(
    position_id: int,
    div_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _require_position(db, position_id, user.id)
    div = db.scalar(
        select(DividendRow).where(
            DividendRow.id == div_id,
            DividendRow.position_id == position_id,
        )
    )
    if div is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No encontrado")
    db.delete(div)
    db.commit()


# ---------------------------------------------------------------------------
#  Helper
# ---------------------------------------------------------------------------

def _require_position(db: Session, position_id: int, user_id: int) -> Position:
    pos = db.scalar(
        select(Position).where(
            Position.id == position_id,
            Position.user_id == user_id,
        )
    )
    if pos is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Posicion no encontrada")
    return pos
