"""Schemas de cartera: posiciones, transacciones y dividendos."""
from __future__ import annotations

from datetime import date as date_type
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, field_validator, model_validator


def _validate_currency_code(v: str) -> str:
    v = v.strip().upper()
    if len(v) != 3 or not v.isalpha():
        raise ValueError("Código de divisa inválido (debe ser 3 letras, ej: EUR, USD, GBP)")
    return v


def _valid_date(v: str) -> str:
    """Valida que la cadena sea una fecha ISO válida (YYYY-MM-DD)."""
    try:
        date_type.fromisoformat(v)
    except ValueError:
        raise ValueError(f"Fecha inválida: '{v}'. Formato esperado: YYYY-MM-DD")
    return v


class PositionCreate(BaseModel):
    security_id: int
    target_sell_price: Decimal | None = None
    notes: str | None = None

    @field_validator("target_sell_price")
    @classmethod
    def target_non_negative(cls, v: Decimal | None) -> Decimal | None:
        if v is not None and v < 0:
            raise ValueError("El precio objetivo no puede ser negativo")
        return v

    @field_validator("notes")
    @classmethod
    def notes_max_len(cls, v: str | None) -> str | None:
        if v is not None and len(v) > 500:
            raise ValueError("Las notas no pueden superar 500 caracteres")
        return v


class NotesUpdate(BaseModel):
    notes: str | None = None

    @field_validator("notes")
    @classmethod
    def notes_max_len(cls, v: str | None) -> str | None:
        if v is not None and len(v) > 500:
            raise ValueError("Las notas no pueden superar 500 caracteres")
        return v


class TargetSellUpdate(BaseModel):
    target_sell_price: Decimal | None = None

    @field_validator("target_sell_price")
    @classmethod
    def non_negative(cls, v: Decimal | None) -> Decimal | None:
        if v is not None and v < 0:
            raise ValueError("El precio objetivo no puede ser negativo")
        return v


class PositionOut(BaseModel):
    id: int
    security_id: int
    user_id: int
    target_sell_price: Decimal | None
    notes: str | None

    model_config = {"from_attributes": True}


class TransactionCreate(BaseModel):
    type: Literal["buy", "sell"]
    date: str          # YYYY-MM-DD
    shares: Decimal
    price: Decimal
    fee: Decimal = Decimal("0")
    currency: str
    exchange_rate: Decimal = Decimal("1")

    @field_validator("currency")
    @classmethod
    def currency_code(cls, v: str) -> str:
        return _validate_currency_code(v)

    @field_validator("date")
    @classmethod
    def valid_date(cls, v: str) -> str:
        return _valid_date(v)

    @field_validator("shares", "price")
    @classmethod
    def positive(cls, v: Decimal) -> Decimal:
        if v <= 0:
            raise ValueError("Debe ser mayor que 0")
        return v

    @field_validator("fee")
    @classmethod
    def non_negative(cls, v: Decimal) -> Decimal:
        if v < 0:
            raise ValueError("No puede ser negativo")
        return v

    @model_validator(mode="after")
    def rate_coherent(self) -> "TransactionCreate":
        if self.currency == "EUR" and self.exchange_rate != Decimal("1"):
            raise ValueError("EUR exige exchange_rate=1")
        if self.currency != "EUR" and self.exchange_rate == Decimal("1"):
            raise ValueError(f"{self.currency} requiere un exchange_rate distinto de 1")
        return self


class TransactionOut(BaseModel):
    id: int
    type: str
    date: str
    shares: Decimal
    price: Decimal
    fee: Decimal
    currency: str
    exchange_rate: Decimal
    transfer_group_id: str | None = None
    related_security_id: int | None = None
    related_security_name: str | None = None
    transfer_partner_shares: Decimal | None = None  # participaciones del otro lado del traspaso

    model_config = {"from_attributes": True}


