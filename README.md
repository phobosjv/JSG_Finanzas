# Finanzas — Seguimiento de cartera de inversión

Aplicación web personal y multiusuario para seguir una cartera de inversión:
bolsa española (IBEX 35, Mercado Continuo), Nasdaq, ETFs, criptomonedas y
fondos de inversión (con traspasos fiscalmente neutros). Multidivisa, con
informe fiscal IRPF, alertas de precio y notificaciones push.

## Stack

| Capa | Tecnología |
|---|---|
| Backend | FastAPI + SQLAlchemy 2.0 + Alembic + APScheduler |
| Base de datos | SQLite (fichero único, volumen persistente) |
| Datos de mercado | yfinance + API SDMX del BCE (tipos de cambio) |
| Frontend | React 18 + Vite + PWA (instalable), i18n ES/EN |
| Despliegue | Docker, 2 contenedores: `finanzas` + `caddy` (HTTPS automático con Let's Encrypt) |

---

## Despliegue con Docker (producción)

```bash
# 1. Copiar variables de entorno
cp .env.example .env
# Editar .env y poner una SECRET_KEY real:
# python -c "import secrets; print(secrets.token_hex(32))"

# 2. Arrancar
docker compose up --build -d

# 3. Crear el primer usuario (solo la primera vez)
docker compose exec finanzas python -m app.scripts.create_user admin tucontraseña

# 4. Abrir en el navegador
# Producción: https://<DOMAIN> (Caddy gestiona el certificado)
# Local con DOMAIN=localhost: http://localhost
```

El contenedor `finanzas` no expone puertos al host: todo el tráfico entra por
Caddy (80/443). El contenedor aplica las migraciones de Alembic automáticamente
en cada arranque y los datos persisten en el volumen Docker `finanzas-data`.

---

## Desarrollo local

### Requisitos

- Python 3.10+
- Node.js 15+ y npm 7+

### Backend

```bash
cd backend

# Crear entorno virtual e instalar dependencias
python -m venv venv
.\venv\Scripts\activate        # Windows
# source venv/bin/activate     # Linux/Mac

pip install -e ".[dev]"

# Variables de entorno de desarrollo
cp ../.env.example .env
# SECRET_KEY ya tiene valor por defecto en .env.example para desarrollo

# Aplicar migraciones (crea finanzas.db)
alembic upgrade head

# Crear usuario inicial
python -m app.scripts.create_user admin tucontraseña

# Arrancar servidor (con reload)
uvicorn app.main:app --reload --port 8000
```

### Frontend

```bash
cd frontend
npm install
npm run dev        # servidor en http://localhost:5173
```

Con ambos servidores activos, el frontend en `:5173` hace proxy de `/api`
hacia el backend en `:8000`.

---

## Comandos útiles

### Tests

```bash
cd backend
pytest -q
```

559 tests (pytest, SQLite en memoria): cálculo FIFO y splits, traspasos de
fondos, multidivisa, informe fiscal, retornos (XIRR / Modified Dietz),
integración de la API, notificaciones y distribución del zip.

### Migraciones

```bash
cd backend

# Aplicar migraciones pendientes
alembic upgrade head

# Generar migración nueva tras cambiar modelos
alembic revision --autogenerate -m "descripcion"
```

### Cargar histórico inicial (5 años)

```bash
cd backend
python -m app.scripts.seed_history
```

Descarga cierres diarios desde Yahoo Finance y tipos BCE para todos los valores
del catálogo. Idempotente: se puede relanzar si se interrumpe.

### Docker

```bash
# Reconstruir y reiniciar
docker compose up --build -d

# Ver logs
docker compose logs -f

# Backup manual de la BD
docker compose exec finanzas sqlite3 /data/finanzas.db ".backup /data/backup.db"
```

---

## Estructura del proyecto

```
finanzas/
├── backend/
│   ├── app/
│   │   ├── api/          # Routers FastAPI (auth, portfolio, markets, admin, push…)
│   │   ├── auth/         # Hash bcrypt + cookie de sesión (itsdangerous)
│   │   ├── models/       # Modelos SQLAlchemy (21 tablas)
│   │   ├── providers/    # yfinance, BCE, Business Insider (fuentes externas)
│   │   ├── repositories/ # Acceso a BD: traduce filas → objetos de cálculo
│   │   ├── scheduler/    # Jobs nocturnos (histórico, snapshots, tipos BCE, DCA, caducidades)
│   │   ├── schemas/      # Modelos Pydantic de entrada/salida
│   │   ├── scripts/      # create_user.py, seed_history.py
│   │   └── services/     # Lógica pura: FIFO, informe IRPF, retornos, indicadores, email
│   ├── alembic/          # Migraciones de base de datos
│   └── tests/            # 559 tests (pytest)
├── frontend/
│   └── src/
│       ├── api/          # Cliente HTTP (fetch + cookie)
│       ├── context/      # AuthContext, AppContext (i18n, tema)
│       ├── hooks/        # useSortableData, useMediaQuery
│       ├── i18n/         # translations.js (ES + EN)
│       ├── pages/        # Login, Dashboard, Markets, Portfolio, SecurityDetail, TaxReport, Utilities, AdminPanel
│       ├── components/   # Navigation, SecurityTable, gráficos, modales…
│       └── sw.js         # Service worker (PWA + notificaciones push)
├── Dockerfile            # Python; usa frontend/dist/ precompilado (sin etapa Node)
├── docker-compose.yml    # 2 servicios: caddy (80/443) + finanzas (interno)
├── Caddyfile
└── entrypoint.sh         # alembic upgrade head → uvicorn
```

---

## Reglas de negocio importantes

- **FIFO obligatorio** para el cálculo de beneficios (norma española).
- **Todo el dinero en `Decimal`**, nunca `float`. La conversión ocurre solo en
  los extremos (lectura de SQLite, serialización JSON).
- **Los datos no se almacenan precalculados**: acciones vivas y precio medio se
  derivan siempre de las transacciones.
- **Tipos de cambio del BCE** (multidivisa): `euros = importe / rate` — el BCE
  publica cada tipo como "divisa por 1 EUR". Divisas soportadas configurables
  por el administrador.
- El informe fiscal detecta la regla de los 2 meses (valores UE) y 1 año (Nasdaq)
  de forma conservadora: marca y avisa, no sentencia.
