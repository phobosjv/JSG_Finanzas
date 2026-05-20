# =============================================================
#  Etapa 1: compilar el frontend (Node) — BUILD ONLY
#
#  Esta etapa NO forma parte de la imagen final. El escáner puede
#  reportar CVEs aquí, pero el artefacto que se copia al stage 2
#  son únicamente ficheros estáticos (HTML/JS/CSS), no binarios
#  de Node ni sus dependencias. Las vulnerabilidades de esta etapa
#  no tienen impacto en tiempo de ejecución.
# =============================================================
FROM node:20-alpine AS frontend
WORKDIR /build
COPY frontend/package*.json ./
RUN npm ci --prefer-offline
COPY frontend/ ./
RUN npm run build

# =============================================================
#  Etapa 2: imagen final Python — lo único que se despliega
#
#  CVEs residuales tras apt-get upgrade:
#  Las 2 CVEs que permanecen están en libcairo2/libpango, dependencias
#  nativas obligatorias de WeasyPrint para generar PDF. No tienen
#  parche disponible en Debian Bookworm a día de hoy. Riesgo aceptado:
#  la app corre en red privada y no procesa PDF de orígenes externos.
#  Revisar en cada rebuild; se parchearán en cuanto Debian publique fix.
# =============================================================
FROM python:3.12-slim

RUN apt-get update && apt-get upgrade -y && apt-get install -y --no-install-recommends \
        libcairo2 \
        libpango-1.0-0 \
        libpangocairo-1.0-0 \
        libgdk-pixbuf-2.0-0 \
        shared-mime-info \
        fonts-liberation \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY backend/pyproject.toml ./
RUN pip install --no-cache-dir .

COPY backend/app     ./app
COPY backend/alembic ./alembic
COPY backend/alembic.ini ./

COPY --from=frontend /build/dist ./static

COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

EXPOSE 8000
ENTRYPOINT ["/entrypoint.sh"]
