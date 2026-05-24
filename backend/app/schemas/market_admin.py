"""Schemas para la gestión de mercados (admin), splits y configuración global."""
from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, field_validator


class MarketCreate(BaseModel):
    code: str
    name: str
    index_ticker: str | None = None
    currency: str = "EUR"
    fiscal_window_days: int = 60
    sort_order: int = 0

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
    currency: Literal["EUR", "USD"] | None = None
    fiscal_window_days: int | None = None
    sort_order: int | None = None

    @field_validator("fiscal_window_days")
    @classmethod
    def window_valid(cls, v: int | None) -> int | None:
        if v is not None and v < 1:
            raise ValueError("fiscal_window_days debe ser >= 1")
        return v


class MarketOut(BaseModel):
    code: str
    name: str
    index_ticker: str | None
    currency: str
    fiscal_window_days: int
    sort_order: int = 0

    model_config = {"from_attributes": True}


class MarketReorderItem(BaseModel):
    """Un ítem en la lista de reordenación de mercados."""
    code: str
    sort_order: int


class SnapshotIntervalUpdate(BaseModel):
    minutes: int

    @field_validator("minutes")
    @classmethod
    def in_range(cls, v: int) -> int:
        if v < 5 or v > 60:
            raise ValueError("El intervalo debe estar entre 5 y 60 minutos")
        return v


class AppNameUpdate(BaseModel):
    app_name: str

    @field_validator("app_name")
    @classmethod
    def name_valid(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("El nombre no puede estar vacío")
        if len(v) > 100:
            raise ValueError("El nombre no puede superar 100 caracteres")
        return v


# ---------------------------------------------------------------------------
#  Importación / exportación de catálogo
# ---------------------------------------------------------------------------

class CatalogMarketIn(BaseModel):
    """Un mercado en el JSON de catálogo (importación/exportación)."""
    code: str
    name: str
    index_ticker: str | None = None
    currency: str = "EUR"
    fiscal_window_days: int = 60


class CatalogSecurityIn(BaseModel):
    """Un valor en el JSON de catálogo (importación/exportación)."""
    name: str
    isin: str | None = None
    yahoo_ticker: str
    google_ticker: str | None = None
    market: str
    currency: str = "EUR"


class CatalogImportBody(BaseModel):
    """Cuerpo de la petición de importación de catálogo.
    Campos extra (exported_at, _note…) son ignorados.
    """
    markets: list[CatalogMarketIn] = []
    securities: list[CatalogSecurityIn] = []

    model_config = {"extra": "ignore"}


# ---------------------------------------------------------------------------
#  Splits / contrasplits
# ---------------------------------------------------------------------------

class SplitIn(BaseModel):
    ex_date: date
    ratio_num: int
    ratio_den: int
    notes: str | None = None

    @field_validator("ratio_num", "ratio_den")
    @classmethod
    def positive(cls, v: int) -> int:
        if v < 1:
            raise ValueError("Debe ser >= 1")
        return v


class SplitOut(BaseModel):
    id: int
    security_id: int
    ex_date: str
    ratio_num: int
    ratio_den: int
    notes: str | None

    model_config = {"from_attributes": True}
