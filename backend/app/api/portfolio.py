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

from app.models import DividendRow, EcbRate, Position, PriceHistory, PriceSnapshot, Security, SecuritySplit, TransactionRow, User
from app.repositories.portfolio_repository import PortfolioRepository
from app.models.market import MarketRow
from app.schemas.portfolio import (
    ClosedPositionAnalytics,
    ClosedPositionSummary,
    DividendCreate, DividendOut,
    NotesUpdate, TargetSellUpdate,
    PositionCreate, PositionOut,
    PositionSummary,
    SecurityDividendSummary,
    TransactionCreate, TransactionOut,
    TransferCreate, TransferResult,
)
from app.services.calculations import (
    Transaction, compute_position, consumed_cost_fifo, daily_change,
    normalize_splits, value_position,
)

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

        if snap and snap.prev_close is not None:
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
        market_code=sec.market,
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
    )


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
    Valor histórico de la cartera reconstruido transacción a transacción.
    Para cada fecha de precio calcula las acciones en posesión en ese momento
    (buys acumulados - sells acumulados hasta esa fecha). Incluye posiciones
    cerradas durante el periodo que estuvieron abiertas.
    """
    positions = db.scalars(
        select(Position).where(Position.user_id == user.id)
    ).all()

    rate_row = db.scalar(select(EcbRate).order_by(EcbRate.date.desc()))
    current_rate = rate_row.rate if rate_row else Decimal("1")

    date_totals: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))

    for pos in positions:
        sec: Security = pos.security
        rate = current_rate if sec.currency == "USD" else Decimal("1")

        # Transacciones ordenadas por fecha (strings YYYY-MM-DD, orden lexicográfico correcto)
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
            .where(
                PriceHistory.security_id == sec.id,
                PriceHistory.date >= first_buy_date,
            )
            .order_by(PriceHistory.date)
        ).all()

        if not price_rows:
            continue

        # Normalizar acciones de cada transacción a equivalente post-todos-los-splits.
        # Los precios históricos de Yahoo Finance son split-adjusted, así que las
        # acciones también deben estarlo para que value = shares × price sea correcto.
        split_rows = db.scalars(
            select(SecuritySplit)
            .where(SecuritySplit.security_id == sec.id)
            .order_by(SecuritySplit.ex_date)
        ).all()

        def _adj_shares(tx_date_str: str, raw: Decimal) -> Decimal:
            result = raw
            for sp in split_rows:
                if sp.ex_date > tx_date_str:
                    result *= Decimal(sp.ratio_num) / Decimal(sp.ratio_den)
            return result

        # Barrido paralelo: acumula shares según las transacciones vigentes en cada fecha
        running_shares = Decimal("0")
        tx_idx = 0
        n_tx = len(tx_rows)

        for price_row in price_rows:
            while tx_idx < n_tx and tx_rows[tx_idx].date <= price_row.date:
                tx = tx_rows[tx_idx]
                adj = _adj_shares(tx.date, tx.shares)
                running_shares += adj if tx.type in ("buy", "transfer_in") else -adj
                tx_idx += 1

            if running_shares > Decimal("0"):
                date_totals[price_row.date] += running_shares * price_row.close / rate

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
        txs    = repo.transactions_for_position(pos.id)
        divs   = repo.dividends_for_position(pos.id)
        if not txs:
            continue
        splits = repo.splits_for_security(sec.id)
        computed = compute_position(txs, divs, splits)
        if not computed.is_closed:
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
    """
    positions = db.scalars(
        select(Position).where(Position.user_id == user.id)
    ).all()
    repo = PortfolioRepository(db)
    result = []

    for pos in positions:
        sec: Security = pos.security
        txs    = repo.transactions_for_position(pos.id)
        divs   = repo.dividends_for_position(pos.id)
        splits = repo.splits_for_security(sec.id)
        computed = compute_position(txs, divs, splits)

        if not computed.is_closed or not computed.sale_matches:
            continue

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

        result.append(ClosedPositionAnalytics(
            position_id=pos.id,
            security_id=sec.id,
            yahoo_ticker=sec.yahoo_ticker,
            name=sec.name,
            market_code=sec.market,
            shares_sold=shares_sold,
            cost_eur=cost_eur,
            proceeds_eur=proceeds_eur,
            realized_pnl_eur=computed.realized_gain_eur,
            dividends_eur=computed.dividends_net_eur,
            total_profit_eur=computed.realized_gain_eur + computed.dividends_net_eur,
            fees_eur=fees_eur,
            avg_days_held=avg_days,
            pnl_pct=pnl_pct,
            last_sell_date=last_sell_date,
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
