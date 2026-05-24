"""
services/tax_report.py
======================
Logica del informe anual para la declaracion de la renta (IRPF, Espana).

Que hace este modulo:
  * Toma los emparejamientos venta-compra (SaleMatch) ya calculados por
    calculations.py y los filtra por ejercicio fiscal.
  * Separa los dos bloques que la declaracion trata de forma distinta:
      - Ganancias y perdidas patrimoniales  (por las VENTAS de acciones)
      - Rendimientos del capital mobiliario (por los DIVIDENDOS)
  * Detecta posibles aplicaciones de la "regla de los dos meses / un ano"
    y MARCA las perdidas afectadas, excluyendolas del saldo computable.

Que NO hace (limites deliberados):
  * No genera el PDF. Devuelve una estructura de datos; otra capa la pinta.
  * No decide de forma definitiva la regla de los dos meses: la determinacion
    de "valores homogeneos" y el computo final son competencia de un asesor.
    El modulo es conservador: ante la duda, avisa.
  * No calcula la deduccion por doble imposicion internacional: depende del
    conjunto de la declaracion. Solo expone la retencion en origen como dato.

Principios mantenidos: funciones puras, sin I/O, todo en Decimal.

Marco normativo aplicado (resumen, orientativo):
  * FIFO obligatorio para acciones homogeneas -> ya viene dado por SaleMatch.
  * Regla de recompra: una perdida no es computable si se recompra el mismo
    valor (u homogeneo) dentro de un plazo alrededor de la venta.
      - Valores en mercados UE/EEE: plazo de DOS MESES (antes o despues).
      - Valores fuera del EEE (p. ej. Nasdaq): plazo de UN ANO.
  * Dividendos: rendimiento del capital mobiliario, bloque distinto.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal

from app.services.calculations import SaleMatch, Transaction, Dividend, to_eur


# --------------------------------------------------------------------------
#  Tipos de entrada enriquecidos
# --------------------------------------------------------------------------
# El informe necesita saber, de cada SaleMatch, a que valor pertenece y en
# que mercado cotiza (para aplicar la regla de recompra). Esa informacion
# no esta en el SaleMatch, asi que la capa que llama debe envolverlo.


@dataclass(frozen=True)
class SecurityRef:
    """Identifica el valor al que pertenecen unas operaciones."""
    security_id: int
    name: str
    isin: str | None
    market: str
    fiscal_window_days: int = 60  # tomado de markets.fiscal_window_days

    @property
    def recapture_window(self) -> timedelta:
        """
        Plazo de la regla de recompra segun el mercado del valor.
        El valor viene de MarketRow.fiscal_window_days: 60 dias (UE/EEE)
        o 365 dias (fuera del EEE, p.ej. Nasdaq).
        """
        return timedelta(days=self.fiscal_window_days)


@dataclass(frozen=True)
class SecuritySales:
    """
    Todas las operaciones de UN valor relevantes para el informe.
    'matches' son los emparejamientos venta-compra producidos por
    calculations.compute_position para ese valor.
    'all_buys' es la lista completa de compras del valor (de cualquier ano):
    se necesita para detectar recompras que activan la regla de recompra.
    """
    security: SecurityRef
    matches: list[SaleMatch]
    all_buys: list[Transaction]


@dataclass(frozen=True)
class DividendRecord:
    """Un dividendo con el valor al que pertenece."""
    security: SecurityRef
    dividend: Dividend


# --------------------------------------------------------------------------
#  Estructuras de salida
# --------------------------------------------------------------------------

@dataclass
class SaleLine:
    """Una linea del informe: una venta emparejada con una compra (FIFO)."""
    security_name: str
    isin: str | None
    market: str
    sell_date: date
    buy_date: date
    shares: Decimal
    cost_eur: Decimal           # coste de adquisicion (con comision de compra)
    proceeds_eur: Decimal       # importe de venta (neto de comision de venta)
    gain_eur: Decimal           # resultado de este tramo
    # Marca de la regla de recompra
    loss_disallowed: bool = False       # True si es perdida y NO computa este ano
    disallowed_reason: str | None = None


@dataclass
class CommissionLine:
    """Resumen de comisiones de un valor cuyas acciones se vendieron en el ejercicio."""
    security_name: str
    isin: str | None
    market: str
    buy_fee_eur: Decimal    # comisiones de compra de los lotes consumidos (proporcional)
    sell_fee_eur: Decimal   # comisiones de venta del ejercicio
    total_fee_eur: Decimal


@dataclass
class DividendLine:
    """Una linea de dividendo del informe."""
    security_name: str
    isin: str | None
    market: str
    pay_date: date
    gross_eur: Decimal
    withholding_eur: Decimal    # retencion en origen
    net_eur: Decimal


@dataclass
class TaxReport:
    """Informe completo de un ejercicio. Lo que consume el generador de PDF."""
    year: int
    sale_lines: list[SaleLine] = field(default_factory=list)
    commission_lines: list[CommissionLine] = field(default_factory=list)
    dividend_lines: list[DividendLine] = field(default_factory=list)

    # --- Resumen de ganancias patrimoniales ---
    total_gains_eur: Decimal = Decimal("0")
    total_losses_computable_eur: Decimal = Decimal("0")
    total_losses_disallowed_eur: Decimal = Decimal("0")
    net_capital_result_eur: Decimal = Decimal("0")

    # --- Resumen de comisiones ---
    total_buy_fee_eur: Decimal = Decimal("0")
    total_sell_fee_eur: Decimal = Decimal("0")
    total_commission_eur: Decimal = Decimal("0")

    # --- Resumen de dividendos ---
    total_dividends_gross_eur: Decimal = Decimal("0")
    total_dividends_withholding_eur: Decimal = Decimal("0")
    total_dividends_net_eur: Decimal = Decimal("0")

    # Avisos para mostrar en el informe
    warnings: list[str] = field(default_factory=list)


# --------------------------------------------------------------------------
#  Deteccion de la regla de recompra
# --------------------------------------------------------------------------

def _is_loss_disallowed(
    match: SaleMatch,
    security: SecurityRef,
    all_buys: list[Transaction],
) -> bool:
    """
    Determina si una perdida queda afectada por la regla de recompra.

    Criterio: el tramo es una perdida (gain_eur < 0) y existe al menos una
    compra del MISMO valor dentro de la ventana temporal alrededor de la
    fecha de venta (antes o despues), distinta de la propia compra emparejada.

    IMPORTANTE: esto es una deteccion conservadora, no una sentencia. La
    norma habla de valores "homogeneos", concepto mas amplio que "el mismo
    valor". El modulo solo puede comprobar el mismo valor; por eso el
    resultado se MARCA y se acompana de aviso, no se aplica como definitivo.
    """
    if match.gain_eur >= Decimal("0"):
        return False  # no es perdida: la regla no aplica

    window = security.recapture_window
    sell = match.sell_date

    # La compra emparejada con esta venta no cuenta íntegramente como "recompra".
    # Se excluye la primera compra hallada en match.buy_date que representa el
    # lote consumido por FIFO; pero SOLO la parte consumida (match.shares).
    # Si esa compra tenía MÁS acciones de las que el FIFO consumió, las acciones
    # sobrantes SÍ son una "recompra" potencial dentro del plazo.
    #
    # IMPORTANTE: all_buys debe haberse normalizado con los mismos splits que se
    # usaron en compute_position (lo hace tax_report_input.build_tax_report_input)
    # para que buy.shares y match.shares sean comparables (ambos post-split).
    matched_buy_excluded = False
    for buy in all_buys:
        if not matched_buy_excluded and buy.date == match.buy_date:
            matched_buy_excluded = True
            # Si el lote de compra tenía más acciones de las emparejadas con
            # esta venta, las restantes ESTÁN en el plazo → pérdida afectada.
            if (
                buy.shares > match.shares
                and (sell - window) <= buy.date <= (sell + window)
            ):
                return True
            continue
        # Recompra dentro de la ventana [venta - plazo, venta + plazo]
        if (sell - window) <= buy.date <= (sell + window):
            return True

    return False


# --------------------------------------------------------------------------
#  Construccion del informe
# --------------------------------------------------------------------------

def build_tax_report(
    year: int,
    sales: list[SecuritySales],
    dividends: list[DividendRecord],
) -> TaxReport:
    """
    Construye el informe fiscal de un ejercicio.

    'year'      : ejercicio fiscal (las operaciones se filtran por este ano).
    'sales'     : ventas por valor, ya con sus emparejamientos FIFO.
    'dividends' : dividendos cobrados, con su valor asociado.

    Devuelve un TaxReport con las lineas detalladas y los totales.
    """
    report = TaxReport(year=year)

    # ---- Bloque 1: ganancias y perdidas patrimoniales (ventas) ----
    any_disallowed = False

    for sec_sales in sales:
        sec = sec_sales.security
        for match in sec_sales.matches:
            # Solo las ventas del ejercicio solicitado
            if match.sell_date.year != year:
                continue

            disallowed = _is_loss_disallowed(match, sec, sec_sales.all_buys)
            reason = None
            if disallowed:
                any_disallowed = True
                # El texto del plazo se deriva de fiscal_window_days del mercado
                # (no del código de mercado): así es correcto para cualquier
                # mercado personalizado, no solo para el código "nasdaq".
                days = sec.fiscal_window_days
                if days >= 365:
                    plazo = "un año"
                elif days >= 30:
                    meses = round(days / 30)
                    plazo = f"{meses} {'mes' if meses == 1 else 'meses'}"
                else:
                    plazo = f"{days} {'día' if days == 1 else 'días'}"
                reason = (
                    f"Posible aplicacion de la regla de recompra: existe una "
                    f"compra del mismo valor dentro del plazo de {plazo} "
                    f"alrededor de la venta. La perdida puede no ser "
                    f"computable en este ejercicio."
                )

            line = SaleLine(
                security_name=sec.name,
                isin=sec.isin,
                market=sec.market,
                sell_date=match.sell_date,
                buy_date=match.buy_date,
                shares=match.shares,
                cost_eur=match.cost_eur,
                proceeds_eur=match.proceeds_eur,
                gain_eur=match.gain_eur,
                loss_disallowed=disallowed,
                disallowed_reason=reason,
            )
            report.sale_lines.append(line)

            # Acumular en los totales segun el tipo de resultado
            if match.gain_eur >= Decimal("0"):
                report.total_gains_eur += match.gain_eur
            else:
                if disallowed:
                    report.total_losses_disallowed_eur += match.gain_eur
                else:
                    report.total_losses_computable_eur += match.gain_eur

    # Saldo computable = ganancias + perdidas que SI computan.
    # Las perdidas marcadas quedan fuera del saldo de este ejercicio.
    report.net_capital_result_eur = (
        report.total_gains_eur + report.total_losses_computable_eur
    )

    # ---- Bloque 2: comisiones de operaciones vendidas en el ejercicio ----
    for sec_sales in sales:
        sec = sec_sales.security
        buy_fee = Decimal("0")
        sell_fee = Decimal("0")
        for match in sec_sales.matches:
            if match.sell_date.year != year:
                continue
            buy_fee += match.buy_fee_eur
            sell_fee += match.sell_fee_eur

        if buy_fee + sell_fee > Decimal("0"):
            report.commission_lines.append(CommissionLine(
                security_name=sec.name,
                isin=sec.isin,
                market=sec.market,
                buy_fee_eur=buy_fee,
                sell_fee_eur=sell_fee,
                total_fee_eur=buy_fee + sell_fee,
            ))
            report.total_buy_fee_eur += buy_fee
            report.total_sell_fee_eur += sell_fee
            report.total_commission_eur += buy_fee + sell_fee

    report.commission_lines.sort(key=lambda l: l.security_name)

    # ---- Bloque 3: rendimientos del capital mobiliario (dividendos) ----
    for rec in dividends:
        div = rec.dividend
        if div.date.year != year:
            continue

        gross_eur = to_eur(div.gross_amount, div.exchange_rate)
        withholding_eur = to_eur(div.withholding_tax, div.exchange_rate)
        net_eur = gross_eur - withholding_eur

        report.dividend_lines.append(
            DividendLine(
                security_name=rec.security.name,
                isin=rec.security.isin,
                market=rec.security.market,
                pay_date=div.date,
                gross_eur=gross_eur,
                withholding_eur=withholding_eur,
                net_eur=net_eur,
            )
        )
        report.total_dividends_gross_eur += gross_eur
        report.total_dividends_withholding_eur += withholding_eur
        report.total_dividends_net_eur += net_eur

    # ---- Avisos para el PDF ----
    report.warnings.append(
        "Informe orientativo de apoyo. No sustituye la revision de un asesor "
        "fiscal ni constituye asesoramiento."
    )
    if any_disallowed:
        report.warnings.append(
            "Se han detectado posibles perdidas afectadas por la regla de "
            "recompra (dos meses / un ano). Aparecen marcadas y NO se han "
            "incluido en el saldo computable. Su tratamiento definitivo "
            "depende del concepto de valores homogeneos y debe revisarse."
        )
    if report.total_dividends_withholding_eur > Decimal("0"):
        report.warnings.append(
            "Existen retenciones en origen sobre dividendos. La deduccion por "
            "doble imposicion internacional no se calcula en este informe: "
            "depende del conjunto de la declaracion."
        )

    # Ordenar las lineas por fecha para una lectura comoda del PDF
    report.sale_lines.sort(key=lambda l: (l.sell_date, l.security_name))
    report.dividend_lines.sort(key=lambda l: (l.pay_date, l.security_name))

    return report


# --------------------------------------------------------------------------
#  Resumen en texto (util para depurar; el PDF usa la estructura directa)
# --------------------------------------------------------------------------

def report_summary(report: TaxReport) -> str:
    """Genera un resumen legible del informe. Para logs y depuracion."""
    lines = [
        f"Informe fiscal {report.year}",
        f"  Ganancias patrimoniales:",
        f"    Ganancias .................. {report.total_gains_eur:>12.2f} EUR",
        f"    Perdidas computables ....... {report.total_losses_computable_eur:>12.2f} EUR",
        f"    Perdidas NO computables .... {report.total_losses_disallowed_eur:>12.2f} EUR",
        f"    Saldo computable ........... {report.net_capital_result_eur:>12.2f} EUR",
        f"  Dividendos:",
        f"    Bruto ...................... {report.total_dividends_gross_eur:>12.2f} EUR",
        f"    Retencion en origen ........ {report.total_dividends_withholding_eur:>12.2f} EUR",
        f"    Neto ....................... {report.total_dividends_net_eur:>12.2f} EUR",
    ]
    return "\n".join(lines)
