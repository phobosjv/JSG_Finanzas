# =============================================================
#  Imagen de distribución — usa el frontend pre-compilado
#
#  El frontend (React/Vite) se compila en el equipo de desarrollo
#  con "npm run build" y el directorio frontend/dist se incluye
#  en el paquete de distribución (finanzas-vX.Y.Z.zip).
#  Docker solo necesita copiar los estáticos ya compilados;
#  no requiere Node.js ni acceso a internet para npm.
#
#  Beneficios:
#  - Imagen final más pequeña (sin Node ni node_modules).
#  - Builds más rápidos en el servidor de despliegue.
#  - Sin dependencia de npmjs.org en producción.
# =============================================================
FROM python:3.12-slim

WORKDIR /app

# Instalar dependencias Python
COPY backend/pyproject.toml ./
RUN pip install --no-cache-dir .

# Copiar código de la aplicación
COPY backend/app     ./app
COPY backend/alembic ./alembic
COPY backend/alembic.ini ./

# Copiar frontend ya compilado (incluido en el zip de distribución)
COPY frontend/dist   ./static

COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

EXPOSE 8000
ENTRYPOINT ["/entrypoint.sh"]
