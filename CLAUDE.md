# Finanzas — Seguimiento de cartera de inversión

Aplicación web personal de seguimiento de cartera de inversión (bolsa
española IBEX 35 + Mercado Continuo, y Nasdaq). Uso personal, multiusuario
con login por contraseña. Inspiración funcional: snowball-analytics.

## Stack

- **Backend**: FastAPI + SQLAlchemy 2.0 (estilo declarativo `Mapped` /
  `mapped_column`) + Alembic (migraciones) + APScheduler (jobs nocturnos).
- **BD**: SQLite, fichero único, volumen persistente.
- **Datos de mercado**: yfinance, detrás de una capa de abstracción de
  proveedores (`providers/`). Tipos de cambio EUR/USD del BCE.
- **Frontend**: React + Vite, instalable como PWA. Responsive (escritorio y
  móvil).
- **Despliegue**: contenedor Docker de servicio único, volumen persistente
  para `finanzas.db` y los backups.

## Reglas de oro (NO romper)

1. **Dinero siempre en `Decimal`, nunca `float`.** La conversión a
   `Decimal` ocurre al leer de SQLite; la conversión a `str`/`float` ocurre
   solo en la frontera de la API o de presentación. En medio, exactitud
   absoluta.
2. **Capa de cálculo pura.** `services/calculations.py` y
   `services/tax_report.py` no importan SQLAlchemy, FastAPI ni nada de I/O.
   Reciben datos, devuelven datos. Son testeables de forma aislada.
3. **Todo se deriva de `transactions`.** El número de acciones, el precio
   medio y los beneficios NO se almacenan. Se calculan aplicando FIFO sobre
   las transacciones. Una posición cerrada es la que tiene cero acciones
   vivas.
4. **FIFO obligatorio** para valores homogéneos (norma española): las
   acciones vendidas son siempre las primeras compradas.
5. **Verificar con tests** todo lo que tenga lógica no trivial. Cada test
   lleva en comentario la aritmética que justifica el resultado esperado.
6. **Explicar las decisiones de diseño antes de escribir el código.**

## Modelo de datos (SQLite)

Tablas: `users`, `user_status_log`, `securities`, `security_splits`,
`markets`, `price_history`, `price_snapshots`, `ecb_rates`, `favorites`,
`positions`, `transactions`, `dividends`, `app_config`.

- `transactions` y `dividends` llevan `currency` ('EUR'|'USD') y
  `exchange_rate` (tipo EUR/USD del BCE en la fecha de la operación; 1 para
  EUR). El BCE publica EUR/USD como "USD por 1 EUR" → `euros = dólares / rate`.
- FKs con intención: `positions.security_id` es `ON DELETE RESTRICT` (no se
  borra un valor con histórico); el resto es `CASCADE`.
- `security_splits.security_id` es `ON DELETE CASCADE`: al borrar un valor
  desaparecen sus splits.
- `user_status_log.actor_id` es `ON DELETE SET NULL` (el historial sobrevive
  aunque se borre el admin que realizó la acción).
- SQLite NO aplica claves foráneas si no se activa `PRAGMA foreign_keys=ON`
  en cada conexión.
- Esquema de referencia: `crear-tablas.sql`.

## Migraciones Alembic

Chain de revisiones (orden cronológico):
1. `d61c248a5dfa` — initial_schema
2. `9b1c2b84199f` — add_is_admin_to_users
3. `a3f9c1d2e5b4` — v1.2.0 dynamic markets
4. `c7f9e2b4d8a1` — v1.3.0 user subscriptions + app_config.app_name
5. `b2d1a3c4e5f6` — v1.4.0 security_splits

## Estructura del proyecto

`backend/app/` con subcarpetas: `models/`, `schemas/`, `api/`, `services/`,
`repositories/`, `providers/`, `scheduler/`, `auth/`, `reports/templates/`.
`backend/tests/` paralela. `frontend/` aparte. Ver `Estructura.txt`.

## Convenciones de nombres importantes

