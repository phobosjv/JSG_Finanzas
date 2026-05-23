"""Schemas del catalogo de valores."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, field_validator

# 'currency' sigue siendo EUR|USD: el motor de cálculo solo soporta BCE EUR/USD.
Currency = Literal["EUR", "USD"]


class SecurityCreate(BaseModel):
    name: str
    isin: str | None = None
    yahoo_ticker: str
    google_ticker: str | None = None
    market: str          # validado en la API contra la tabla markets
    currency: Currency

    @field_validator("name")
    @classmethod
    def name_valid(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("El nombre no puede estar vacío")
        if len(v) > 200:
            raise ValueError("El nombre no puede superar 200 caracteres")
        return v

    @field_validator("isin")
    @classmethod
    def isin_format(cls, v: str | None) -> str | None:
        if v is None:
            return v
        v = v.strip().upper()
        if len(v) != 12 or not v.isalnum():
            raise ValueError("El ISIN debe tener exactamente 12 caracteres alfanuméricos")
        return v

    @field_validator("yahoo_ticker")
    @classmethod
    def ticker_not_empty(cls, v: str) -> str:
        v = v.strip().upper()
        if not v:
            raise ValueError("yahoo_ticker no puede estar vacío")
        if len(v) > 20:
            raise ValueError("yahoo_ticker no puede superar 20 caracteres")
        return v

    @field_validator("google_ticker")
    @classmethod
    def google_ticker_clean(cls, v: str | None) -> str | None:
        if v is None:
            return v
        v = v.strip()
        if len(v) > 30:
            raise ValueError("google_ticker no puede superar 30 caracteres")
        return v or None


class SecurityOut(BaseModel):
    id: int
    name: str
    isin: str | None
    yahoo_ticker: str
    google_ticker: str | None
    market: str
    currency: str

    model_config = {"from_attributes": True}
