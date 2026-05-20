"""
services/backup.py
==================
Serialización pura para backup/restore de cartera.

Las funciones de este módulo no tocan la BD; reciben estructuras de datos
ya leídas y devuelven dicts exportables, o validan el formato de un import.
La I/O real (SELECT/INSERT) queda en api/backup.py.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


BACKUP_VERSION = "1"


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
