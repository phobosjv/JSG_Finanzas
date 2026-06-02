"""Schemas para la gestión de mercados (admin), splits y configuración global."""
from __future__ import annotations

import base64
import binascii
from datetime import date
from typing import Literal

from pydantic import BaseModel, field_validator

# Tipo de producto de un mercado (v1.7.6).
MarketType = Literal["stock", "fund", "etf", "crypto"]


class MarketCreate(BaseModel):
    code: str
    name: str
    index_ticker: str | None = None
    currency: str = "EUR"
    fiscal_window_days: int = 60
    sort_order: int = 0
    yahoo_exchange: str | None = None
    market_type: MarketType = "stock"
    # is_fund_market se deriva de market_type ('fund'); se acepta por
    # compatibilidad con clientes antiguos pero el tipo manda.
    is_fund_market: bool = False

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
    yahoo_exchange: str | None = None
    market_type: MarketType | None = None
    is_fund_market: bool | None = None

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
    yahoo_exchange: str | None = None
    market_type: str = "stock"
    is_fund_market: bool = False

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


class CurrenciesUpdate(BaseModel):
    currencies: list[str]


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


# Tipos de imagen permitidos para el logotipo de la aplicación.
LOGO_ALLOWED_MIMES = {"image/png", "image/jpeg", "image/webp", "image/svg+xml"}
# Tamaño máximo de la imagen ya decodificada (1 MiB).
LOGO_MAX_BYTES = 1024 * 1024


class LogoUpdate(BaseModel):
    """Subida del logotipo de la app como base64.

    `data` acepta tanto base64 puro como un data-URI
    (`data:image/png;base64,...`); en este último caso el prefijo se
    descompone y, si no se indica `mime`, se toma el del propio data-URI.
    """
    data: str
    mime: str | None = None

    @field_validator("data")
    @classmethod
    def data_valid(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("La imagen no puede estar vacía")
        return v.strip()

    def decoded(self) -> tuple[bytes, str]:
        """Devuelve (bytes, mime) validados. Lanza ValueError si algo falla."""
        raw = self.data
        mime = (self.mime or "").strip().lower()

        # Descomponer data-URI si viene con prefijo
        if raw.startswith("data:"):
            try:
                header, raw = raw.split(",", 1)
            except ValueError:
                raise ValueError("data-URI mal formado")
            # header tipo "data:image/png;base64"
            if not mime and ";" in header:
                mime = header[len("data:"):].split(";", 1)[0].strip().lower()

        if mime not in LOGO_ALLOWED_MIMES:
            raise ValueError(
                "Tipo de imagen no permitido. Usa PNG, JPEG, WebP o SVG."
            )

        try:
            blob = base64.b64decode(raw, validate=True)
        except (binascii.Error, ValueError):
            raise ValueError("La imagen no es base64 válido")

        if not blob:
            raise ValueError("La imagen está vacía")
        if len(blob) > LOGO_MAX_BYTES:
            raise ValueError("La imagen supera el tamaño máximo de 1 MB")

        return blob, mime


# ---------------------------------------------------------------------------
#  Importación / exportación de catálogo
# ---------------------------------------------------------------------------

class CatalogMarketIn(BaseModel):
    """Un mercado en el JSON de catálogo (importación/exportación).

    market_type es opcional para compatibilidad con catálogos exportados antes
    de v1.7.6: si falta, el importador lo deriva (fondo / 'etf'/'crypto' en el
    código / resto stock).
    """
    code: str
    name: str
    index_ticker: str | None = None
    currency: str = "EUR"
    fiscal_window_days: int = 60
    sort_order: int = 0
    market_type: MarketType | None = None
    is_fund_market: bool = False


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