- Los **modelos SQLAlchemy de filas** se llaman `TransactionRow` y
  `DividendRow`, NO `Transaction`/`Dividend`. Esos nombres ya pertenecen a
  los dataclasses puros de `calculations.py`. Mantener la distinción evita
  colisiones de import y deja claro qué es una fila de BD y qué es un objeto
  de cálculo.
- El **repositorio** traduce `TransactionRow` → `calculations.Transaction`.
  Es el puente entre la BD y la lógica.
- `SecuritySplit` (modelo SQLAlchemy) vs `Split` (dataclass de calculations.py):
  misma distinción. El repositorio convierte `SecuritySplit` → `Split`.

## Tipo `Money` (models/base.py)

`TypeDecorator` para columnas monetarias en SQLite:
- Al escribir: `Decimal` → `float` (lo único que SQLite entiende),
  validando que no entre un `float` crudo por accidente.
- Al leer: `float` → `Decimal(str(float))`, que elimina el ruido binario
  del `REAL` de SQLite.
- **Limitación conocida y aceptada**: el camino `Decimal → float → Decimal`
  no preserva los ceros finales (`100.10` se relee como `100.1`). El valor
  es numéricamente exacto y la aritmética `Decimal` correcta; solo se pierde
  la escala textual. No afecta al cálculo ni a la presentación.

## Splits / contrasplits (v1.4.0)

Los splits son eventos corporativos globales gestionados por el admin:
- Tabla `security_splits`: `security_id`, `ex_date` (YYYY-MM-DD),
  `ratio_num` (acciones nuevas), `ratio_den` (acciones antiguas), `notes`.
- `calculations._normalize_splits()` normaliza todas las transacciones
  anteriores a `ex_date` multiplicando shares×factor y dividiendo price/factor.
  El coste total por lote se conserva (invariante matemático).
- `PortfolioRepository.splits_for_security(security_id)` carga los splits y
  los pasa a `compute_position`. Todos los call-sites lo hacen: portfolio
  abierto, cerrado, validaciones CRUD, tax_report_input, historial de cartera.
- El gráfico de evolución de cartera (`/portfolio/history`) también normaliza
  el running_shares para que sea consistente con los precios split-adjusted
  que devuelve Yahoo Finance.
- **Limitación conocida**: splits con ratios que producen decimales periódicos
  (ej. 3:2 aplicado dos veces) pueden dejar un error de centésimas en el
  coste total. Numéricamente irrelevante para presentación, pero los tests
  usan `abs(valor - esperado) < 0.01` en lugar de igualdad exacta.

## Capas y separación de responsabilidades

- `repositories/` — I/O puro: lee filas de SQLite y las traduce a objetos
  puros. No aplica FIFO, no decide nada fiscal, no redondea. Solo lectura
  para alimentar el cálculo.
- `repositories/tax_report_input.py` — orquestador: une repositorio +
  `compute_position` para producir el input completo de `build_tax_report`.
- `services/` — lógica pura, sin I/O.
- `api/` — routers FastAPI; única capa que conoce HTTP.

---

## Estado actual (mayo 2026) — v1.4.0

### Implementado y funcional

- **Auth**: login por cookie firmada (itsdangerous), hash bcrypt.
  Bloqueado si `is_enabled=False` o `expires_at` pasado (→ 403 con
  mensaje "Contactar con el administrador").
- **Modelos**: 13 tablas SQLAlchemy, 5 migraciones Alembic.
- **Providers**: yfinance (histórico + snapshot), BCE (tipos EUR/USD).
- **Scheduler**: job nocturno (06:30) que actualiza histórico, snapshots e
  indicadores; job periódico de snapshots (intervalo configurable por admin,
  5-60 min, por defecto 5 min).
- **Services**: FIFO con normalización de splits, informe fiscal IRPF,
  PDF WeasyPrint, indicadores de rango, backup.
- **API**: auth, admin (usuarios + suscripciones + historial), admin_markets,
  admin_splits, app_config (público), securities, markets, portfolio,
  favorites, reports, backup.
- **Frontend**: Login, Dashboard, Markets, Portfolio, SecurityDetail,
  Utilities (con selector de tema), AdminPanel (usuarios, mercados, valores,
  splits, configuración).
