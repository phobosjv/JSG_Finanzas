"""
models/__init__.py
==================
Punto de entrada del paquete de modelos. Importar Base y todos los modelos
aqui garantiza que SQLAlchemy los registre en Base.metadata antes de que
Alembic o los tests llamen a create_all / drop_all.
"""

from app.models.base import Base, Money
from app.models.user import User
from app.models.security import Security
from app.models.price import EcbRate, PriceHistory, PriceSnapshot
from app.models.portfolio import DividendRow, Favorite, Position, TransactionRow

__all__ = [
    "Base",
    "Money",
    "User",
    "Security",
    "EcbRate",
    "PriceHistory",
    "PriceSnapshot",
    "DividendRow",
    "Favorite",
    "Position",
    "TransactionRow",
]
