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
from app.services.calculations import compute_position
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
    """
    repo = PortfolioRepository(session)

    sales: list[SecuritySales] = []
    for pos in repo.positions_of_user(user_id):
        txs = repo.transactions_for_position(pos.id)
        divs = repo.dividends_for_position(pos.id)

        # FIFO: produce los SaleMatch (emparejamientos venta-compra).
        position_result = compute_position(txs, divs)

        sales.append(
            SecuritySales(
                security=repo.security_ref(pos.security_id),
                matches=position_result.sale_matches,
                all_buys=repo.all_buys_for_security(user_id, pos.security_id),
            )
        )

    dividends = repo.dividend_records(user_id)
    return sales, dividends
