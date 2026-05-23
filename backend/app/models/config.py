"""
models/config.py
================
Tabla 'app_config'. Configuración global de la aplicación (clave-valor).

Claves definidas:
  snapshot_interval_minutes — frecuencia (min) del job de snapshots en vivo
                              (mínimo 5, máximo 60; por defecto 5).
"""

from __future__ import annotations

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class AppConfig(Base):
    __tablename__ = "app_config"

    key:   Mapped[str] = mapped_column(String, primary_key=True)
    value: Mapped[str] = mapped_column(String, nullable=False)

    def __repr__(self) -> str:
        return f"<AppConfig {self.key}={self.value!r}>"
