"""
services/backup.py
==================
Serialización pura para backup/restore de cartera.

Las funciones de este módulo no tocan la BD; reciben estructuras de datos
ya leídas y devuelven dicts exportables, o validan el formato de un import.
La I/O real (SELECT/INSERT) queda en api/backup.py y api/admin.py.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


BACKUP_VERSION = "1"
# admin_2 (v1.22.0): añade app_config, tax_brackets, security_splits,
# subcarteras y campos extra de usuario (email/is_enabled/expires_at/…) para que
# el backup completo sirva como migración 1:1 de servidor. Retrocompatible con
# admin_1: las secciones nuevas son opcionales y un backup admin_1 se importa
# igual (sin esas secciones).
ADMIN_BACKUP_VERSION = "admin_2"
_ACCEPTED_ADMIN_VERSIONS = {"admin_1", "admin_2"}


def build_export(positions: list[dict]) -> dict:
    """
    Envuelve la lista de posiciones (cada una con 'transactions' y 'dividends')
    en el sobre de backup con versión y timestamp.
    """
    return {
        "version": BACKUP_VERSION,
        "exported_at": datetime.utcnow().isoformat(timespec="seconds"),
        "positions": positions,
    }


@dataclass
class ImportResult:
    positions_found: int = 0
    positions_skipped: int = 0
    transactions_added: int = 0
    dividends_added: int = 0
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "positions_found": self.positions_found,
            "positions_skipped": self.positions_skipped,
            "transactions_added": self.transactions_added,
            "dividends_added": self.dividends_added,
            "errors": self.errors,
        }


def build_admin_export(
    users: list[dict], securities: list[dict], portfolios: list[dict],
    markets: list[dict] | None = None,
    app_config: list[dict] | None = None,
    tax_brackets: list[dict] | None = None,
    security_splits: list[dict] | None = None,
) -> dict:
    """Envuelve el snapshot completo del sistema en el sobre de backup admin.

    `app_config`, `tax_brackets` y `security_splits` (admin_2) permiten que el
    backup reproduzca el sitio 1:1 al restaurarlo en otro servidor. Las
    subcarteras viajan anidadas dentro de cada usuario en `portfolios`.
    """
    return {
        "version": ADMIN_BACKUP_VERSION,
        "exported_at": datetime.utcnow().isoformat(timespec="seconds"),
        "markets": markets or [],
        "app_config": app_config or [],
        "tax_brackets": tax_brackets or [],
        "security_splits": security_splits or [],
        "users": users,
        "securities": securities,
        "portfolios": portfolios,
    }


@dataclass
class AdminImportResult:
    users_created: int = 0
    users_skipped: int = 0
    users_updated: int = 0
    securities_created: int = 0
    securities_updated: int = 0
    positions_found: int = 0
    positions_skipped: int = 0
    transactions_added: int = 0
    dividends_added: int = 0
    favorites_added: int = 0
    config_keys: int = 0
    tax_brackets_set: int = 0
    splits_added: int = 0
    subcarteras_added: int = 0
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "users_created": self.users_created,
            "users_skipped": self.users_skipped,
            "users_updated": self.users_updated,
            "securities_created": self.securities_created,
            "securities_updated": self.securities_updated,
            "positions_found": self.positions_found,
            "positions_skipped": self.positions_skipped,
            "transactions_added": self.transactions_added,
            "dividends_added": self.dividends_added,
            "favorites_added": self.favorites_added,
            "config_keys": self.config_keys,
            "tax_brackets_set": self.tax_brackets_set,
            "splits_added": self.splits_added,
            "subcarteras_added": self.subcarteras_added,
            "errors": self.errors,
        }


def validate_admin_backup(data: dict) -> list[str]:
    errors: list[str] = []
    if not isinstance(data, dict):
        return ["El fichero no es un objeto JSON válido"]
    if data.get("version") not in _ACCEPTED_ADMIN_VERSIONS:
        errors.append(
            f"Versión desconocida: {data.get('version')!r} "
            f"(esperadas: {sorted(_ACCEPTED_ADMIN_VERSIONS)!r})"
        )
    for key in ("users", "securities", "portfolios"):
        if key not in data:
            errors.append(f"Falta la clave '{key}'")
        elif not isinstance(data[key], list):
            errors.append(f"'{key}' debe ser una lista")
    # Secciones opcionales: 'markets' (backups < v1.7.8 no lo traen); las de
    # admin_2 ('app_config', 'tax_brackets', 'security_splits') no vienen en
    # backups admin_1. Si aparecen, deben ser listas.
    for key in ("markets", "app_config", "tax_brackets", "security_splits"):
        if key in data and not isinstance(data[key], list):
            errors.append(f"'{key}' debe ser una lista")
    return errors


def validate_backup(data: dict) -> list[str]:
    """
    Comprueba que el JSON de backup tiene la estructura esperada.
    Devuelve una lista de mensajes de error (vacía si todo va bien).
    """
    errors: list[str] = []
    if not isinstance(data, dict):
        return ["El fichero no es un objeto JSON válido"]
    if data.get("version") != BACKUP_VERSION:
        errors.append(f"Versión desconocida: {data.get('version')!r} (esperada: {BACKUP_VERSION!r})")
    if "positions" not in data:
        errors.append("Falta la clave 'positions'")
    elif not isinstance(data["positions"], list):
        errors.append("'positions' debe ser una lista")
    return errors
