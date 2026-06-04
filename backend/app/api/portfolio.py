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
POST   /portfolio/{position_id}/recurring-buys        — serie de aportaciones periodicas (DCA).
POST   /portfolio/transfer                            — traspaso de fondos (fiscalmente neutro).
DELETE /portfolio/transfer/{group_id}                 — deshacer un traspaso (borra la pareja).
GET    /portfolio/{position_id}/dividends             — dividendos.
POST   /portfolio/{position_id}/dividends             — nuevo dividendo.
DELETE /portfolio/{position_id}/dividends/{div_id}    — borrar dividendo.
"""

from __future__ import annotations

import uuid
from datetime import date as date_type, timedelta
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from collections import defaultdict

from app.models import DividendRow, EcbRate, Position, PriceHistory, PriceSnapshot, RecurringPlanRow, Security, SecuritySplit, TransactionRow, User
from app.repositories.portfolio_repository import PortfolioRepository
from app.repositories.exchange_rates import latest_rate, rate_on_date
from app.models.market import MarketRow
from app.schemas.portfolio import (
    ClosedPositionAnalytics,
    ClosedPositionSummary,
    DividendCreate, DividendOut,
    NotesUpdate, TargetSellUpdate,
    PositionCreate, PositionOut,
    PositionSummary,
    RecurringBuyCreate, RecurringBuyResult, RecurringPlanOut, SkippedContribution,
    SecurityDividendSummary,
    TransactionCreate, TransactionOut,
    TransferCreate, TransferResult,
)
from app.services.calculations import (
    Transaction, compute_position, consumed_cost_fifo, daily_change,
    normalize_splits, value_position,
)
from app.services.recurring import contribution_dates_until, nth_contribution_date
from app.services.returns import xirr, modified_dietz

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
    txs    = repo.transactions_for_position(pos.id)
    divs   = repo.dividends_for_position(pos.id)
    splits = repo.splits_for_security(sec.id)
    result = compute_position(txs, divs, splits)

    if result.is_closed:
        return None

    shares = result.current_shares
    avg_cost_eur = result.invested_eur / shares if shares > 0 else Decimal("0")
    cost_eur = result.invested_eur

    snap: PriceSnapshot | None = db.get(PriceSnapshot, sec.id)
    current_price   = snap.last_price       if snap else None
    max_1y          = snap.max_1y           if snap else None

    current_rate = latest_rate(db, sec.currency)
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

        if snap and snap.prev_close is not None:
            dc = daily_change(shares, current_price, snap.prev_close, current_rate)
            daily_chg_eur = dc["daily_change_eur"]
        else:
            daily_chg_eur = None

    dividends_eur    = result.dividends_net_eur
    realized_pnl_eur = result.realized_gain_eur
    total_profit_eur = unrealized_pnl_eur + realized_pnl_eur + dividends_eur
    fees_eur         = sum((tx.fee / tx.exchange_rate for tx in txs), Decimal("0"))

    # Valor de MERCADO en el momento de cada traspaso de ENTRADA: participaciones
    # recibidas × NAV de esa fecha. Permite mostrar la rentabilidad "desde el
    # traspaso" (rendimiento propio del fondo), distinta del coste heredado.
    norm_txs = normalize_splits(txs, splits) if splits else txs
    transfer_ins = [t for t in norm_txs if t.type == "transfer_in"]
    transfer_in_market_eur = None
    if transfer_ins:
        total_ti = Decimal("0")
        for t in transfer_ins:
            d_str = t.date.isoformat()
            ph = db.scalar(
                select(PriceHistory)
                .where(PriceHistory.security_id == sec.id, PriceHistory.date <= d_str)
                .order_by(PriceHistory.date.desc())
            )
            if ph is None or ph.close <= Decimal("0"):
                continue
            total_ti += t.shares * ph.close / rate_on_date(db, sec.currency, d_str)
        transfer_in_market_eur = total_ti

    market_row = db.get(MarketRow, sec.market)
    return PositionSummary(
        position_id=pos.id,
        security_id=sec.id,
        yahoo_ticker=sec.yahoo_ticker,
        name=sec.name,
        currency=sec.currency,
        market_code=sec.market,
        market_type=market_row.market_type if market_row else "stock",
        is_fund_market=market_row.is_fund_market if market_row else False,
        has_sells=any(tx.type == "sell" for tx in txs),
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
        transfer_in_market_eur=transfer_in_market_eur,
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
#  Traspaso de fondos (fiscalmente neutro)
# ---------------------------------------------------------------------------

def _is_fund_security(db: Session, security: Security) -> bool:
    """True si el valor pertenece a un mercado marcado como mercado de fondos."""
    market = db.get(MarketRow, security.market)
    return bool(market and market.is_fund_market)


@router.post("/transfer", response_model=TransferResult, status_code=status.HTTP_201_CREATED)
def create_transfer(
    body: TransferCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    Registra un traspaso entre fondos: consume 'shares' del origen (transfer_out,
    sin resultado fiscal) y crea 'dest_shares' en el destino (transfer_in) con el
    COSTE HEREDADO calculado por FIFO. La plusvalía latente se difiere hasta el
    reembolso final, conforme al régimen español de traspasos de fondos.
    """
    origin = _require_position(db, body.origin_position_id, user.id)
    origin_sec = db.get(Security, origin.security_id)
    dest_sec = db.get(Security, body.dest_security_id)
    if dest_sec is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Fondo de destino no encontrado")

    # Ambos extremos deben ser fondos: el traspaso es un régimen específico de fondos.
    if not _is_fund_security(db, origin_sec):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="El valor de origen no pertenece a un mercado de fondos.",
        )
    if not _is_fund_security(db, dest_sec):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="El valor de destino no pertenece a un mercado de fondos.",
        )
    if origin.security_id == body.dest_security_id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="El fondo de origen y el de destino no pueden ser el mismo.",
        )

    transfer_date = date_type.fromisoformat(body.date)

    # Coste heredado: estado FIFO del origen con las transacciones hasta la fecha
    # del traspaso (inclusive). Se consumen 'shares' de la cola para sumar su coste.
    repo = PortfolioRepository(db)
    splits = repo.splits_for_security(origin.security_id)
    origin_txs = [
        t for t in repo.transactions_for_position(origin.id)
        if t.date <= transfer_date
    ]
    origin_state = compute_position(origin_txs, [], splits)
    try:
        _, inherited_cost_eur = consumed_cost_fifo(origin_state.open_lots, body.shares)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc))

    # Identificador único que vincula las dos filas del traspaso para deshacerlo.
    group_id = uuid.uuid4().hex

    # transfer_out en el origen (precio informativo = coste heredado por participación)
    out_price = inherited_cost_eur / body.shares
    out_row = TransactionRow(
        position_id=origin.id,
        type="transfer_out",
        date=body.date,
        shares=body.shares,
        price=out_price,
        fee=Decimal("0"),
        currency="EUR",
        exchange_rate=Decimal("1"),
        transfer_group_id=group_id,
    )

    # Posición de destino (crear si no existe)
    dest_pos = db.scalar(
        select(Position).where(
            Position.user_id == user.id,
            Position.security_id == body.dest_security_id,
        )
    )
    if dest_pos is None:
        dest_pos = Position(user_id=user.id, security_id=body.dest_security_id)
        db.add(dest_pos)
        db.flush()  # para disponer de dest_pos.id

    # transfer_in en el destino con precio sintético que codifica el coste heredado
    in_price = inherited_cost_eur / body.dest_shares
    in_row = TransactionRow(
        position_id=dest_pos.id,
        type="transfer_in",
        date=body.date,
        shares=body.dest_shares,
        price=in_price,
        fee=Decimal("0"),
        currency="EUR",
        exchange_rate=Decimal("1"),
        transfer_group_id=group_id,
    )

    db.add(out_row)
    db.add(in_row)
    db.commit()
    db.refresh(out_row)
    db.refresh(in_row)

    return TransferResult(
        origin_position_id=origin.id,
        dest_position_id=dest_pos.id,
        transfer_out_id=out_row.id,
        transfer_in_id=in_row.id,
        inherited_cost_eur=inherited_cost_eur,
        transfer_group_id=group_id,
    )


