"""
repositories/portfolio_repository.py
====================================
El puente entre SQLite y la logica verificada.

Responsabilidad unica: leer filas (TransactionRow, DividendRow, Position,
Security) y traducirlas a los objetos PUROS que consumen los servicios:
  * calculations.Transaction / calculations.Dividend
  * tax_report.SecurityRef / SecuritySales / DividendRecord

Lo que este modulo NO hace:
  * No aplica FIFO ni calcula nada: eso es de calculations.py.
  * No decide nada fiscal: eso es de tax_report.py.
  * No redondea importes: eso es de la capa de presentacion.
  * No escribe: es de solo lectura (las altas/bajas las haran los routers
    CRUD; este repositorio alimenta la cadena de calculo).

Tres traducciones delicadas (ver justificacion en cada metodo):
  1. fecha texto 'YYYY-MM-DD'  ->  objeto date  (date.fromisoformat)
  2. importe REAL de SQLite    ->  Decimal limpio (lo garantiza el tipo Money)
  3. currency + exchange_rate  ->  validacion de coherencia
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    DividendRow, MarketRow, Position, Security, SecuritySplit, TransactionRow,
)
from app.services.calculations import Dividend, Split, Transaction
from app.services.tax_report import (
    SecurityRef, SecuritySales, DividendRecord,
)


# --------------------------------------------------------------------------
#  Validacion de coherencia divisa <-> tipo de cambio
# --------------------------------------------------------------------------

def _check_currency_consistency(
    row_id: int, kind: str, currency: str, exchange_rate: Decimal,
) -> None:
    """
    Una operacion en EUR debe tener exchange_rate exactamente 1; una en USD
    debe tenerlo distinto de 1 (no tiene sentido un cambio EUR/USD de 1.0).
    Una incoherencia aqui falsea silenciosamente toda la conversion a euros,
    asi que se detiene con error claro en lugar de devolver cifras malas.
    """
    if currency == "EUR" and exchange_rate != Decimal("1"):
        raise ValueError(
            f"{kind} id={row_id}: currency='EUR' exige exchange_rate=1, "
            f"pero vale {exchange_rate}."
        )
    if currency == "USD" and exchange_rate == Decimal("1"):
        raise ValueError(
            f"{kind} id={row_id}: currency='USD' con exchange_rate=1 es "
            f"sospechoso (no se pudo aplicar el tipo del BCE)."
        )
    if exchange_rate <= Decimal("0"):
        raise ValueError(
            f"{kind} id={row_id}: exchange_rate debe ser positivo, "
            f"vale {exchange_rate}."
        )


# --------------------------------------------------------------------------
#  Traductores fila -> objeto puro
# --------------------------------------------------------------------------

def _to_transaction(row: TransactionRow) -> Transaction:
    """
    TransactionRow (fila SQLite) -> calculations.Transaction (dataclass puro).

    'currency' NO se copia: el dataclass Transaction no lo tiene, al nucleo
    de calculo solo le importa exchange_rate. Pero SI se usa para validar
    coherencia antes de descartarlo.
    """
    _check_currency_consistency(
        row.id, "Transaccion", row.currency, row.exchange_rate
    )
    return Transaction(
        type=row.type,                       # 'buy' | 'sell'
        date=date.fromisoformat(row.date),   # texto -> objeto date
        shares=row.shares,                   # Decimal limpio (tipo Money)
        price=row.price,
        fee=row.fee,
        exchange_rate=row.exchange_rate,
    )


def _to_dividend(row: DividendRow) -> Dividend:
    """DividendRow (fila SQLite) -> calculations.Dividend (dataclass puro)."""
    _check_currency_consistency(
        row.id, "Dividendo", row.currency, row.exchange_rate
    )
    return Dividend(
        date=date.fromisoformat(row.date),
        shares_at_date=row.shares_at_date,
        gross_amount=row.gross_amount,
        withholding_tax=row.withholding_tax,
        exchange_rate=row.exchange_rate,
    )


def _to_security_ref(sec: Security, fiscal_window_days: int = 60) -> SecurityRef:
    """Security (fila SQLite) -> tax_report.SecurityRef."""
    return SecurityRef(
        security_id=sec.id,
        name=sec.name,
        isin=sec.isin,
        market=sec.market,
        fiscal_window_days=fiscal_window_days,
        currency=sec.currency,
    )


# --------------------------------------------------------------------------
#  Repositorio
# --------------------------------------------------------------------------

class PortfolioRepository:
    """
    Acceso de solo lectura a transacciones y dividendos, devolviendo ya los
    objetos que consumen calculations.py y tax_report.py.

    Recibe la Session de SQLAlchemy por constructor (inyeccion): el router
    abre la sesion, se la pasa, y el repositorio no gestiona su ciclo de vida.
    """

    def __init__(self, session: Session):
        self._db = session

    # ---- Para calculations.compute_position ------------------------------

    def transactions_for_position(self, position_id: int) -> list[Transaction]:
        """
        Todas las transacciones de UNA posicion, como objetos Transaction.

        No se ordenan aqui a proposito: compute_position reordena
        internamente (compras antes que ventas en igualdad de fecha). Anadir
        un ORDER BY seria trabajo redundante y podria dar falsa seguridad.
        """
        rows = self._db.scalars(
            select(TransactionRow).where(
                TransactionRow.position_id == position_id
            )
        ).all()
        return [_to_transaction(r) for r in rows]

    def dividends_for_position(self, position_id: int) -> list[Dividend]:
        """Todos los dividendos de UNA posicion, como objetos Dividend."""
        rows = self._db.scalars(
            select(DividendRow).where(
                DividendRow.position_id == position_id
            )
        ).all()
        return [_to_dividend(r) for r in rows]

    def splits_for_security(self, security_id: int) -> list[Split]:
        """Todos los splits de un valor, como objetos Split puros."""
        rows = self._db.scalars(
            select(SecuritySplit).where(SecuritySplit.security_id == security_id)
        ).all()
        return [
            Split(
                ex_date=date.fromisoformat(row.ex_date),
                ratio_num=row.ratio_num,
                ratio_den=row.ratio_den,
            )
            for row in rows
        ]

    # ---- Para tax_report.build_tax_report --------------------------------

    def all_buys_for_security(
        self, user_id: int, security_id: int,
    ) -> list[Transaction]:
        """
        TODAS las compras de un valor para un usuario, de CUALQUIER ano.

        tax_report necesita el historico completo de compras (no solo las
        del ejercicio) para detectar la regla de recompra: una venta con
        perdida en 2023 puede quedar afectada por una compra de 2024.

        El cruce es positions -> transactions: una posicion identifica
        univocamente (user, security), asi que se filtra por la posicion
        de ese usuario y ese valor.
        """
        rows = self._db.scalars(
            select(TransactionRow)
            .join(Position, TransactionRow.position_id == Position.id)
            .where(
                Position.user_id == user_id,
                Position.security_id == security_id,
                TransactionRow.type == "buy",
            )
        ).all()
        return [_to_transaction(r) for r in rows]

    def security_ref(self, security_id: int) -> SecurityRef:
        """Construye el SecurityRef de un valor. Falla si el valor no existe."""
        sec = self._db.get(Security, security_id)
        if sec is None:
            raise ValueError(f"No existe el valor con id={security_id}.")
        market_row = self._db.get(MarketRow, sec.market)
        fiscal_window_days = market_row.fiscal_window_days if market_row else 60
        return _to_security_ref(sec, fiscal_window_days)

    def dividend_records(self, user_id: int) -> list[DividendRecord]:
        """
        Todos los dividendos de un usuario como DividendRecord (dividendo +
        SecurityRef de su valor), listos para build_tax_report.

        El filtrado por ejercicio fiscal lo hace tax_report, no el
        repositorio: build_tax_report ya descarta lo que no es del ano.
        Se cargan todos y se deja decidir a la capa fiscal.
        """
        rows = self._db.execute(
            select(DividendRow, Security)
            .join(Position, DividendRow.position_id == Position.id)
            .join(Security, Position.security_id == Security.id)
            .where(Position.user_id == user_id)
        ).all()

        records: list[DividendRecord] = []
        for div_row, sec in rows:
            market_row = self._db.get(MarketRow, sec.market)
            fiscal_window_days = market_row.fiscal_window_days if market_row else 60
            records.append(
                DividendRecord(
                    security=_to_security_ref(sec, fiscal_window_days),
                    dividend=_to_dividend(div_row),
                )
            )
        return records

    def security_sales(self, user_id: int) -> list[SecuritySales]:
        """
        Construye un SecuritySales por cada valor con posicion del usuario.

        OJO: el campo 'matches' (los SaleMatch) lo produce
        calculations.compute_position, NO el repositorio. Aqui se devuelve
        'matches' como lista vacia; quien orquesta el informe debe rellenarla
        ejecutando compute_position con las transacciones de la posicion.

        Lo que el repositorio SI aporta: el SecurityRef y 'all_buys' (el
        historico completo de compras del valor).

        Se devuelve incompleto a proposito en lugar de llamar a
        compute_position aqui: eso mezclaria I/O con calculo y romperia la
        separacion de capas. El metodo build_sales_input (abajo) hace el
        montaje completo para quien quiera la pieza ya ensamblada.
        """
        positions = self._db.scalars(
            select(Position).where(Position.user_id == user_id)
        ).all()

        result: list[SecuritySales] = []
        for pos in positions:
            sec_ref = self.security_ref(pos.security_id)  # ya incluye fiscal_window_days
            all_buys = self.all_buys_for_security(user_id, pos.security_id)
            result.append(
                SecuritySales(
                    security=sec_ref,
                    matches=[],          # lo rellena compute_position
                    all_buys=all_buys,
                )
            )
        return result

    def positions_of_user(self, user_id: int) -> list[Position]:
        """Las filas Position de un usuario (para iterar posicion a posicion)."""
        return list(
            self._db.scalars(
                select(Position).where(Position.user_id == user_id)
            ).all()
        )
