"""Schemas de precios de mercado."""
from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel


class PriceHistoryPoint(BaseModel):
    date: str
    close: Decimal

    model_config = {"from_attributes": True}


class SnapshotOut(BaseModel):
    security_id: int
    last_price: Decimal | None
    prev_close: Decimal | None
    daily_change_pct: Decimal | None
    min_1y: Decimal | None
    max_1y: Decimal | None
    min_2y: Decimal | None
    max_2y: Decimal | None
    min_5y: Decimal | None
    max_5y: Decimal | None
    last_dividend: Decimal | None
    updated_at: str | None

    model_config = {"from_attributes": True}


class SecurityOverview(BaseModel):
    """Security + snapshot + estado de favorito del usuario. Un call, todos los datos."""
    id: int
    name: str
    isin: str | None
    yahoo_ticker: str
    google_ticker: str | None
    market: str
    currency: str
    market_type: str = "stock"
    is_fund_market: bool = False
    last_price: Decimal | None
    daily_change_pct: Decimal | None
    min_1y: Decimal | None
    min_2y: Decimal | None
    min_5y: Decimal | None
    max_1y: Decimal | None
    last_dividend: Decimal | None
    is_favorite: bool
    target_buy_price: Decimal | None
    updated_at: str | None = None


class IndexQuote(BaseModel):
    name: str
    ticker: str
    last_price: Decimal | None
    daily_change_pct: Decimal | None
