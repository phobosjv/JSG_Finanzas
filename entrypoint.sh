#!/bin/sh
set -e

cd /app

# Aplicar migraciones de base de datos
alembic upgrade head

# Arrancar la aplicacion
exec uvicorn app.main:app --host 0.0.0.0 --port 8000
