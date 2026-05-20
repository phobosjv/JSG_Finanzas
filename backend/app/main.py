"""
main.py
=======
Crea la aplicacion FastAPI, registra los routers y arranca APScheduler.

Orden de arranque
-----------------
1. Se crea la app FastAPI.
2. Se montan los routers de la API bajo /api.
3. En el evento 'startup' se inicia el scheduler con el job nocturno.
4. En el evento 'shutdown' se detiene el scheduler limpiamente.

Ficheros estaticos del frontend
--------------------------------
En produccion (Docker) el frontend compilado se copia a /app/static y
se sirve como ficheros estaticos en la raiz. En desarrollo local el
frontend corre con Vite en :5173 y el backend en :8000; CORS permite
la comunicacion cruzada.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import os

from app.api import admin, auth, backup, favorites, markets, portfolio, reports, securities
from app.config import get_settings
from app.database import SessionLocal
from app.scheduler.jobs import daily_update

log = logging.getLogger(__name__)


def _make_scheduler() -> BackgroundScheduler:
    scheduler = BackgroundScheduler()

    def _job():
        db = SessionLocal()
        try:
            daily_update(db)
        finally:
            db.close()

    # Cada noche a las 06:30 (hora del servidor)
    scheduler.add_job(_job, "cron", hour=6, minute=30, id="daily_update")
    return scheduler


@asynccontextmanager
async def lifespan(app: FastAPI):
    scheduler = _make_scheduler()
    scheduler.start()
    log.info("Scheduler iniciado")
    yield
    scheduler.shutdown(wait=False)
    log.info("Scheduler detenido")


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="Finanzas",
        description="Seguimiento de cartera de inversion",
        version="0.1.0",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    prefix = "/api"
    app.include_router(auth.router, prefix=prefix)
    app.include_router(admin.router, prefix=prefix)
    app.include_router(securities.router, prefix=prefix)
    app.include_router(markets.router, prefix=prefix)
    app.include_router(favorites.router, prefix=prefix)
    app.include_router(portfolio.router, prefix=prefix)
    app.include_router(reports.router, prefix=prefix)
    app.include_router(backup.router, prefix=prefix)

    # Frontend compilado. En Docker se copia a /app/static (Dockerfile).
    # En desarrollo local se sirve desde frontend/dist si existe,
    # pero lo habitual es usar el servidor Vite en :5173.
    app_root = os.path.dirname(__file__)
    candidates = [
        os.path.join(app_root, "..", "static"),         # Docker: /app/static
        os.path.join(app_root, "..", "..", "frontend", "dist"),  # dev local
    ]
    for static_dir in candidates:
        if os.path.isdir(static_dir):
            app.mount("/", StaticFiles(directory=static_dir, html=True), name="static")
            break

    return app


app = create_app()
