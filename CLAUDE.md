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

Tablas: `users`, `securities`, `price_history`, `price_snapshots`,
`ecb_rates`, `favorites`, `positions`, `transactions`, `dividends`.

- `transactions` y `dividends` llevan `currency` ('EUR'|'USD') y
  `exchange_rate` (tipo EUR/USD del BCE en la fecha de la operación; 1 para
  EUR). El BCE publica EUR/USD como "USD por 1 EUR" → `euros = dólares / rate`.
- FKs con intención: `positions.security_id` es `ON DELETE RESTRICT` (no se
  borra un valor con histórico); el resto es `CASCADE`.
- SQLite NO aplica claves foráneas si no se activa `PRAGMA foreign_keys=ON`
  en cada conexión.
- Esquema de referencia: `crear-tablas.sql`.

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

## Capas y separación de responsabilidades

- `repositories/` — I/O puro: lee filas de SQLite y las traduce a objetos
  puros. No aplica FIFO, no decide nada fiscal, no redondea. Solo lectura
  para alimentar el cálculo.
- `repositories/tax_report_input.py` — orquestador: une repositorio +
  `compute_position` para producir el input completo de `build_tax_report`.
- `services/` — lógica pura, sin I/O.
- `api/` — routers FastAPI; única capa que conoce HTTP.

---

## Estado actual (mayo 2026)

### Implementado y funcional

- **Auth**: login por cookie firmada (itsdangerous), hash bcrypt.
- **Modelos**: 9 tablas SQLAlchemy, migraciones Alembic.
- **Providers**: yfinance (histórico + snapshot), BCE (tipos EUR/USD).
- **Scheduler**: job nocturno (06:30) que actualiza histórico, snapshots e indicadores.
- **Services**: FIFO, informe fiscal IRPF, PDF WeasyPrint, indicadores de rango, backup.
- **API**: auth, admin, securities, markets, portfolio, favorites, reports, backup.
- **Frontend**: Login, Dashboard, Markets, Portfolio, SecurityDetail, Utilities, AdminPanel.
- **Sistema de roles**: `is_admin` en User; admin gestiona usuarios desde AdminPanel; usuarios normales no ven el panel de admin.
- **PWA + Docker** configurados.
- **Tests**: 103 en verde.

### Gaps identificados (instrucciones originales vs lo construido)

Los siguientes puntos están en las instrucciones originales del usuario pero
**no están implementados** o están incompletos. Deben abordarse por orden
de prioridad. No eliminar esta lista hasta que cada punto esté completado.

#### A — Dashboard (al hacer login)
- [x] **A1** Top 5 valores que más suben y más bajan del IBEX ese día.
- [x] **A2** Top 5 valores que más suben y más bajan del Nasdaq ese día.
  - Implementado: `GET /markets/top-movers?market=ibex35&n=5&direction=up|down`
    lee `price_snapshots` y ordena por `daily_change_pct`. Dashboard muestra
    dos secciones (IBEX y Nasdaq) con las tablas de mayores subidas/bajadas.

#### B — Explorador de Mercados (`Markets.jsx`)
- [x] **B1** Cuatro pestañas: IBEX 35 / Mercado Continuo / Nasdaq / Favoritos.
  La pestaña Favoritos muestra icono papelera en lugar de estrella.
- [x] **B2** `IndexHeader` con nombre, precio, variación % y `Sparkline` SVG
  del último año. Caché 15 min (cotización) y 1 h (histórico) en memoria.
- [x] **B3** Columnas: ISIN, Google Ticker, Mín 1a/2a/5a, Máx 1a, Dividendo.
- [x] **B4** Badge naranja `MinBadge`: "Mín 5a" > "Mín 2a" > "Mín 1a" cuando
  `last_price ≤ mínimo`. Sin parpadeo.
- [x] **B5** `TargetCell` editable en línea (solo favoritos); `PATCH /favorites/{id}`;
  columna "% hasta objetivo"; indicador `¡Comprar!` verde parpadeante.

#### C — Cartera (`Portfolio.jsx` + API)
- [x] **C1** 7 tarjetas de resumen: Invertido, Valor actual, Diferencia (€+%),
  B/P latente, Dividendos, Var. hoy, Beneficio realizado.
- [x] **C2** 16 columnas en tabla de posiciones abiertas con todos los campos
  solicitados; `TargetSellCell` editable; alerta `¡Vender!` parpadeante.
- [x] **C3** Tabla de posiciones cerradas (endpoint `GET /portfolio/closed`).

#### D — Explorador individual de valor (`SecurityDetail.jsx`)
- [x] **D1** ISIN y Google Ticker en cabecera.
- [x] **D2** Tarjetas: Invertido, B/P latente (con %), Dividendos neto, Beneficio total.
- [x] **D3** Tablas separadas: Compras y Ventas.
- [x] **D4** Columna "Total op." en ambas tablas.
- [x] **D5** `AddDivModal` para añadir dividendos desde la pantalla de detalle.

#### E — Utilidades (`Utilities.jsx`)
- [x] **E1** Card "Informe fiscal (IRPF)" con selector de año y botón
  "Descargar PDF" → `GET /api/reports/tax/{year}`.
- [x] **E2** Backup/import JSON implementado.

#### F — Backend / API
- [x] **F1** Endpoint `GET /markets/top-movers` — implementado con `direction=up|down`, `n` configurable.
- [x] **F2** `PositionSummary` extendido con todos los campos de C2.
- [x] **F3** Endpoint `GET /portfolio/closed` implementado.
- [x] **F4** `price_snapshots` incluye `min_1y`, `min_2y`, `min_5y`, `max_1y`. El
  modelo, el scheduler (`compute_ranges`) y los schemas ya lo cubren.
- [x] **F5** `POST /portfolio/{position_id}/dividends` ya existe; botón añadido en SecurityDetail (AddDivModal).

---

## Sistema de roles (añadido post-spec)

- Columna `is_admin BOOLEAN NOT NULL DEFAULT 0` en `users`.
- Router `api/admin.py` con dependencia `require_admin` (403 si no es admin):
  - `GET /admin/users` — lista usuarios
  - `POST /admin/users` — crea usuario (con is_admin opcional)
  - `PATCH /admin/users/{id}/password` — cambia contraseña
  - `PATCH /admin/users/{id}/role` — cambia rol (no sobre uno mismo)
  - `DELETE /admin/users/{id}` — elimina usuario (no sobre uno mismo)
- `UserOut` incluye `is_admin`; el frontend bifurca en `App.jsx`:
  admin → `AdminPanel.jsx` (solo gestión de usuarios), normal → app completa.
- Crear primer admin: `python -m app.scripts.create_user <user> <pass> --admin`

## Tipo de cambio USD (corrección post-spec)

`_build_position_summary` consultaba `current_rate = Decimal("1")` para todos los
valores. Ahora, si `sec.currency == "USD"`, busca el registro más reciente de
`ecb_rates` y usa ese tipo. Si no hay tipo BCE disponible, fallback a 1.

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

# Docker
docker compose up --build
```
