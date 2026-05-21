"""
services/calculations.py
========================
Núcleo de cálculo financiero de la aplicación.

Principios de diseño (NO romper):
  * Funciones PURAS: este módulo no importa SQLAlchemy, FastAPI ni nada de I/O.
    Recibe datos y devuelve datos. Esto lo hace testeable de forma aislada.
  * Todo el dinero se opera con Decimal, nunca float. La capa que lee de
    SQLite convierte a Decimal al entrar; la capa de API convierte a str/float
    al salir. Aquí dentro, exactitud absoluta.
  * Todo se deriva de las transacciones. No hay estado precalculado.

Conversión de divisa:
  Los importes se reciben en su divisa nativa junto a su 'exchange_rate'
  (EUR/USD del BCE de la fecha de la operación; 1 para operaciones en EUR).
  El importe en euros es SIEMPRE  importe_divisa / exchange_rate  cuando el
  exchange_rate se expresa como "USD por 1 EUR" (que es como lo publica el BCE:
  p. ej. 1.0850 significa 1 EUR = 1.0850 USD). Por tanto:
        euros = dolares / rate
  Para operaciones en EUR, rate = 1 y la fórmula no altera nada.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from typing import Literal

# --------------------------------------------------------------------------
#  Tipos de entrada
# --------------------------------------------------------------------------
# Estas son representaciones ligeras de las filas de BD. La capa que llama
# (un router o un repositorio) construye estos objetos a partir de los
# modelos SyQLAlchemy y se los pasa a las funciones de este módulo.

CENT = Decimal("0.01")          # redondeo a céntimo
SHARE_PREC = Decimal("0.000001")  # precisión para fracciones de acción


@dataclass(frozen=True)
class Transaction:
    """Una compra o una venta. Importes en divisa nativa de la operación."""
    type: Literal["buy", "sell"]
    date: date
    shares: Decimal
    price: Decimal          # precio por acción, divisa nativa
    fee: Decimal            # comisión, divisa nativa
    exchange_rate: Decimal  # EUR/USD del BCE; 1 si la operación es en EUR


@dataclass(frozen=True)
class Dividend:
    """Un dividendo cobrado. Importes en divisa nativa."""
    date: date
    shares_at_date: Decimal
    gross_amount: Decimal       # bruto total
    withholding_tax: Decimal    # retención en origen
    exchange_rate: Decimal


# --------------------------------------------------------------------------
#  Estructuras internas y de salida
# --------------------------------------------------------------------------

@dataclass
class Lot:
    """
    Un lote de acciones compradas que aún no se han vendido.
    Forma la cola FIFO. 'unit_cost_eur' incluye su parte proporcional de
    comisión de compra, ya convertida a euros.
    """
    buy_date: date
    shares: Decimal             # acciones que quedan vivas en este lote
    unit_cost_native: Decimal   # coste por acción en divisa nativa (con comisión)
    unit_cost_eur: Decimal      # coste por acción en euros (con comisión)
    unit_fee_eur: Decimal = Decimal("0")  # comisión de compra por acción en euros


@dataclass(frozen=True)
class SaleMatch:
    """
    Resultado de emparejar una venta con un lote de compra concreto (FIFO).
    Es la unidad básica del informe fiscal: cada venta puede generar varios
    de estos si consume varios lotes.
    """
    sell_date: date
    buy_date: date
    shares: Decimal
    # Coste de adquisición de estas 'shares' (proporción del lote)
    cost_native: Decimal
    cost_eur: Decimal
    # Importe de venta imputable a estas 'shares' (proporción de la venta)
    proceeds_native: Decimal
    proceeds_eur: Decimal
    # Resultado fiscal de este tramo
    gain_native: Decimal
    gain_eur: Decimal
    # Comisiones imputables a este tramo (proporcionales a las acciones)
    buy_fee_eur: Decimal = Decimal("0")
    sell_fee_eur: Decimal = Decimal("0")


@dataclass
class PositionResult:
    """Todo lo derivado de una posición. Lo que consumen Cartera y la ficha."""
    # --- Acciones vivas hoy ---
    current_shares: Decimal
    # --- Coste de lo que se conserva ---
    invested_native: Decimal        # coste de los lotes vivos, divisa nativa
    invested_eur: Decimal           # idem en euros (cambios históricos)
    avg_price_native: Decimal       # precio medio de compra, divisa nativa
    # --- Resultado realizado (ventas ya ejecutadas) ---
    realized_gain_native: Decimal
    realized_gain_eur: Decimal
    # --- Dividendos ---
    dividends_net_native: Decimal
    dividends_net_eur: Decimal
    # --- Lotes vivos y emparejamientos de venta ---
    open_lots: list[Lot] = field(default_factory=list)
    sale_matches: list[SaleMatch] = field(default_factory=list)

    @property
    def is_closed(self) -> bool:
        """Posición cerrada: no quedan acciones vivas."""
        return self.current_shares <= Decimal("0")


# --------------------------------------------------------------------------
#  Conversión de divisa
# --------------------------------------------------------------------------

def to_eur(amount_native: Decimal, exchange_rate: Decimal) -> Decimal:
    """
    Convierte un importe de su divisa nativa a euros.
    El BCE publica EUR/USD como 'USD por 1 EUR' (p. ej. 1.0850).
    Para EUR, exchange_rate vale 1 y el importe pasa intacto.
    """
    if exchange_rate == Decimal("0"):
        raise ValueError("exchange_rate no puede ser 0")
    return amount_native / exchange_rate


# --------------------------------------------------------------------------
#  Núcleo: recorrido FIFO de las transacciones
# --------------------------------------------------------------------------

def compute_position(
    transactions: list[Transaction],
    dividends: list[Dividend],
) -> PositionResult:
    """
    Reconstruye el estado completo de una posición a partir de sus
    transacciones y dividendos, aplicando FIFO.

    FIFO (obligatorio en España para valores homogéneos): las acciones
    vendidas son siempre las primeras que se compraron.

    Devuelve un PositionResult con acciones vivas, coste, resultado
    realizado, dividendos netos, lotes abiertos y los emparejamientos
    venta-compra que alimentan el informe fiscal.
    """
    # Ordenar por fecha es imprescindible para que FIFO sea correcto.
    # Ante misma fecha, las compras van antes que las ventas: no se puede
    # vender una acción que se compra el mismo día si aún no está en cola.
    txs = sorted(
        transactions,
        key=lambda t: (t.date, 0 if t.type == "buy" else 1),
    )

    open_lots: list[Lot] = []
    sale_matches: list[SaleMatch] = []
    realized_native = Decimal("0")
    realized_eur = Decimal("0")

    for tx in txs:
        if tx.type == "buy":
            _apply_buy(tx, open_lots)
        else:  # sell
            g_native, g_eur, matches = _apply_sell(tx, open_lots)
            realized_native += g_native
            realized_eur += g_eur
            sale_matches.extend(matches)

    # --- Estado tras recorrer todo ---
    current_shares = sum((lot.shares for lot in open_lots), Decimal("0"))
    invested_native = sum(
        (lot.shares * lot.unit_cost_native for lot in open_lots), Decimal("0")
    )
    invested_eur = sum(
        (lot.shares * lot.unit_cost_eur for lot in open_lots), Decimal("0")
    )
    avg_price_native = (
        invested_native / current_shares
        if current_shares > Decimal("0")
        else Decimal("0")
    )

    # --- Dividendos ---
    div_net_native = Decimal("0")
    div_net_eur = Decimal("0")
    for d in dividends:
        net_native = d.gross_amount - d.withholding_tax
        div_net_native += net_native
        div_net_eur += to_eur(net_native, d.exchange_rate)

    return PositionResult(
        current_shares=current_shares,
        invested_native=invested_native,
        invested_eur=invested_eur,
        avg_price_native=avg_price_native,
        realized_gain_native=realized_native,
        realized_gain_eur=realized_eur,
        dividends_net_native=div_net_native,
        dividends_net_eur=div_net_eur,
        open_lots=open_lots,
        sale_matches=sale_matches,
    )


def _apply_buy(tx: Transaction, open_lots: list[Lot]) -> None:
    """
    Procesa una compra: crea un nuevo lote al final de la cola FIFO.
    El coste unitario incluye la comisión repartida entre las acciones,
    porque la comisión de compra es coste de adquisición a efectos fiscales.
    """
    gross_native = tx.shares * tx.price + tx.fee
    unit_cost_native = gross_native / tx.shares
    unit_cost_eur = to_eur(unit_cost_native, tx.exchange_rate)
    unit_fee_eur = to_eur(tx.fee, tx.exchange_rate) / tx.shares

    open_lots.append(
        Lot(
            buy_date=tx.date,
            shares=tx.shares,
            unit_cost_native=unit_cost_native,
            unit_cost_eur=unit_cost_eur,
            unit_fee_eur=unit_fee_eur,
        )
    )


def _apply_sell(
    tx: Transaction, open_lots: list[Lot]
) -> tuple[Decimal, Decimal, list[SaleMatch]]:
    """
    Procesa una venta consumiendo lotes desde el principio de la cola (FIFO).

    El ingreso neto de la venta = shares*price - fee (la comisión de venta
    resta del ingreso). Ese ingreso se reparte proporcionalmente entre los
    lotes consumidos para construir cada SaleMatch.

    Devuelve (ganancia_nativa, ganancia_eur, lista_de_emparejamientos).
    """
    shares_to_sell = tx.shares
    proceeds_total_native = tx.shares * tx.price - tx.fee  # neto de comisión

    matches: list[SaleMatch] = []
    gain_native_total = Decimal("0")
    gain_eur_total = Decimal("0")

    while shares_to_sell > Decimal("0"):
        if not open_lots:
            # No hay lotes que consumir: se intenta vender más de lo que
            # se posee. Es un error de datos del usuario, no se debe tragar.
            raise ValueError(
                f"Venta del {tx.date}: se intentan vender más acciones "
                f"de las disponibles segun el historial de compras."
            )

        lot = open_lots[0]
        take = min(shares_to_sell, lot.shares)

        # Importe de venta imputable a este tramo (proporcional)
        proceeds_native = proceeds_total_native * (take / tx.shares)
        proceeds_eur = to_eur(proceeds_native, tx.exchange_rate)

        # Coste de adquisición de este tramo
        cost_native = take * lot.unit_cost_native
        cost_eur = take * lot.unit_cost_eur

        gain_native = proceeds_native - cost_native
        gain_eur = proceeds_eur - cost_eur

        # Comisiones proporcionales a las acciones de este tramo
        buy_fee_eur = take * lot.unit_fee_eur
        sell_fee_eur = to_eur(tx.fee, tx.exchange_rate) * (take / tx.shares)

        matches.append(
            SaleMatch(
                sell_date=tx.date,
                buy_date=lot.buy_date,
                shares=take,
                cost_native=cost_native,
                cost_eur=cost_eur,
                proceeds_native=proceeds_native,
                proceeds_eur=proceeds_eur,
                gain_native=gain_native,
                gain_eur=gain_eur,
                buy_fee_eur=buy_fee_eur,
                sell_fee_eur=sell_fee_eur,
            )
        )

        gain_native_total += gain_native
        gain_eur_total += gain_eur

        # Consumir el lote
        lot.shares -= take
        shares_to_sell -= take
        if lot.shares <= Decimal("0"):
            open_lots.pop(0)

    return gain_native_total, gain_eur_total, matches


# --------------------------------------------------------------------------
#  Valoración a precio de mercado de hoy
# --------------------------------------------------------------------------

def value_position(
    result: PositionResult,
    current_price_native: Decimal,
    current_rate: Decimal,
) -> dict[str, Decimal]:
    """
    Valora una posición a la cotización de HOY.

    'current_price_native' es la última cotización (divisa nativa del valor).
    'current_rate' es el cambio EUR/USD de HOY (1 si el valor cotiza en EUR).

    Importante sobre divisas: el beneficio latente en euros mezcla dos
    efectos -- el del precio de la accion y el del tipo de cambio. Es
    inevitable al consolidar en euros y es la realidad de invertir en otra
    divisa. Aqui se devuelve el dato; la interfaz puede, si quiere, mostrar
    tambien el rendimiento "puro" en divisa nativa.

    Devuelve un diccionario de magnitudes ya listas para la pantalla.
    """
    shares = result.current_shares

    market_value_native = shares * current_price_native
    market_value_eur = to_eur(market_value_native, current_rate)

    # Beneficio latente: lo que valen hoy menos lo que costaron (coste
    # historico, con su cambio de cada compra).
    unrealized_native = market_value_native - result.invested_native
    unrealized_eur = market_value_eur - result.invested_eur

    # Porcentaje en EUR para que sea consistente con unrealized_eur:
    # un inversor en EUR mide su rentabilidad en EUR, no en la divisa nativa.
    unrealized_pct = (
        (unrealized_eur / result.invested_eur * Decimal("100"))
        if result.invested_eur > Decimal("0")
        else Decimal("0")
    )

    # Beneficio total del valor: realizado + latente + dividendos.
    total_gain_eur = (
        result.realized_gain_eur + unrealized_eur + result.dividends_net_eur
    )

    return {
        "market_value_native": market_value_native,
        "market_value_eur": market_value_eur,
        "unrealized_gain_native": unrealized_native,
        "unrealized_gain_eur": unrealized_eur,
        "unrealized_gain_pct": unrealized_pct,
        "total_gain_eur": total_gain_eur,
    }


def daily_change(
    shares: Decimal,
    last_price: Decimal,
    prev_close: Decimal,
    current_rate: Decimal,
) -> dict[str, Decimal]:
    """
    Variacion diaria de una posicion: cuanto se ha movido hoy lo que se posee.
    'prev_close' es el cierre del dia de bolsa anterior.
    """
    change_per_share = last_price - prev_close
    change_native = shares * change_per_share
    change_eur = to_eur(change_native, current_rate)
    change_pct = (
        (change_per_share / prev_close * Decimal("100"))
        if prev_close > Decimal("0")
        else Decimal("0")
    )
    return {
        "daily_change_native": change_native,
        "daily_change_eur": change_eur,
        "daily_change_pct": change_pct,
    }


# --------------------------------------------------------------------------
#  Agregados de cartera (Datos Generales del Dashboard / Cartera)
# --------------------------------------------------------------------------

def aggregate_portfolio(
    valued_positions: list[dict[str, Decimal]],
) -> dict[str, Decimal]:
    """
    Consolida varias posiciones ya valoradas en los Datos Generales.

    Cada elemento de 'valued_positions' debe traer, EN EUROS:
      invested_eur, market_value_eur, realized_gain_eur,
      unrealized_gain_eur, dividends_net_eur

    El % promedio es el AGREGADO (beneficio total / capital invertido),
    no la media de los porcentajes de cada valor: una posicion pequena con
    +200% no debe pesar igual que una grande con +5%.
    """
    invested = sum((p["invested_eur"] for p in valued_positions), Decimal("0"))
    market = sum((p["market_value_eur"] for p in valued_positions), Decimal("0"))
    realized = sum((p["realized_gain_eur"] for p in valued_positions), Decimal("0"))
    unrealized = sum((p["unrealized_gain_eur"] for p in valued_positions), Decimal("0"))
    dividends = sum((p["dividends_net_eur"] for p in valued_positions), Decimal("0"))

    total_gain = realized + unrealized + dividends

    # Para el % agregado se usa como base el capital invertido en lo VIVO.
    avg_pct = (
        (unrealized / invested * Decimal("100"))
        if invested > Decimal("0")
        else Decimal("0")
    )

    return {
        "invested_eur": invested,
        "market_value_eur": market,
        "difference_eur": market - invested,
        "realized_gain_eur": realized,
        "unrealized_gain_eur": unrealized,
        "dividends_net_eur": dividends,
        "total_gain_eur": total_gain,
        "avg_return_pct": avg_pct,
    }


# --------------------------------------------------------------------------
#  Utilidades de redondeo (solo en la frontera de presentacion)
# --------------------------------------------------------------------------

def round_money(value: Decimal) -> Decimal:
    """Redondea a 2 decimales. Usar SOLO al presentar, nunca al calcular."""
    return value.quantize(CENT, rounding=ROUND_HALF_UP)
