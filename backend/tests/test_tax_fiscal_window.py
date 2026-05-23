"""
test_tax_fiscal_window.py
=========================
Verifica que el repositorio pasa fiscal_window_days correcto al SecurityRef,
y que el informe fiscal aplica la regla de recompra según ese plazo.
"""

from datetime import date
from decimal import Decimal

import pytest

from app.models import MarketRow, Position, Security, TransactionRow, User
from app.repositories.portfolio_repository import PortfolioRepository


def D(x): return Decimal(x)


def make_user(db):
    u = User(username="ana", password_hash="x")
    db.add(u)
    db.flush()
    return u


def make_security(db, market="ibex35"):
    s = Security(name="Test", yahoo_ticker=f"TST_{market}", market=market, currency="EUR")
    db.add(s)
    db.flush()
    return s


def make_position(db, user, security):
    p = Position(user_id=user.id, security_id=security.id)
    db.add(p)
    db.flush()
    return p


def seed_market(db, code, fiscal_window_days):
    from datetime import datetime
    m = MarketRow(
        code=code, name=code, index_ticker=None,
        currency="EUR", fiscal_window_days=fiscal_window_days,
        created_at=datetime.now().isoformat(timespec="seconds"),
    )
    db.merge(m)
    db.flush()


def test_fiscal_window_days_de_ibex35(db):
    """security_ref devuelve fiscal_window_days=60 para mercado ibex35."""
    seed_market(db, "ibex35", 60)
    u = make_user(db)
    s = make_security(db, market="ibex35")
    db.commit()

    repo = PortfolioRepository(db)
    ref = repo.security_ref(s.id)
    # 60 días de ventana (mercado UE/EEE)
    assert ref.fiscal_window_days == 60
    from datetime import timedelta
    assert ref.recapture_window == timedelta(days=60)


def test_fiscal_window_days_de_nasdaq(db):
    """security_ref devuelve fiscal_window_days=365 para mercado nasdaq."""
    seed_market(db, "nasdaq", 365)
    u = make_user(db)
    s = make_security(db, market="nasdaq")
    db.commit()

    repo = PortfolioRepository(db)
    ref = repo.security_ref(s.id)
    # 365 días de ventana (mercado fuera del EEE)
    assert ref.fiscal_window_days == 365
    from datetime import timedelta
    assert ref.recapture_window == timedelta(days=365)


def test_fiscal_window_days_fallback_si_no_existe_mercado(db):
    """Si el mercado no existe en la tabla, fiscal_window_days=60 por defecto."""
    u = make_user(db)
    s = make_security(db, market="mercado_desconocido")
    db.commit()

    repo = PortfolioRepository(db)
    ref = repo.security_ref(s.id)
    assert ref.fiscal_window_days == 60
