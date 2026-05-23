"""Schemas para la gestión de mercados (admin) y configuración global."""
from __future__ import annotations

from pydantic import BaseModel, field_validator


class MarketCreate(BaseModel):
    code: str
    name: str
    index_ticker: str | None = None
    currency: str = "EUR"
    fiscal_window_days: int = 60

    @field_validator("code")
    @classmethod
    def code_valid(cls, v: str) -> str:
        v = v.strip().lower()
        if not v or not v.replace("_", "").replace("-", "").isalnum():
            raise ValueError("El código solo puede contener letras, dígitos, - y _")
        if len(v) > 20:
            raise ValueError("El código no puede superar 20 caracteres")
        return v

    @field_validator("name")
    @classmethod
    def name_valid(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("El nombre no puede estar vacío")
        if len(v) > 100:
            raise ValueError("El nombre no puede superar 100 caracteres")
        return v

    @field_validator("fiscal_window_days")
    @classmethod
    def window_valid(cls, v: int) -> int:
        if v < 1:
            raise ValueError("fiscal_window_days debe ser >= 1")
        return v


class MarketUpdate(BaseModel):
    name: str | None = None
    index_ticker: str | None = None
    currency: str | None = None
    fiscal_window_days: int | None = None


class MarketOut(BaseModel):
    code: str
    name: str
    index_ticker: str | None
    currency: str
    fiscal_window_days: int

    model_config = {"from_attributes": True}


class SnapshotIntervalUpdate(BaseModel):
    minutes: int

    @field_validator("minutes")
    @classmethod
    def in_range(cls, v: int) -> int:
        if v < 5 or v > 60:
            raise ValueError("El intervalo debe estar entre 5 y 60 minutos")
        return v
