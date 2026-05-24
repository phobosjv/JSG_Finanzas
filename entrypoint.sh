#!/bin/sh
set -e

echo "=== FJS Finanzas ==="
echo "Aplicando migraciones Alembic..."
alembic upgrade head

echo "Arrancando servidor..."
exec uvicorn app.main:app --host 0.0.0.0 --port 8000
