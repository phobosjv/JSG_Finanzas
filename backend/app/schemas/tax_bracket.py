"""Schemas para los tramos IRPF del ahorro."""
from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel, field_validator, model_validator


class TaxBracketOut(BaseModel):
    id: int
    min_amount: Decimal
    max_amount: Decimal | None
    rate: Decimal
    sort_order: int

    model_config = {"from_attributes": True}


class TaxBracketCreate(BaseModel):
    min_amount: Decimal
    max_amount: Decimal | None = None
    rate: Decimal
    sort_order: int = 0

    @field_validator("min_amount")
    @classmethod
    def min_non_negative(cls, v: Decimal) -> Decimal:
        if v < Decimal("0"):
            raise ValueError("min_amount no puede ser negativo")
        return v

    @field_validator("rate")
    @classmethod
    def rate_valid(cls, v: Decimal) -> Decimal:
        if v <= Decimal("0") or v >= Decimal("100"):
            raise ValueError("rate debe estar entre 0 y 100 (exclusivo)")
        return v

    @model_validator(mode="after")
    def max_greater_than_min(self) -> "TaxBracketCreate":
        if self.max_amount is not None and self.max_amount <= self.min_amount:
            raise ValueError("max_amount debe ser mayor que min_amount")
        return self


class TaxBracketUpdate(BaseModel):
    min_amount: Decimal | None = None
    max_amount: Decimal | None = None          # None = no cambia; usar clear_max=True para borrar
    clear_max: bool = False                    # True → poner max_amount a NULL (sin techo)
    rate: Decimal | None = None
    sort_order: int | None = None

    @field_validator("min_amount")
    @classmethod
    def min_non_negative(cls, v: Decimal | None) -> Decimal | None:
        if v is not None and v < Decimal("0"):
            raise ValueError("min_amount no puede ser negativo")
        return v

    @field_validator("rate")
    @classmethod
    def rate_valid(cls, v: Decimal | None) -> Decimal | None:
        if v is not None and (v <= Decimal("0") or v >= Decimal("100")):
            raise ValueError("rate debe estar entre 0 y 100 (exclusivo)")
        return v