- **Sistema de roles**: `is_admin` en User; admin → AdminPanel; usuario normal
  → app completa.
- **Control de suscripciones** (v1.3.0): enable/disable, fecha de caducidad,
  historial cronológico de cambios de estado.
- **Nombre de la app personalizable** (v1.3.0): campo en `app_config`,
  aparece en login, cabecera y título del navegador.
- **Tema claro/oscuro** (v1.3.0): toggle en pie del menú lateral y en
  Utilidades; preferencia en `localStorage`.
- **Splits/contrasplits** (v1.4.0): gestión admin por valor, efecto global
  en todos los usuarios.
- **PWA + Docker** configurados.
- **Tests**: 161 en verde (pytest).

### Routers y prefijos API

| Módulo            | Prefix          | Autenticación |
|-------------------|-----------------|---------------|
| app_config        | /api/config     | ninguna       |
| auth              | /api/auth       | ninguna/user  |
| admin             | /api/admin      | require_admin |
| admin_markets     | /api/admin      | require_admin |
| admin_splits      | /api/admin      | require_admin |
| securities        | /api/securities | user/admin    |
| markets           | /api/markets    | user          |
| portfolio         | /api/portfolio  | user          |
| favorites         | /api/favorites  | user          |
| reports           | /api/reports    | user          |
| backup            | /api/backup     | user          |

### Gaps identificados (instrucciones originales vs lo construido)

Todos los puntos originales están implementados:

#### A — Dashboard
- [x] A1/A2 Top movers IBEX y Nasdaq

#### B — Explorador de Mercados
- [x] B1 Pestañas dinámicas + Favoritos
- [x] B2 IndexHeader con sparkline
- [x] B3 Columnas extendidas
- [x] B4 MinBadge naranja
- [x] B5 TargetCell editable en línea

#### C — Cartera
- [x] C1 7 tarjetas de resumen
- [x] C2 16 columnas con alertas
- [x] C3 Tabla de posiciones cerradas

#### D — SecurityDetail
- [x] D1-D5 Todos los campos y tablas

#### E — Utilidades
- [x] E1 Informe fiscal IRPF con PDF
- [x] E2 Backup/import JSON

---

## Sistema de roles

- Columna `is_admin BOOLEAN NOT NULL DEFAULT 0` en `users`.
- Router `api/admin.py` con dependencia `require_admin` (403 si no es admin):
  - `GET  /admin/users` — lista usuarios
  - `POST /admin/users` — crea usuario
  - `PATCH /admin/users/{id}/password` — cambia contraseña
  - `PATCH /admin/users/{id}/role` — cambia rol (no sobre uno mismo)
  - `PATCH /admin/users/{id}/status` — habilita/deshabilita (con anotación)
  - `PATCH /admin/users/{id}/expiry` — fecha de caducidad
  - `GET  /admin/users/{id}/history` — historial de estados
  - `DELETE /admin/users/{id}` — elimina usuario (no sobre uno mismo)
- Crear primer admin: `python -m app.scripts.create_user <user> <pass> --admin`
- Al arrancar, `_ensure_default_admin()` crea admin por defecto si
  `ADMIN_DEFAULT_USER` / `ADMIN_DEFAULT_PASSWORD` están en `.env`.

## Tipo de cambio USD

Si `sec.currency == "USD"`, `_build_position_summary` busca el registro
más reciente de `ecb_rates` y usa ese tipo. Fallback a 1 si no hay datos BCE.

---

## Comandos

```bash
# Tests
cd backend && .\venv\Scripts\python -m pytest -v

# Servidor de desarrollo
cd backend && .\venv\Scripts\uvicorn app.main:app --reload --port 8000

# Migraciones
cd backend && .\venv\Scripts\alembic upgrade head
cd backend && .\venv\Scripts\alembic revision --autogenerate -m "mensaje"

# Crear usuario / admin
cd backend && .\venv\Scripts\python -m app.scripts.create_user <username> <password> [--admin]

# Generar manual PDF
python gen_instrucciones.py

# Docker
docker compose up --build
```
