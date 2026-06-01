"""
repositories/tax_report_input.py
================================
Orquestador: une la capa repositorio (I/O) con la capa de calculo para
producir el input completo de tax_report.build_tax_report.

Por que esto no esta dentro del repositorio:
  El repositorio es I/O puro y no debe llamar a compute_position (calculo).
  build_tax_report necesita SecuritySales con 'matches' YA rellenado. El
  unico modo de obtener 'matches' es ejecutar compute_position. Esa union
  -leer de BD + calcular- es lo que hace este modulo, que es la capa de
  orquestacion: conoce a ambas, pero ni el repositorio ni calculations.py
  se conocen entre si.

Resultado: una funcion que, dado un usuario, devuelve (sales, dividends)
listos para pasar a build_tax_report.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.repositories.portfolio_repository import PortfolioRepository
from app.services.calculations import compute_position, normalize_splits
from app.services.tax_report import SecuritySales, DividendRecord


def build_tax_report_input(
    session: Session, user_id: int,
) -> tuple[list[SecuritySales], list[DividendRecord]]:
    """
    Prepara los dos argumentos de tax_report.build_tax_report para un usuario.

    Para cada posicion del usuario:
      1. el repositorio carga sus transacciones y dividendos,
      2. compute_position aplica FIFO y produce los SaleMatch,
      3. se arma el SecuritySales con esos matches y el historico de compras.

    Devuelve (sales, dividends). El filtrado por ejercicio fiscal NO se hace
    aqui: build_tax_report ya descarta lo que no pertenece al ano pedido.

    Los fondos de inversión SÍ entran en el informe (sus ganancias acumulan en
    la base del ahorro como las acciones). Lo que NO genera resultado fiscal es
    el TRASPASO: en compute_position un 'transfer_out' consume lotes FIFO sin
    producir SaleMatch, así que el diferimiento fiscal del traspaso se respeta
    automáticamente y la plusvalía latente viaja al fondo de destino vía el
    coste heredado del 'transfer_in'.
    """
    repo = PortfolioRepository(session)

    sales: list[SecuritySales] = []
    for pos in repo.positions_of_user(user_id):
        txs    = repo.transactions_for_position(pos.id)
        divs   = repo.dividends_for_position(pos.id)
        splits = repo.splits_for_security(pos.security_id)

        # FIFO: produce los SaleMatch (emparejamientos venta-compra).
        position_result = compute_position(txs, divs, splits)

        # Normalizar all_buys con los mismos splits aplicados en compute_position.
        # Esto permite comparar match.shares (post-split) con buy.shares (también
        # post-split) en _is_loss_disallowed para detectar correctamente la regla
        # de recompra cuando el FIFO solo consume PARTE de una compra.
        raw_buys = repo.all_buys_for_security(user_id, pos.security_id)
        normalized_buys = normalize_splits(raw_buys, splits) if splits else raw_buys

        sales.append(
            SecuritySales(
                security=repo.security_ref(pos.security_id),
                matches=position_result.sale_matches,
                all_buys=normalized_buys,
            )
        )

    dividends = repo.dividend_records(user_id)
    return sales, dividends