class TransferCreate(BaseModel):
    """
    Traspaso de fondos: salida de 'shares' del fondo de origen y entrada de
    'dest_shares' en el fondo de destino, en la misma fecha. El backend calcula
    el coste heredado por FIFO (no se introduce manualmente). Fiscalmente neutro.
    """
    origin_position_id: int
    shares: Decimal            # participaciones a traspasar del origen
    dest_security_id: int      # fondo de destino
    dest_shares: Decimal       # participaciones recibidas en el destino
    date: str                  # YYYY-MM-DD

    @field_validator("date")
    @classmethod
    def valid_date(cls, v: str) -> str:
        return _valid_date(v)

    @field_validator("shares", "dest_shares")
    @classmethod
    def positive(cls, v: Decimal) -> Decimal:
        if v <= 0:
            raise ValueError("Debe ser mayor que 0")
        return v


class TransferUpdate(BaseModel):
    """Edición de un traspaso existente: nuevos valores de participaciones y fecha.
    El backend recalcula el coste heredado por FIFO. No se puede cambiar el fondo."""
    shares: Decimal
    dest_shares: Decimal
    date: str

    @field_validator("date")
    @classmethod
    def valid_date(cls, v: str) -> str:
        return _valid_date(v)

    @field_validator("shares", "dest_shares")
    @classmethod
    def positive(cls, v: Decimal) -> Decimal:
        if v <= 0:
            raise ValueError("Debe ser mayor que 0")
        return v


class TransferResult(BaseModel):
    """Resultado de un traspaso: las dos transacciones creadas + coste heredado."""
    origin_position_id: int
    dest_position_id: int
    transfer_out_id: int
    transfer_in_id: int
    inherited_cost_eur: Decimal
    transfer_group_id: str


class RecurringBuyCreate(BaseModel):
    """
    Serie de aportaciones periódicas (DCA) definida por un RANGO de fechas
    (inicio → fin) y un importe fijo por aportación.

    Las aportaciones pasadas (<= hoy) se registran ya como compras con el precio
    histórico de cada fecha (participaciones = importe / precio; USD usa el tipo
    EUR/USD del BCE de la fecha). Las futuras quedan como plan que el scheduler
    ejecuta al llegar cada fecha. El importe y la comisión van en la divisa
    nativa del valor.
    """
    amount_per_period: Decimal      # importe invertido en cada aportación (divisa nativa)
    fee_per_period: Decimal = Decimal("0")
    frequency: Literal["weekly", "monthly", "quarterly", "yearly"]
    start_date: str                 # YYYY-MM-DD (primera aportación)
    end_date: str                   # YYYY-MM-DD (última aportación posible, incluida)

    @field_validator("start_date", "end_date")
    @classmethod
    def valid_date(cls, v: str) -> str:
        return _valid_date(v)

    @field_validator("amount_per_period")
    @classmethod
    def amount_positive(cls, v: Decimal) -> Decimal:
        if v <= 0:
            raise ValueError("El importe por aportación debe ser mayor que 0")
        return v

    @field_validator("fee_per_period")
    @classmethod
    def fee_non_negative(cls, v: Decimal) -> Decimal:
        if v < 0:
            raise ValueError("La comisión no puede ser negativa")
        return v

    @model_validator(mode="after")
    def end_after_start(self) -> "RecurringBuyCreate":
        if self.end_date < self.start_date:  # comparación lexicográfica ISO válida
            raise ValueError("La fecha de fin no puede ser anterior a la de inicio")
        return self


class SkippedContribution(BaseModel):
    """Una aportación PASADA que no se pudo registrar (backfill), con su motivo."""
    date: str
    reason: str


class RecurringPlanOut(BaseModel):
    """Plan de aportaciones periódicas futuras (lo ejecuta el scheduler)."""
    id: int
    security_id: int
    yahoo_ticker: str
    name: str
    amount_per_period: Decimal
    fee_per_period: Decimal
    frequency: str
    currency: str
    next_date: str          # próxima aportación pendiente (calculada)
    remaining: int          # aportaciones futuras que quedan por ejecutar