@router.delete("/transfer/{group_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_transfer(
    group_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    Deshace un traspaso: borra ATÓMICAMENTE las dos filas acopladas
    (transfer_out en el origen + transfer_in en el destino) que comparten el
    'transfer_group_id'.

    Antes de borrar valida que la eliminación no deja transacciones
    posteriores sin respaldo en NINGUNA de las dos posiciones afectadas: si el
    fondo de destino ya reembolsó o volvió a traspasar las participaciones
    heredadas, deshacer el traspaso dejaría esas ventas sin lotes y se rechaza
    con 422.
    """
    rows = db.scalars(
        select(TransactionRow)
        .join(Position, TransactionRow.position_id == Position.id)
        .where(
            TransactionRow.transfer_group_id == group_id,
            Position.user_id == user.id,
        )
    ).all()
    if not rows:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Traspaso no encontrado")

    ids_to_delete = {r.id for r in rows}
    affected_positions = {r.position_id for r in rows}

    # Validar cada posición afectada con las transacciones que QUEDARÍAN.
    repo = PortfolioRepository(db)
    for pos_id in affected_positions:
        sec_id = db.get(Position, pos_id).security_id
        splits = repo.splits_for_security(sec_id)
        remaining_rows = db.scalars(
            select(TransactionRow).where(
                TransactionRow.position_id == pos_id,
                TransactionRow.id.notin_(ids_to_delete),
            )
        ).all()
        remaining = [
            Transaction(
                type=r.type,
                date=date_type.fromisoformat(r.date),
                shares=r.shares,
                price=r.price,
                fee=r.fee,
                exchange_rate=r.exchange_rate,
            )
            for r in remaining_rows
        ]
        try:
            compute_position(remaining, [], splits)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=(
                    "No se puede deshacer el traspaso: dejaría operaciones "
                    f"posteriores sin participaciones que las respalden ({exc})."
                ),
            )

    for r in rows:
        db.delete(r)
    db.commit()


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

def _history_series(
    db: Session, user_id: int, selected_types: set[str] | None,
) -> list[dict]:
    """
    Serie diaria de valor de cartera en EUR (reconstruida transacción a
    transacción). Reutilizada por el gráfico de historial y por los retornos
    por periodo. 'selected_types' filtra por tipo de producto (None = todo).
    """
    positions = db.scalars(
        select(Position).where(Position.user_id == user_id)
    ).all()
    market_types: dict[str, str] = {
        m.code: m.market_type for m in db.scalars(select(MarketRow)).all()
    }

    # Para cada posición recopilamos su línea temporal de participaciones
    # (transacciones) y de precios (cierres). Después valoramos CADA posición en
    # CADA fecha del eje global usando su último cierre conocido (carry-forward).
    #
    # Antes se sumaba el valor de una posición SOLO en las fechas con cotización
    # propia: si en una fecha del eje (p. ej. el último día) ese valor no tenía
    # registro de precio —algo habitual entre fondos (NAV) y acciones, o por
    # festivos desalineados— quedaba fuera del total. Eso infravaloraba la
    # cartera (sobre todo el último punto, v_end) y disparaba los retornos por
    # periodo a valores imposibles (Modified Dietz con numerador negativo).
    sec_series: list[tuple[Decimal, list, list, list[tuple[str, Decimal]]]] = []
    all_dates: set[str] = set()

    for pos in positions:
        sec: Security = pos.security
        if selected_types is not None and market_types.get(sec.market, "stock") not in selected_types:
            continue
        rate = latest_rate(db, sec.currency)

        tx_rows = db.scalars(
            select(TransactionRow)
            .where(TransactionRow.position_id == pos.id)
            .order_by(TransactionRow.date)
        ).all()
        if not tx_rows:
            continue
        first_buy_date = next(
            (tx.date for tx in tx_rows if tx.type in ("buy", "transfer_in")), None
        )
        if not first_buy_date:
            continue

        price_rows = db.scalars(
            select(PriceHistory)
            .where(PriceHistory.security_id == sec.id, PriceHistory.date >= first_buy_date)
            .order_by(PriceHistory.date)
        ).all()
        if not price_rows:
            continue

        split_rows = db.scalars(
            select(SecuritySplit)
            .where(SecuritySplit.security_id == sec.id)
            .order_by(SecuritySplit.ex_date)
        ).all()

        prices = [(p.date, p.close) for p in price_rows]
        sec_series.append((rate, list(tx_rows), list(split_rows), prices))
        all_dates.update(d for d, _ in prices)

    if not all_dates:
        return []

    axis = sorted(all_dates)
    date_totals: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))

    for rate, tx_rows, split_rows, prices in sec_series:

        def _adj_shares(tx_date_str: str, raw: Decimal) -> Decimal:
            result = raw
            for sp in split_rows:
                if sp.ex_date > tx_date_str:
                    result *= Decimal(sp.ratio_num) / Decimal(sp.ratio_den)
            return result

        running_shares = Decimal("0")
        tx_idx = 0
        n_tx = len(tx_rows)
        price_idx = 0
        n_p = len(prices)
        last_close: Decimal | None = None

        # Dos punteros sobre el eje global: uno para participaciones (tx) y otro
        # para el último cierre conocido (carry-forward).
        for d in axis:
            while tx_idx < n_tx and tx_rows[tx_idx].date <= d:
                tx = tx_rows[tx_idx]
                adj = _adj_shares(tx.date, tx.shares)
                running_shares += adj if tx.type in ("buy", "transfer_in") else -adj
                tx_idx += 1
            while price_idx < n_p and prices[price_idx][0] <= d:
                last_close = prices[price_idx][1]
                price_idx += 1
            if last_close is not None and running_shares > Decimal("0"):
                date_totals[d] += running_shares * last_close / rate

    return [{"date": d, "value": float(date_totals[d])} for d in sorted(date_totals)]


@router.get("/history")
def get_portfolio_history(
    types: str | None = Query(None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    Valor histórico de la cartera reconstruido transacción a transacción.

    'types' (opcional): lista separada por comas de tipos de producto
    (stock,fund,etf,crypto) para segmentar el histórico por tipo.
    """
    selected = {t.strip() for t in types.split(",") if t.strip()} if types else None
    return _history_series(db, user.id, selected)


def _portfolio_flows(db: Session, user_id: int, selected_types: set[str] | None) -> list[tuple[date_type, float]]:
    """
    Flujos de caja reales de la cartera (para retornos por periodo): compras
    (+ aportación), ventas (− retirada) y dividendos (− retirada), en EUR. Los
    traspasos no son flujos. Filtra por tipo de producto si se indica.
    """
    market_types = {m.code: m.market_type for m in db.scalars(select(MarketRow)).all()}
    flows: list[tuple[date_type, float]] = []
    for pos in db.scalars(select(Position).where(Position.user_id == user_id)).all():
        sec: Security = pos.security
        if selected_types is not None and market_types.get(sec.market, "stock") not in selected_types:
            continue
        for tx in db.scalars(select(TransactionRow).where(TransactionRow.position_id == pos.id)).all():
            d = date_type.fromisoformat(tx.date)
            if tx.type == "buy":
                flows.append((d, float((tx.shares * tx.price + tx.fee) / tx.exchange_rate)))
            elif tx.type == "sell":
                flows.append((d, -float((tx.shares * tx.price - tx.fee) / tx.exchange_rate)))
        for div in db.scalars(select(DividendRow).where(DividendRow.position_id == pos.id)).all():
            d = date_type.fromisoformat(div.date)
            flows.append((d, -float((div.gross_amount - div.withholding_tax) / div.exchange_rate)))
    return flows


@router.get("/period-returns")
def get_period_returns(
    types: str | None = Query(None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    Rentabilidad por periodo (YTD, 1 año, 3 años, total) mediante Modified Dietz:
    rentabilidad acumulada del periodo ajustada por el momento de las
    aportaciones/retiradas. Cada valor es un % o null si no es calculable.
    Respeta el segmentador por tipo ('types').
    """
    selected = {t.strip() for t in types.split(",") if t.strip()} if types else None
    series = _history_series(db, user.id, selected)
    if not series:
        return {"ytd": None, "y1": None, "y3": None, "total": None}

    flows = _portfolio_flows(db, user.id, selected)
    today = date_type.today()
    v_end = series[-1]["value"]
    end_date = date_type.fromisoformat(series[-1]["date"])
    first_date = date_type.fromisoformat(series[0]["date"])

    starts = {
        "ytd":   date_type(today.year, 1, 1),
        "y1":    today - timedelta(days=365),
        "y3":    today - timedelta(days=3 * 365),
        "total": None,
    }

    def _period(start: date_type | None):
        # Valor y fecha de inicio: último punto de la serie con fecha <= start.
        # 'inclusive' es True cuando v_start es sintético (0): el periodo arranca
        # antes de cualquier inversión, así que los flujos DE la fecha de inicio
        # (las primeras compras) sí cuentan. Si v_start viene de la serie, ya
        # incluye las operaciones de ese día → se excluyen (estricto).
        if start is None:
            v_start, start_actual, inclusive = 0.0, first_date, True
        else:
            start_str = start.isoformat()
            prior = [p for p in series if p["date"] <= start_str]
            if prior:
                v_start = prior[-1]["value"]
                start_actual = date_type.fromisoformat(prior[-1]["date"])
                inclusive = False
            else:
                v_start, start_actual, inclusive = 0.0, first_date, True
        days = (end_date - start_actual).days
        if days <= 0:
            return None
        period_flows = [
            ((days - (d - start_actual).days) / days, amt)
            for d, amt in flows
            if (start_actual <= d if inclusive else start_actual < d) and d <= end_date
        ]
        r = modified_dietz(v_start, v_end, period_flows)
        return round(r * 100, 2) if r is not None else None

    return {k: _period(v) for k, v in starts.items()}


# ---------------------------------------------------------------------------
#  Rentabilidad anualizada ponderada por dinero (TIR / XIRR)
# ---------------------------------------------------------------------------

@router.get("/xirr")
def get_portfolio_xirr(
    types: str | None = Query(None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    TIR (XIRR) de la cartera: rentabilidad anual ponderada por dinero, sobre
    TODOS los flujos reales (compras = salida, ventas y dividendos = entrada) más
    el valor de mercado actual como flujo final. Los traspasos no son flujos.

    'types' (opcional): segmenta por tipo de producto (igual que /history).
    Devuelve {xirr_pct, cashflows, market_value_eur} (xirr_pct null si no es
    resoluble: sin operaciones, todo del mismo signo o un solo día).
    """
    selected_types: set[str] | None = None
    if types:
        selected_types = {t.strip() for t in types.split(",") if t.strip()}
    market_types: dict[str, str] = {
        m.code: m.market_type for m in db.scalars(select(MarketRow)).all()
    }

    positions = db.scalars(
        select(Position).where(Position.user_id == user.id)
    ).all()
    repo = PortfolioRepository(db)

    cashflows: list[tuple[date_type, float]] = []
    terminal = Decimal("0")

    for pos in positions:
        sec: Security = pos.security
        if selected_types is not None and market_types.get(sec.market, "stock") not in selected_types:
            continue

        # Flujos reales (importes en EUR con el tipo de cada operación).
        for tx in db.scalars(
            select(TransactionRow).where(TransactionRow.position_id == pos.id)
        ).all():
            d = date_type.fromisoformat(tx.date)
            if tx.type == "buy":
                cashflows.append((d, -float((tx.shares * tx.price + tx.fee) / tx.exchange_rate)))
            elif tx.type == "sell":
                cashflows.append((d, float((tx.shares * tx.price - tx.fee) / tx.exchange_rate)))
            # transfer_in / transfer_out: no son flujos de caja.
        for div in db.scalars(
            select(DividendRow).where(DividendRow.position_id == pos.id)
        ).all():
            d = date_type.fromisoformat(div.date)
            cashflows.append((d, float((div.gross_amount - div.withholding_tax) / div.exchange_rate)))

        # Valor de mercado actual de la posición (si sigue abierta).
        summary = _build_position_summary(pos, repo, db)
        if summary is not None:
            terminal += summary.market_value_eur

    if terminal > Decimal("0"):
        cashflows.append((date_type.today(), float(terminal)))

    rate = xirr(cashflows)
    return {
        "xirr_pct": round(rate * 100, 2) if rate is not None else None,
        "cashflows": len(cashflows),
        "market_value_eur": float(terminal),
    }


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


@router.get("/by-security/{security_id}/operations")
def get_operations_by_security(
    security_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    Operaciones (transacciones + dividendos) del usuario para un valor, exista o
    no posición ABIERTA. Permite ver el historial completo aunque la posición
    esté CERRADA (vendida o traspasada del todo). 404 si nunca hubo posición.
    """
    pos = db.scalar(
        select(Position).where(
            Position.user_id == user.id,
            Position.security_id == security_id,
        )
    )
    if pos is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sin posición para este valor")
    txs = db.scalars(
        select(TransactionRow).where(TransactionRow.position_id == pos.id).order_by(TransactionRow.date)
    ).all()
    divs = db.scalars(
        select(DividendRow).where(DividendRow.position_id == pos.id).order_by(DividendRow.date)
    ).all()
    return {
        "position_id": pos.id,
        "transactions": [TransactionOut.model_validate(t) for t in txs],
        "dividends": [DividendOut.model_validate(d) for d in divs],
    }


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
    market_types: dict[str, str] = {
        m.code: m.market_type for m in db.scalars(select(MarketRow)).all()
    }
    result = []

    for pos in positions:
        sec: Security = pos.security
        txs    = repo.transactions_for_position(pos.id)
        divs   = repo.dividends_for_position(pos.id)
        if not txs:
            continue
        splits = repo.splits_for_security(sec.id)
        computed = compute_position(txs, divs, splits)
        if not computed.is_closed:
            continue
        # Una posición cerrada SIN sale_matches lo está por un traspaso íntegro
        # (transfer_out), no por una venta. No es un reembolso: su valor se
        # difirió al fondo de destino. No debe figurar como posición cerrada
        # (evita filas fantasma con todo a cero). Coherente con closed-analytics.
        if not computed.sale_matches:
            continue

        # shares_sold se obtiene de computed.sale_matches (ya normalizadas a
        # equivalente post-split por _normalize_splits) en lugar de las
        # transacciones crudas. Así la cifra es coherente con el precio medio
        # y el coste que también vienen del cálculo FIFO normalizado.
        shares_sold  = sum((m.shares       for m in computed.sale_matches), Decimal("0"))
        cost_eur     = sum((m.cost_eur     for m in computed.sale_matches), Decimal("0"))
        proceeds_eur = sum((m.proceeds_eur for m in computed.sale_matches), Decimal("0"))

        fees_eur = sum((tx.fee / tx.exchange_rate for tx in txs), Decimal("0"))

        result.append(ClosedPositionSummary(
            position_id=pos.id,
            security_id=sec.id,
            yahoo_ticker=sec.yahoo_ticker,
            name=sec.name,
            market_code=sec.market,
            market_type=market_types.get(sec.market, "stock"),
            is_fund_market=market_types.get(sec.market) == "fund",
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
#  Posiciones cerradas enriquecidas (para scatter plot)
# ---------------------------------------------------------------------------

@router.get("/closed-analytics", response_model=list[ClosedPositionAnalytics])
def get_closed_analytics(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    Como /closed pero añade avg_days_held (media ponderada por lote FIFO) y pnl_pct.
    Usado por el scatter plot de posiciones cerradas en Portfolio.

    Incluye también los round-trips YA realizados de posiciones que siguen
    ABIERTAS (ventas parciales pasadas): cada punto representa la parte vendida
    (sale_matches). Esos puntos se marcan con `still_open=True` para que el
    frontend pueda distinguirlos. Para los abiertos no se atribuyen dividendos
    al round-trip parcial (no es posible repartirlos limpiamente entre lo
    vendido y lo que se conserva), así que `dividends_eur=0`.
    """
    positions = db.scalars(
        select(Position).where(Position.user_id == user.id)
    ).all()
    repo = PortfolioRepository(db)
    market_types: dict[str, str] = {
        m.code: m.market_type for m in db.scalars(select(MarketRow)).all()
    }
    result = []

    for pos in positions:
        sec: Security = pos.security
        txs    = repo.transactions_for_position(pos.id)
        divs   = repo.dividends_for_position(pos.id)
        splits = repo.splits_for_security(sec.id)
        computed = compute_position(txs, divs, splits)

        # Antes solo se incluían las posiciones cerradas. Ahora también las
        # ABIERTAS que tengan ventas parciales ya realizadas: su round-trip
        # cerrado pasado merece estar en el scatter.
        if not computed.sale_matches:
            continue

        still_open = not computed.is_closed
        matches = computed.sale_matches
        shares_sold  = sum((m.shares       for m in matches), Decimal("0"))
        cost_eur     = sum((m.cost_eur     for m in matches), Decimal("0"))
        proceeds_eur = sum((m.proceeds_eur for m in matches), Decimal("0"))
        fees_eur     = sum((tx.fee / tx.exchange_rate for tx in txs), Decimal("0"))

        # Defensa: una posición con sale_matches no vacío pero cost_eur=0 es
        # un dato corrupto. Mejor omitirla que mostrar pnl_pct sin sentido.
        if cost_eur <= Decimal("0") or shares_sold <= Decimal("0"):
            continue

        # Media ponderada de días por lote FIFO (cost_eur y shares_sold > 0 garantizado)
        weighted_days = sum(
            m.shares * Decimal((m.sell_date - m.buy_date).days)
            for m in matches
        )
        avg_days = float(weighted_days / shares_sold)
        pnl_pct  = float(computed.realized_gain_eur / cost_eur * 100)

        last_sell_date = max(m.sell_date for m in matches).isoformat()

        # Para posiciones abiertas (round-trip parcial) no atribuimos dividendos
        # al tramo vendido: no se pueden repartir limpiamente entre lo vendido y
        # lo que se conserva. Para cerradas, todos los dividendos pertenecen a
        # acciones ya vendidas, así que se incluyen.
        dividends_eur = Decimal("0") if still_open else computed.dividends_net_eur

        result.append(ClosedPositionAnalytics(
            position_id=pos.id,
            security_id=sec.id,
            yahoo_ticker=sec.yahoo_ticker,
            name=sec.name,
            market_code=sec.market,
            market_type=market_types.get(sec.market, "stock"),
            is_fund_market=market_types.get(sec.market) == "fund",
            shares_sold=shares_sold,
            cost_eur=cost_eur,
            proceeds_eur=proceeds_eur,
            realized_pnl_eur=computed.realized_gain_eur,
            dividends_eur=dividends_eur,
            total_profit_eur=computed.realized_gain_eur + dividends_eur,
            fees_eur=fees_eur,
            avg_days_held=avg_days,
            pnl_pct=pnl_pct,
            last_sell_date=last_sell_date,
            still_open=still_open,
        ))

    return result


# ---------------------------------------------------------------------------
#  Dividendos agrupados por acción (para tabla + gráficas)
# ---------------------------------------------------------------------------

def _months_held_active(txs: list) -> int:
    """
    Meses con ≥1 acción en posesión, contando solo periodos activos.
    'txs' son Transaction (calculations) ordenadas por fecha.
    """
    import math
    from datetime import date as dt_type

    events = sorted(txs, key=lambda t: t.date)
    shares = Decimal("0")
    prev_date = None
    total_days = 0

    for tx in events:
        if prev_date is not None and shares > Decimal("0"):
            total_days += (tx.date - prev_date).days
        shares += tx.shares if tx.type in ("buy", "transfer_in") else -tx.shares
        prev_date = tx.date

    # Si todavía tiene acciones (posición abierta), contar hasta hoy
    if shares > Decimal("0") and prev_date is not None:
        total_days += (dt_type.today() - prev_date).days

    return math.ceil(total_days / 30.44) if total_days > 0 else 0


@router.get("/dividends-by-security", response_model=list[SecurityDividendSummary])
def get_dividends_by_security(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    Agrega todos los dividendos del usuario agrupados por valor (security).
    Solo incluye valores con ≥1 dividendo cobrado.
    Consolida posiciones múltiples del mismo valor (compra, venta, recompra, etc.)
    """

    # Obtener todas las posiciones del usuario
    positions = db.scalars(
        select(Position).where(Position.user_id == user.id)
    ).all()

    # Agrupar posiciones por security_id
    pos_by_sec: dict[int, list[Position]] = defaultdict(list)
    for pos in positions:
        pos_by_sec[pos.security.id].append(pos)

    market_types: dict[str, str] = {
        m.code: m.market_type for m in db.scalars(select(MarketRow)).all()
    }

    repo = PortfolioRepository(db)
    summaries: list[SecurityDividendSummary] = []

    for sec_id, sec_positions in pos_by_sec.items():
        sec: Security = sec_positions[0].security

        # Consolidar todas las transacciones y dividendos de TODAS las posiciones
        all_txs: list = []
        all_divs_rows: list = []
        for pos in sec_positions:
            all_txs.extend(repo.transactions_for_position(pos.id))
            div_rows = db.scalars(
                select(DividendRow).where(DividendRow.position_id == pos.id)
            ).all()
            all_divs_rows.extend(div_rows)

        if not all_divs_rows:
            continue  # Sin dividendos → no incluir

        splits = repo.splits_for_security(sec_id)

        # Normalizar transacciones por splits
        txs_sorted = sorted(all_txs, key=lambda t: t.date)
        if splits:
            txs_sorted = normalize_splits(txs_sorted, splits)

        # Meses activos (con ≥1 acción)
        months_held = _months_held_active(txs_sorted)
        years_held = months_held / 12.0 if months_held > 0 else 0.0

        # Capital total invertido (todas las compras en EUR)
        total_cost_eur = float(sum(
            tx.price * tx.shares / tx.exchange_rate + tx.fee / tx.exchange_rate
            for tx in all_txs if tx.type in ("buy", "transfer_in")
        ))

        # Yield por dividendo: gross_eur / capital_en_fecha
        yield_pcts: list[float] = []
        per_shares_eur: list[float] = []
        total_eur = 0.0

        divs_sorted = sorted(all_divs_rows, key=lambda d: d.date)

        for div_row in divs_sorted:
            gross_eur = float(div_row.gross_amount / div_row.exchange_rate)
            total_eur += gross_eur
            per_shares_eur.append(float(div_row.gross_per_share / div_row.exchange_rate))

            # Calcular el capital en la fecha del dividendo
            # Usar compute_position con transacciones hasta esa fecha
            txs_until = [t for t in txs_sorted if t.date <= date_type.fromisoformat(div_row.date)]
            if txs_until:
                divs_until: list = []  # sin dividendos para avg_cost
                cp = compute_position(txs_until, divs_until, splits)
                shares_then = float(div_row.shares_at_date)
                if cp.current_shares > Decimal("0"):
                    avg_cost_eur = float(cp.invested_eur / cp.current_shares)
                else:
                    avg_cost_eur = 0.0
                capital_at_date = shares_then * avg_cost_eur
            else:
                capital_at_date = 0.0

            if capital_at_date > 0:
                yield_pcts.append(gross_eur / capital_at_date * 100)

        avg_yield_pct = sum(yield_pcts) / len(yield_pcts) if yield_pcts else 0.0
        avg_per_share = sum(per_shares_eur) / len(per_shares_eur) if per_shares_eur else 0.0

        # Yield on cost anualizado
        if years_held > 0 and total_cost_eur > 0:
            yield_on_cost = (total_eur / years_held) / total_cost_eur * 100
        else:
            yield_on_cost = 0.0

        summaries.append(SecurityDividendSummary(
            security_id=sec_id,
            yahoo_ticker=sec.yahoo_ticker,
            name=sec.name,
            market_type=market_types.get(sec.market, "stock"),
            count=len(all_divs_rows),
            months_held=months_held,
            years_held=round(years_held, 2),
            avg_yield_pct=round(avg_yield_pct, 4),
            avg_per_share=round(avg_per_share, 4),
            total_eur=round(total_eur, 2),
            total_cost_eur=round(total_cost_eur, 2),
            yield_on_cost=round(yield_on_cost, 4),
        ))

    summaries.sort(key=lambda s: s.total_eur, reverse=True)
    return summaries


# ---------------------------------------------------------------------------
#  Precio objetivo de venta (PATCH)
# ---------------------------------------------------------------------------

@router.patch("/{position_id}/notes", response_model=PositionOut)
def update_notes(
    position_id: int,
    body: NotesUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    pos = _require_position(db, position_id, user.id)
    pos.notes = body.notes or None
    db.commit()
    db.refresh(pos)
    return pos


@router.patch("/{position_id}/target-sell", response_model=PositionOut)
def update_target_sell(
    position_id: int,
    body: TargetSellUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    pos = _require_position(db, position_id, user.id)
    pos.target_sell_price = body.target_sell_price
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
    pos = _require_position(db, position_id, user.id)

    if body.type == "sell":
        repo = PortfolioRepository(db)
        existing_txs = repo.transactions_for_position(position_id)
        splits = repo.splits_for_security(pos.security_id)
        new_tx = Transaction(
            type="sell",
            date=date_type.fromisoformat(body.date),
            shares=body.shares,
            price=body.price,
            fee=body.fee,
            exchange_rate=body.exchange_rate,
        )
        try:
            compute_position(existing_txs + [new_tx], [], splits)
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
    pos = _require_position(db, position_id, user.id)
    tx = db.scalar(
        select(TransactionRow).where(
            TransactionRow.id == tx_id,
            TransactionRow.position_id == position_id,
        )
    )
    if tx is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No encontrado")

    # Las filas de traspaso (transfer_in/transfer_out) forman pareja entre dos
    # posiciones y NO se editan sueltas: hacerlo rompería el coste heredado y el
    # diferimiento fiscal. Se gestionan solo vía POST/DELETE /portfolio/transfer.
    if tx.type in ("transfer_in", "transfer_out"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Una transacción de traspaso no se edita; deshaz el traspaso y vuelve a crearlo.",
        )

    # Validar siempre: editar una compra a menos acciones puede dejar ventas sin respaldo.
    repo = PortfolioRepository(db)
    splits = repo.splits_for_security(pos.security_id)
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
        type=body.type,
        date=date_type.fromisoformat(body.date),
        shares=body.shares,
        price=body.price,
        fee=body.fee,
        exchange_rate=body.exchange_rate,
    )
    try:
        compute_position(other_txs + [new_tx], [], splits)
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
    pos = _require_position(db, position_id, user.id)
    tx = db.scalar(
        select(TransactionRow).where(
            TransactionRow.id == tx_id,
            TransactionRow.position_id == position_id,
        )
    )
    if tx is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No encontrado")

    # Las filas de traspaso no se borran sueltas: dejarían la pareja huérfana en
    # la otra posición. Se deshacen como pareja vía DELETE /portfolio/transfer.
    if tx.type in ("transfer_in", "transfer_out"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Una transacción de traspaso no se borra suelta; usa «deshacer traspaso».",
        )

    # Validar que eliminar esta transacción no deja las ventas sin respaldo
    repo = PortfolioRepository(db)
    splits = repo.splits_for_security(pos.security_id)
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
    try:
        compute_position(other_txs, [], splits)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"No se puede eliminar: {exc}",
        )

    db.delete(tx)
    db.commit()


# ---------------------------------------------------------------------------
#  Aportaciones periódicas (DCA)
# ---------------------------------------------------------------------------

def _plan_out(db: Session, plan: RecurringPlanRow) -> RecurringPlanOut:
    """Construye el RecurringPlanOut de un plan (próxima fecha y restantes)."""
    pos = db.get(Position, plan.position_id)
    sec = db.get(Security, pos.security_id)
    start = date_type.fromisoformat(plan.start_date)
    next_date = nth_contribution_date(start, plan.frequency, plan.done_count)
    return RecurringPlanOut(
        id=plan.id,
        security_id=sec.id,
        yahoo_ticker=sec.yahoo_ticker,
        name=sec.name,
        amount_per_period=plan.amount_per_period,
        fee_per_period=plan.fee_per_period,
        frequency=plan.frequency,
        currency=plan.currency,
        next_date=next_date.isoformat(),
        remaining=plan.total_count - plan.done_count,
    )


@router.post(
    "/{position_id}/recurring-buys",
    response_model=RecurringBuyResult,
    status_code=status.HTTP_201_CREATED,
)
def create_recurring_buys(
    position_id: int,
    body: RecurringBuyCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    Crea una serie de aportaciones periódicas (DCA) con importe fijo.

    Las aportaciones PASADAS (fecha <= hoy) se registran ya como compras
    (backfill): para cada fecha se resuelve el precio histórico del valor
    (price_history, día hábil anterior si no cotiza ese día) y participaciones =
    importe / precio. Para divisas distintas de EUR usa el tipo BCE de la fecha.
    Las pasadas que no se pueden valorar se devuelven en 'skipped'.

    Las aportaciones FUTURAS (fecha > hoy) NO se crean ahora —es imposible saber
    las participaciones sin cotización—: se guardan como un PLAN que el
    scheduler ejecutará al llegar cada fecha, con el precio real de ese día.

    La serie la define el rango start_date → end_date (ambos incluidos).
    """
    pos = _require_position(db, position_id, user.id)
    sec: Security = pos.security

    start = date_type.fromisoformat(body.start_date)
    end = date_type.fromisoformat(body.end_date)
    try:
        dates = contribution_dates_until(start, body.frequency, end)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc))
    count = len(dates)
    today = date_type.today()

    skipped: list[SkippedContribution] = []
    total_invested = Decimal("0")
    total_shares = Decimal("0")
    created_rows: list[TransactionRow] = []
    past_count = 0  # aportaciones cuya fecha ya pasó (<= hoy): consumidas del plan

    for d in dates:
        if d > today:
            break  # las futuras van al plan; las fechas vienen en orden creciente
        past_count += 1
        d_str = d.isoformat()

        # Precio del día hábil anterior o igual a la fecha de la aportación.
        price_row = db.scalar(
            select(PriceHistory)
            .where(
                PriceHistory.security_id == sec.id,
                PriceHistory.date <= d_str,
            )
            .order_by(PriceHistory.date.desc())
        )
        if price_row is None or price_row.close <= Decimal("0"):
            skipped.append(SkippedContribution(date=d_str, reason="sin precio histórico para esa fecha"))
            continue

        # Tipo de cambio de la fecha (1 para EUR; BCE por divisa para el resto).
        if sec.currency == "EUR":
            rate = Decimal("1")
        else:
            rate_row = db.scalar(
                select(EcbRate)
                .where(EcbRate.currency == sec.currency, EcbRate.date <= d_str)
                .order_by(EcbRate.date.desc())
            )
            if rate_row is None:
                skipped.append(SkippedContribution(date=d_str, reason="sin tipo de cambio para esa fecha"))
                continue
            rate = rate_row.rate

        shares = body.amount_per_period / price_row.close

        created_rows.append(TransactionRow(
            position_id=pos.id,
            type="buy",
            date=d_str,
            shares=shares,
            price=price_row.close,
            fee=body.fee_per_period,
            currency=sec.currency,
            exchange_rate=rate,
        ))
        total_invested += body.amount_per_period
        total_shares += shares

    for row in created_rows:
        db.add(row)

    # Si quedan aportaciones futuras, guardar el plan que el scheduler ejecutará.
    plan_row: RecurringPlanRow | None = None
    if past_count < count:
        plan_row = RecurringPlanRow(
            position_id=pos.id,
            amount_per_period=body.amount_per_period,
            fee_per_period=body.fee_per_period,
            frequency=body.frequency,
            start_date=body.start_date,
            total_count=count,
            done_count=past_count,
            currency=sec.currency,
        )
        db.add(plan_row)

    db.commit()

    return RecurringBuyResult(
        created=len(created_rows),
        skipped=skipped,
        total_invested_native=total_invested,
        total_shares=total_shares,
        currency=sec.currency,
        plan=_plan_out(db, plan_row) if plan_row is not None else None,
    )


@router.get("/recurring-plans", response_model=list[RecurringPlanOut])
def list_recurring_plans(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Planes de aportación periódica activos del usuario (pendientes de ejecutar)."""
    plans = db.scalars(
        select(RecurringPlanRow)
        .join(Position, RecurringPlanRow.position_id == Position.id)
        .where(Position.user_id == user.id)
    ).all()
    return [_plan_out(db, p) for p in plans]


@router.delete("/recurring-plans/{plan_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_recurring_plan(
    plan_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Cancela un plan de aportación periódica. No afecta a las compras ya creadas."""
    plan = db.scalar(
        select(RecurringPlanRow)
        .join(Position, RecurringPlanRow.position_id == Position.id)
        .where(RecurringPlanRow.id == plan_id, Position.user_id == user.id)
    )
    if plan is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Plan no encontrado")
    db.delete(plan)
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
#  Eliminar posición completa (solo si no tiene ventas)
# ---------------------------------------------------------------------------

@router.delete(
    "/positions/{position_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_position(
    position_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    Elimina una posición y todas sus compras y dividendos.

    Solo se permite si la posición no tiene ninguna venta registrada.
    Si hay ventas (aunque sea parciales), hay historial fiscal que no se
    puede borrar a la ligera; el usuario debe eliminar las ventas primero.
    """
    pos = _require_position(db, position_id, user.id)

    has_sells = db.scalar(
        select(TransactionRow).where(
            TransactionRow.position_id == position_id,
            TransactionRow.type == "sell",
        )
    ) is not None

    if has_sells:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=(
                "No se puede eliminar una posición con ventas registradas. "
                "Elimina primero las ventas desde el detalle del valor."
            ),
        )

    db.delete(pos)  # CASCADE elimina transactions y dividends hijos
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
