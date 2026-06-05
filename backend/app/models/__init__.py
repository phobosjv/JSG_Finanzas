"""
models/__init__.py
==================
Punto de entrada del paquete de modelos. Importar Base y todos los modelos
aqui garantiza que SQLAlchemy los registre en Base.metadata antes de que
Alembic o los tests llamen a create_all / drop_all.
"""

from app.models.base import Base, Money
from app.models.user import User, UserStatusLog
from app.models.security import Security, SecuritySplit
from app.models.market import MarketRow
from app.models.config import AppConfig
from app.models.price import EcbRate, PriceHistory, PriceSnapshot
from app.models.portfolio import (
    DividendRow, Favorite, Position, RecurringPlanRow, TransactionRow,
)
from app.models.tax_bracket import TaxBracketRow
from app.models.push import PushSubscription

__all__ = [
    "Base",
    "Money",
    "User",
    "UserStatusLog",
    "Security",
    "SecuritySplit",
    "MarketRow",
    "AppConfig",
    "EcbRate",
    "PriceHistory",
    "PriceSnapshot",
    "DividendRow",
    "Favorite",
    "Position",
    "RecurringPlanRow",
    "TransactionRow",
    "TaxBracketRow",
    "PushSubscription",
]
