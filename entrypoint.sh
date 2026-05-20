#!/bin/sh
set -e
# Aplica migraciones pendientes antes de arrancar el servidor.
# En el primer arranque crea todas las tablas; en arranques posteriores
# es un no-op si el esquema ya está al día.
cd /app
alembic upgrade head
exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1
