"""
models/base.py
==============
Base declarativa de SQLAlchemy y tipos de columna compartidos.

El problema del dinero en SQLite
--------------------------------
SQLite no tiene un tipo decimal nativo: las columnas REAL son coma flotante
binaria de 64 bits. Si una columna monetaria se mapea sin cuidado, SQLAlchemy
devuelve 'float' y se rompe la invariante del proyecto ("todo en Decimal,
nunca float") justo en la frontera de entrada.

'Numeric(asdecimal=True)' hace que SQLAlchemy entregue Decimal al leer, pero
sobre SQLite ese Decimal se reconstruye DESDE el float almacenado y puede
arrastrar ruido binario: Decimal('100.00000000000001').

'Money' resuelve las dos mitades:
  * Al ESCRIBIR: acepta Decimal/int/str y guarda float (lo unico que SQLite
    entiende), pero validando que no entre un float crudo por accidente.
  * Al LEER: reconstruye el Decimal pasando por str(), que es la unica via
    para obtener el Decimal "limpio" que esperan calculations.py y los tests.

El redondeo NO se hace aqui: este tipo conserva el valor; redondear es
competencia exclusiva de la capa de presentacion (round_money / _fmt_money).
"""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import Float, TypeDecorator
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Base declarativa unica para todos los modelos del proyecto."""
    pass


class Money(TypeDecorator):
    """
    Columna monetaria segura para SQLite.

    Python <-> BD:
      - bind  (escribir): Decimal -> float, validando el tipo de entrada.
      - result (leer):    float   -> Decimal(str(float)), Decimal limpio.

    Es 'cache_ok' porque no tiene estado mutable: SQLAlchemy puede cachear
    los planes de consulta que lo usan.
    """

    impl = Float
    cache_ok = True

    def process_bind_param(self, value, dialect):
        """Valor que va HACIA la base de datos."""
        if value is None:
            return None
        # Un float crudo aqui es un sintoma de que alguien salto la capa
        # Decimal. Se permite (no romper escrituras legitimas) pero el punto
        # de entrada correcto es Decimal/int/str.
        if isinstance(value, Decimal):
            return float(value)
        if isinstance(value, (int, str)):
            return float(Decimal(value))
        if isinstance(value, float):
            return value
        raise TypeError(
            f"Money no admite el tipo {type(value).__name__}; "
            f"use Decimal, int o str."
        )

    def process_result_value(self, value, dialect):
        """Valor que viene DESDE la base de datos."""
        if value is None:
            return None
        # str() es el puente: Decimal(str(0.1)) == Decimal('0.1'),
        # mientras que Decimal(0.1) == Decimal('0.1000000000000000055...').
        return Decimal(str(value))
