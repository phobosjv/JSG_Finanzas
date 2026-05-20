"""Schemas del catalogo de valores."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, field_validator

Market = Literal["ibex35", "continuo", "nasdaq"]
Currency = Literal["EUR", "USD"]


class SecurityCreate(BaseModel):
    name: str
    isin: str | None = None
    yahoo_ticker: str
    google_ticker: str | None = None
    market: Market
    currency: Currency

    @field_validator("yahoo_ticker")
    @classmethod
    def ticker_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("yahoo_ticker no puede estar vacio")
        return v.strip().upper()


class SecurityOut(BaseModel):
    id: int
    name: str
    isin: str | None
    yahoo_ticker: str
    google_ticker: str | None
    market: str
    currency: str

    model_config = {"from_attributes": True}
