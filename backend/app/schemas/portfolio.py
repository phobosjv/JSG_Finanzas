"""Schemas de cartera: posiciones, transacciones y dividendos."""
from __future__ import annotations

from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, field_validator, model_validator


class PositionCreate(BaseModel):
    security_id: int
    target_sell_price: Decimal | None = None
    notes: str | None = None


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
    currency: Literal["EUR", "USD"]
    exchange_rate: Decimal = Decimal("1")

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
    currency: Literal["EUR", "USD"]
    exchange_rate: Decimal = Decimal("1")

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
    shares_sold: Decimal
    cost_eur: Decimal            # coste total de adquisición
    proceeds_eur: Decimal        # ingresos totales de la venta
    realized_pnl_eur: Decimal
    dividends_eur: Decimal
    total_profit_eur: Decimal    # realized_pnl + dividends
    fees_eur: Decimal
