#!/bin/sh
set -e

# Aplicar migraciones de base de datos
cd /app/backend
alembic upgrade head

# Arrancar la aplicacion
exec uvicorn app.main:app --host 0.0.0.0 --port 8000
