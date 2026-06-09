"""Schemas para subcarteras (agrupaciones personalizadas de posiciones)."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, field_validator


class SubcarteraCreate(BaseModel):
    name: str
    description: str | None = None

    @field_validator("name")
    @classmethod
    def name_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("El nombre no puede estar vacío")
        return v.strip()


class SubcarteraUpdate(BaseModel):
    name: str | None = None
    description: str | None = None

    @field_validator("name")
    @classmethod
    def name_not_empty(cls, v: str | None) -> str | None:
        if v is not None and not v.strip():
            raise ValueError("El nombre no puede estar vacío")
        return v.strip() if v is not None else v


class SubcarteraOut(BaseModel):
    id: int
    name: str
    description: str | None
    position_ids: list[int]
    created_at: datetime

    model_config = {"from_attributes": True}
