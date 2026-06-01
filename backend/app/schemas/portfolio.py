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
        if self.currency == "USD" and self.exchange_rate == Decimal("1"):
            raise ValueError("USD requiere un exchange_rate distinto de 1")
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

    model_config = {"from_attributes": True}


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
        if self.currency == "USD" and self.exchange_rate == Decimal("1"):
            raise ValueError("USD requiere un exchange_rate distinto de 1")
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
    currency: str                # divisa nativa del valor ('EUR' o 'USD')
    market_code: str             # código de mercado (para badge ETF/Crypto/Acción)
    has_sells: bool              # True si existe alguna venta (impide borrar la posición completa)
    # Acciones y coste
    shares: Decimal
    avg_cost_eur: Decimal        # precio medio por acción en EUR (con comisión)
    cost_eur: Decimal            # importe invertido = shares × avg_cost_eur
    # Valoración actual
    current_price: Decimal | None
    market_value_eur: Decimal
    # Beneficio latente
    unrealized_pnl_eur: Decimal
    unrealized_pnl_pct: Decimal
    # Variación diaria
    daily_change_pct: Decimal | None
    daily_change_eur: Decimal | None
    # Dividendos y beneficio total
    dividends_eur: Decimal
    realized_pnl_eur: Decimal    # beneficio realizado de ventas parciales
    total_profit_eur: Decimal    # unrealized_pnl + realized_pnl + dividends
    fees_eur: Decimal            # suma de comisiones de todas las transacciones en EUR
    # Objetivo de venta e indicadores
    target_sell_price: Decimal | None
    max_1y: Decimal | None
    notes: str | None = None


class ClosedPositionSummary(BaseModel):
    position_id: int
    security_id: int
    yahoo_ticker: str
    name: str
    market_code: str             # código de mercado (para badge ETF/Crypto/Acción)
    shares_sold: Decimal
    cost_eur: Decimal            # coste total de adquisición
    proceeds_eur: Decimal        # ingresos totales de la venta
    realized_pnl_eur: Decimal
    dividends_eur: Decimal
    total_profit_eur: Decimal    # realized_pnl + dividends
    fees_eur: Decimal


class ClosedPositionAnalytics(ClosedPositionSummary):
    """ClosedPositionSummary enriquecido con métricas para el scatter plot."""
    avg_days_held: float   # media ponderada de (sell_date - buy_date).days por lote FIFO
    pnl_pct: float         # realized_pnl_eur / cost_eur × 100
    last_sell_date: str    # fecha de la última venta (YYYY-MM-DD), para la etiqueta


class SecurityDividendSummary(BaseModel):
    """Agregado de dividendos cobrados de una acción, para tabla y gráficas."""
    security_id: int
    yahoo_ticker: str
    name: str
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