class RecurringBuyResult(BaseModel):
    """
    Resultado de crear una serie de aportaciones periódicas (DCA).

    Parte PASADA: se registran ya como compras (backfill) con precio histórico
    (created/skipped/totales). Parte FUTURA: queda como plan que el scheduler
    ejecutará al llegar cada fecha (campo 'plan', None si no hay fechas futuras).
    """
    created: int
    skipped: list[SkippedContribution] = []
    total_invested_native: Decimal = Decimal("0")
    total_shares: Decimal = Decimal("0")
    currency: str = "EUR"
    plan: RecurringPlanOut | None = None


class DividendCreate(BaseModel):
    date: str
    shares_at_date: Decimal
    gross_per_share: Decimal
    gross_amount: Decimal
    withholding_tax: Decimal = Decimal("0")
    currency: str
    exchange_rate: Decimal = Decimal("1")

    @field_validator("currency")
    @classmethod
    def currency_code(cls, v: str) -> str:
        return _validate_currency_code(v)

    @field_validator("date")
    @classmethod
    def valid_date(cls, v: str) -> str:
        return _valid_date(v)

    @field_validator("shares_at_date", "gross_per_share", "gross_amount")
    @classmethod
    def positive(cls, v: Decimal) -> Decimal:
        if v <= 0:
            raise ValueError("Debe ser mayor que 0")
        return v

    @model_validator(mode="after")
    def rate_coherent(self) -> "DividendCreate":
        if self.currency == "EUR" and self.exchange_rate != Decimal("1"):
            raise ValueError("EUR exige exchange_rate=1")
        if self.currency != "EUR" and self.exchange_rate == Decimal("1"):
            raise ValueError(f"{self.currency} requiere un exchange_rate distinto de 1")
        return self


class DividendOut(BaseModel):
    id: int
    date: str
    shares_at_date: Decimal
    gross_per_share: Decimal
    gross_amount: Decimal
    withholding_tax: Decimal
    currency: str
    exchange_rate: Decimal

    model_config = {"from_attributes": True}


class PositionSummary(BaseModel):
    position_id: int
    security_id: int
    yahoo_ticker: str
    name: str
    isin: str | None = None
    currency: str                # divisa nativa del valor ('EUR' o 'USD')
    market_code: str             # código de mercado (para badge ETF/Crypto/Acción)
    market_type: str = "stock"   # tipo de producto: stock|fund|etf|crypto (segmentación)
    is_fund_market: bool = False # True si el mercado es de fondos de inversión
    has_sells: bool              # True si existe alguna venta (impide borrar la posición completa)
    # Acciones y coste
    shares: Decimal
    avg_cost_eur: Decimal        # precio medio por acción en EUR (con comisión)
    cost_eur: Decimal            # importe invertido = shares × avg_cost_eur
    avg_cost_native: Decimal     # precio medio por acción en divisa nativa
    cost_native: Decimal         # importe invertido en divisa nativa
    # Valoración actual
    current_price: Decimal | None
    market_value_eur: Decimal
    market_value_native: Decimal
    # Beneficio latente
    unrealized_pnl_eur: Decimal
    unrealized_pnl_pct: Decimal
    unrealized_pnl_native: Decimal
    # Variación diaria
    daily_change_pct: Decimal | None
    daily_change_eur: Decimal | None
    # Dividendos y beneficio total
    dividends_eur: Decimal
    dividends_native: Decimal
    realized_pnl_eur: Decimal    # beneficio realizado de ventas parciales
    realized_pnl_native: Decimal
    total_profit_eur: Decimal    # unrealized_pnl + realized_pnl + dividends
    total_profit_native: Decimal
    fees_eur: Decimal            # suma de comisiones de todas las transacciones en EUR
    fees_native: Decimal         # suma de comisiones en divisa nativa
    # Objetivos de precio e indicadores. El objetivo de COMPRA vive en favorites
    # (catálogo/mercados), no en la posición; aquí solo el de venta.
    target_sell_price: Decimal | None
    max_1y: Decimal | None
    notes: str | None = None
    # Valor de mercado en el momento de los traspasos de entrada (para mostrar la
    # rentabilidad "desde el traspaso"). None si la posición no tiene traspasos.
    transfer_in_market_eur: Decimal | None = None


