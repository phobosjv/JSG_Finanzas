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
from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
import os

from app.api import (
    admin, admin_markets, admin_splits, app_config, auth, backup,
    catalog_requests, admin_catalog_requests,
    csv_import, favorites, ghostfolio_import, markets, notifications,
    portfolio, push, reports, securities, subcarteras,
)
from app.api.deps import get_db
from app.auth.security import hash_password
from app.config import get_settings
from app.database import SessionLocal
from app.scheduler.jobs import daily_update, update_snapshots_live

log = logging.getLogger(__name__)


def _ensure_default_admin() -> None:
    """Crea el usuario admin por defecto si no existe todavÃ­a."""
    from sqlalchemy import select
    from app.models import User

    settings = get_settings()
    username = settings.admin_default_user.strip()
    password = settings.admin_default_password
    if not username or not password:
        return

    db = SessionLocal()
    try:
        existing = db.scalar(select(User).where(User.username == username))
        if existing:
            return
        db.add(User(username=username, password_hash=hash_password(password), is_admin=True))
        db.commit()
        log.info("Usuario admin por defecto creado: %s", username)
    finally:
        db.close()


def _get_snapshot_interval() -> int:
    """Lee el intervalo de snapshots en vivo desde app_config. Fallback 5 min."""
    from app.models import AppConfig
    try:
        db = SessionLocal()
        try:
            row = db.get(AppConfig, "snapshot_interval_minutes")
            return int(row.value) if row else 5
        finally:
            db.close()
    except Exception:
        return 5


def _make_scheduler() -> BackgroundScheduler:
    scheduler = BackgroundScheduler()

    def _daily_job():
        db = SessionLocal()
        try:
            daily_update(db)
        finally:
            db.close()

    def _live_job():
        db = SessionLocal()
        try:
            update_snapshots_live(db)
        finally:
            db.close()

    # Job nocturno (historia + snapshots + BCE)
    scheduler.add_job(_daily_job, "cron", hour=6, minute=30, id="daily_update")

    # Job periÃ³dico de snapshots en vivo (intervalo configurable por admin)
    interval = _get_snapshot_interval()
    scheduler.add_job(_live_job, "interval", minutes=interval, id="snapshot_live")

    return scheduler


def _ensure_vapid_keys() -> None:
    """Genera claves VAPID en app_config si no existen todavía."""
    from app.api.push import ensure_vapid_keys
    db = SessionLocal()
    try:
        ensure_vapid_keys(db)
    except Exception:
        log.exception("Error generando claves VAPID")
    finally:
        db.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    _ensure_default_admin()
    _ensure_vapid_keys()
    scheduler = _make_scheduler()
    scheduler.start()
    app.state.scheduler = scheduler   # expuesto para reschedule_job desde admin
    log.info("Scheduler iniciado")
    yield
    scheduler.shutdown(wait=False)
    log.info("Scheduler detenido")


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="Finanzas",
        description="Seguimiento de cartera de inversion",
        version="1.19.1",
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
    app.include_router(app_config.router, prefix=prefix)
    app.include_router(auth.router, prefix=prefix)
    app.include_router(admin.router, prefix=prefix)
    app.include_router(admin_markets.router, prefix=prefix)
    app.include_router(admin_splits.router, prefix=prefix)
    app.include_router(securities.router, prefix=prefix)
    app.include_router(markets.router, prefix=prefix)
    app.include_router(favorites.router, prefix=prefix)
    app.include_router(portfolio.router, prefix=prefix)
    app.include_router(reports.router, prefix=prefix)
    app.include_router(backup.router, prefix=prefix)
    app.include_router(csv_import.router, prefix=prefix)
    app.include_router(ghostfolio_import.router, prefix=prefix)
    app.include_router(push.router, prefix=prefix)
    app.include_router(subcarteras.router, prefix=prefix)
    app.include_router(catalog_requests.router, prefix=prefix)
    app.include_router(admin_catalog_requests.router, prefix=prefix)
    app.include_router(notifications.router, prefix=prefix)

    # Manifest PWA dinÃ¡mico. Debe registrarse ANTES del catch-all serve_spa
    # para que gane al fichero estÃ¡tico que genera VitePWA. Refleja el nombre
    # de la app y, si hay logo subido, lo usa como icono de la PWA.
    @app.get("/manifest.webmanifest", include_in_schema=False)
    def dynamic_manifest(db: Session = Depends(get_db)):
        from app.models import AppConfig

        name_row = db.get(AppConfig, "app_name")
        app_name = name_row.value if name_row else "JSG Soft."

        logo_data = db.get(AppConfig, "logo_data")
        logo_mime = db.get(AppConfig, "logo_mime")
        logo_updated = db.get(AppConfig, "logo_updated_at")

        if logo_data is not None and logo_mime is not None:
            ver = logo_updated.value if logo_updated else ""
            src = f"/api/config/logo?v={ver}"
            icons = [
                {"src": src, "sizes": "192x192", "type": logo_mime.value, "purpose": "any"},
                {"src": src, "sizes": "512x512", "type": logo_mime.value, "purpose": "any"},
                {"src": src, "sizes": "any", "type": logo_mime.value, "purpose": "maskable"},
            ]
        else:
            icons = [
                {"src": "/icons/icon-192.png", "sizes": "192x192", "type": "image/png"},
                {"src": "/icons/icon-512.png", "sizes": "512x512", "type": "image/png"},
            ]

        return JSONResponse(
            content={
                "name": app_name,
                "short_name": app_name,
                "description": "Seguimiento de cartera de inversiÃ³n",
                "theme_color": "#1a1a2e",
                "background_color": "#1a1a2e",
                "display": "standalone",
                "start_url": "/",
                "icons": icons,
            },
            media_type="application/manifest+json",
        )

    # Frontend compilado. En Docker se copia a /app/static (Dockerfile).
    # En desarrollo local se sirve desde frontend/dist si existe,
    # pero lo habitual es usar el servidor Vite en :5173.
    app_root = os.path.dirname(__file__)
    candidates = [
        os.path.join(app_root, "..", "static"),         # Docker: /app/static
        os.path.join(app_root, "..", "..", "frontend", "dist"),  # dev local
    ]
    static_dir = None
    for candidate in candidates:
        if os.path.isdir(candidate):
            static_dir = os.path.realpath(candidate)
            break

    if static_dir:
        assets_dir = os.path.join(static_dir, "assets")
        if os.path.isdir(assets_dir):
            app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

        @app.get("/{full_path:path}", include_in_schema=False)
        async def serve_spa(full_path: str):
            # Serve exact static file if it exists (icons, SW, manifest, â€¦)
            if full_path:
                candidate_file = os.path.realpath(os.path.join(static_dir, full_path))
                # Path traversal guard
                if candidate_file.startswith(static_dir) and os.path.isfile(candidate_file):
                    return FileResponse(candidate_file)
            # SPA fallback: let React Router handle the route
            index = os.path.join(static_dir, "index.html")
            if os.path.isfile(index):
                return FileResponse(index)
            raise HTTPException(status_code=404)

    return app


app = create_app()
