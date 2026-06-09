"""
schemas/catalog_requests.py
============================
Schemas Pydantic para solicitudes de catálogo, notificaciones in-app y
mensajes al administrador (v1.12.0).
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, field_validator


class SecurityRequestCreate(BaseModel):
    ticker: str
    isin: str | None = None
    name: str
    market_id: str
    currency: str | None = None

    @field_validator("ticker")
    @classmethod
    def ticker_upper(cls, v: str) -> str:
        return v.strip().upper()

    @field_validator("isin")
    @classmethod
    def isin_upper(cls, v: str | None) -> str | None:
        return v.strip().upper() if v and v.strip() else None

    @field_validator("name")
    @classmethod
    def name_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("El nombre no puede estar vacío")
        return v.strip()

    @field_validator("market_id")
    @classmethod
    def market_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("El mercado no puede estar vacío")
        return v.strip()


class SecurityRequestOut(BaseModel):
    id: int
    user_id: int
    username: str | None = None
    ticker: str
    isin: str | None
    name: str
    market_id: str | None
    currency: str | None
    status: str
    security_id: int | None
    reviewed_by: int | None
    reviewed_at: datetime | None
    notes: str | None
    created_at: datetime


class RequestApprove(BaseModel):
    market_id: str
    notes: str | None = None

    @field_validator("market_id")
    @classmethod
    def market_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("El mercado no puede estar vacío")
        return v.strip()


class RequestReject(BaseModel):
    notes: str | None = None


class UserNotificationOut(BaseModel):
    id: int
    type: str
    title: str
    body: str
    related_id: int | None
    related_type: str | None
    is_read: bool
    created_at: datetime


class CatalogMessageCreate(BaseModel):
    message: str
    security_request_id: int | None = None

    @field_validator("message")
    @classmethod
    def message_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("El mensaje no puede estar vacío")
        return v.strip()


class CatalogMessageOut(BaseModel):
    id: int
    user_id: int
    username: str | None = None
    message: str
    security_request_id: int | None
    is_resolved: bool
    created_at: datetime


class NotificationReply(BaseModel):
    message: str

    @field_validator("message")
    @classmethod
    def message_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("El mensaje no puede estar vacío")
        return v.strip()