class ClosedPositionSummary(BaseModel):
    position_id: int
    security_id: int
    yahoo_ticker: str
    name: str
    isin: str | None = None
    currency: str = "EUR"        # divisa nativa del valor
    market_code: str             # código de mercado (para badge ETF/Crypto/Acción)
    market_type: str = "stock"   # tipo de producto: stock|fund|etf|crypto (segmentación)
    is_fund_market: bool = False # True si el mercado es de fondos de inversión
    shares_sold: Decimal
    cost_eur: Decimal            # coste total de adquisición en EUR
    cost_native: Decimal         # coste total de adquisición en divisa nativa
    proceeds_eur: Decimal        # ingresos totales de la venta en EUR
    proceeds_native: Decimal     # ingresos totales de la venta en divisa nativa
    realized_pnl_eur: Decimal
    realized_pnl_native: Decimal
    dividends_eur: Decimal
    dividends_native: Decimal
    total_profit_eur: Decimal    # realized_pnl + dividends (EUR)
    total_profit_native: Decimal
    fees_eur: Decimal
    fees_native: Decimal


class ClosedPositionAnalytics(ClosedPositionSummary):
    """ClosedPositionSummary enriquecido con métricas para el scatter plot."""
    avg_days_held: float   # media ponderada de (sell_date - buy_date).days por lote FIFO
    pnl_pct: float         # realized_pnl_eur / cost_eur × 100
    last_sell_date: str    # fecha de la última venta (YYYY-MM-DD), para la etiqueta
    still_open: bool = False  # True si la posición SIGUE abierta (round-trip parcial pasado)


class SecurityDividendSummary(BaseModel):
    """Agregado de dividendos cobrados de una acción, para tabla y gráficas."""
    security_id: int
    yahoo_ticker: str
    name: str
    market_type: str = "stock"  # tipo de producto: stock|fund|etf|crypto (segmentación)
    count: int             # número de cobros de dividendo
    months_held: int       # meses con ≥1 acción (ceil), solo periodos activos
    years_held: float      # months_held / 12
    avg_yield_pct: float   # media de (gross_eur / capital_en_fecha × 100) por cobro
    avg_per_share: float   # media de gross_per_share en EUR por cobro
    total_eur: float       # suma de gross_amount_eur de todos los cobros
    total_cost_eur: float  # capital total invertido (suma de todas las compras en EUR)
    yield_on_cost: float   # (total_eur / years_held) / total_cost_eur × 100 (anualizado)


# ---------------------------------------------------------------------------
#  Importación CSV de operaciones
# ---------------------------------------------------------------------------

class CsvRowIn(BaseModel):
    """Una fila del CSV de importación. El frontend parsea el CSV y envía
    la lista de filas como JSON. Los campos no aplicables se ignoran."""
    type: Literal["buy", "sell", "dividend"]
    ticker: str
    date: str
    shares: Decimal                          # acciones (buy/sell) o shares_at_date (dividend)
    price: Decimal | None = None             # obligatorio para buy/sell
    gross_per_share: Decimal | None = None   # obligatorio para dividend
    gross_amount: Decimal | None = None      # opcional dividend; calculado si None
    fee: Decimal = Decimal("0")              # solo buy/sell
    withholding_tax: Decimal = Decimal("0")  # solo dividend
    currency: str = "EUR"
    exchange_rate: Decimal = Decimal("1")

    @field_validator("currency")
    @classmethod
    def currency_code(cls, v: str) -> str:
        return _validate_currency_code(v)


class CsvImportBody(BaseModel):
    rows: list[CsvRowIn]


class CsvImportResult(BaseModel):
    transactions_added: int
    dividends_added: int
    skipped: int
    errors: list[dict]  # [{"row": int, "ticker": str, "reason": str}]
