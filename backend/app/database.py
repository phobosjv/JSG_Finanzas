"""
database.py
===========
Engine SQLAlchemy, fabrica de sesiones y dependencia FastAPI.

PRAGMA foreign_keys=ON
----------------------
SQLite no aplica claves foraneas a menos que se active el pragma en CADA
conexion nueva. El listener 'connect' lo garantiza sin excepcion: se dispara
justo despues de que SQLite abre el fichero, antes de que SQLAlchemy use la
conexion para cualquier otra cosa.

check_same_thread=False
-----------------------
SQLite por defecto prohíbe usar una conexion desde un hilo distinto al que
la creo. FastAPI puede ejecutar distintas partes de una peticion en hilos
diferentes (p.ej. dependencias vs. endpoint). check_same_thread=False
deshabilita esa comprobacion; es seguro porque SQLAlchemy gestiona el pool
y garantiza que cada sesion usa su propia conexion.
"""

from collections.abc import Generator

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings


def _build_engine(database_url: str) -> Engine:
    connect_args = {}
    if database_url.startswith("sqlite"):
        connect_args["check_same_thread"] = False

    engine = create_engine(database_url, connect_args=connect_args)

    if database_url.startswith("sqlite"):
        @event.listens_for(engine, "connect")
        def _set_sqlite_pragma(dbapi_conn, _connection_record):
            dbapi_conn.execute("PRAGMA foreign_keys=ON")

    return engine


_settings = get_settings()
engine: Engine = _build_engine(_settings.database_url)

SessionLocal: sessionmaker[Session] = sessionmaker(
    bind=engine,
    autocommit=False,
    autoflush=False,
)


def get_db() -> Generator[Session, None, None]:
    """
    Dependencia FastAPI: abre una sesion por peticion y la cierra al final.

    Uso:
        @router.get("/algo")
        def endpoint(db: Session = Depends(get_db)):
            ...
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
