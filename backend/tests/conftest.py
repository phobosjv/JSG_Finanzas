"""
conftest.py
===========
Infraestructura compartida de todos los tests.

Fixtures de BD (para tests de repositorio y servicio)
------------------------------------------------------
- engine : SQLite en memoria con foreign_keys=ON y esquema creado.
- db     : Session limpia por test.

Fixtures de API (para tests de integración)
--------------------------------------------
- client      : TestClient sin sesión iniciada.
- auth_client : TestClient con sesión de un usuario de prueba ya activa.
- test_user   : el User creado en la BD de prueba.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.models import Base, MarketRow, User
from app.auth.security import hash_password


# ---------------------------------------------------------------------------
#  BD en memoria compartida por los tests de repositorio
# ---------------------------------------------------------------------------

@pytest.fixture()
def engine():
    # StaticPool: todas las conexiones del mismo engine comparten la misma
    # BD en memoria. Sin esto, cada conexion nueva abre una BD vacia y el
    # TestClient no ve las tablas creadas por create_all.
    eng = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(eng, "connect")
    def _fk_on(dbapi_conn, _record):
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA foreign_keys = ON")
        cur.close()

    Base.metadata.create_all(eng)
    yield eng
    Base.metadata.drop_all(eng)


@pytest.fixture()
def db(engine):
    with Session(engine) as session:
        yield session


# ---------------------------------------------------------------------------
#  TestClient de FastAPI con BD en memoria inyectada
# ---------------------------------------------------------------------------

@pytest.fixture()
def client(engine):
    """TestClient sin sesión. La BD es SQLite en memoria."""
    from app.main import app
    from app.database import get_db

    def _override_db():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_db] = _override_db
    # raise_server_exceptions=True hace que los errores 500 salten como
    # excepción en el test en lugar de devolver una respuesta opaca.
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture()
def test_user(engine) -> User:
    """Usuario de prueba insertado directamente en la BD."""
    with Session(engine) as session:
        user = User(
            username="testuser",
            password_hash=hash_password("testpass123"),
        )
        session.add(user)
        session.commit()
        session.refresh(user)
        return user


@pytest.fixture()
def auth_client(client, test_user):
    """TestClient con sesión ya iniciada (cookie presente)."""
    resp = client.post("/api/auth/login", json={
        "username": "testuser",
        "password": "testpass123",
    })
    assert resp.status_code == 200, resp.text
    return client


@pytest.fixture()
def test_admin(engine) -> User:
    """Usuario administrador de prueba insertado directamente en la BD."""
    with Session(engine) as session:
        user = User(
            username="adminuser",
            password_hash=hash_password("adminpass123"),
            is_admin=True,
        )
        session.add(user)
        session.commit()
        session.refresh(user)
        return user


@pytest.fixture()
def admin_client(client, test_admin):
    """TestClient con sesión de admin ya iniciada."""
    resp = client.post("/api/auth/login", json={
        "username": "adminuser",
        "password": "adminpass123",
    })
    assert resp.status_code == 200, resp.text
    return client


@pytest.fixture(autouse=True)
def _no_currency_backfill(monkeypatch):
    """Evita que PATCH /admin/config/currencies dispare el hilo de backfill de
    tipos BCE (red real + SessionLocal de producción) durante los tests. Los
    tests que necesiten comprobar el disparo lo re-patchean con su propio mock
    dentro del cuerpo (el último setattr gana)."""
    monkeypatch.setattr(
        "app.api.admin_markets._backfill_currency_rates",
        lambda: None,
    )
    yield


@pytest.fixture()
def seed_markets(engine):
    """Inserta los tres mercados por defecto en la BD de prueba."""
    from datetime import datetime
    with Session(engine) as session:
        for code, name, ticker, currency, days in [
            ("ibex35",   "IBEX 35",           "^IBEX",  "EUR", 60),
            ("continuo", "Mercado Continuo",   "^SMSI",  "EUR", 60),
            ("nasdaq",   "Nasdaq Composite",   "^IXIC",  "USD", 365),
        ]:
            session.merge(MarketRow(
                code=code, name=name, index_ticker=ticker,
                currency=currency, fiscal_window_days=days,
                created_at=datetime.now().isoformat(timespec="seconds"),
            ))
        session.commit()
