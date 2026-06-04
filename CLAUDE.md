# Finanzas — Seguimiento de cartera de inversión

> **Versión actual: 1.8.9** · **Tests: 380 en verde** · Aplicación web personal
> multiusuario para seguimiento de cartera de inversión (IBEX 35, Mercado
> Continuo, Nasdaq, ETFs, cripto, **fondos de inversión**). Inspiración
> funcional: snowball-analytics.

---

## Cómo usar este documento

CLAUDE.md se carga automáticamente al inicio de cada conversación. Está
diseñado para que un nuevo chat retome el proyecto sin contexto previo.

**Índice rápido — dónde mirar para…**

| Quiero… | Sección |
|---|---|
| Entender el stack y la arquitectura | [Stack](#stack) · [Capas](#capas-y-separación-de-responsabilidades) |
| No romper invariantes del proyecto | [Reglas de oro](#reglas-de-oro-no-romper) |
| Ver qué se ha hecho recientemente | `git log --oneline -30` y [CHANGELOG.md](CHANGELOG.md) |
| Saber el estado actual | [Estado actual](#estado-actual--v1612) |
| Entender un cálculo financiero | [Modelo de datos](#modelo-de-datos-sqlite) · [Splits](#splits--contrasplits-v140) · [Tramos IRPF](#tramos-irpf-configurables-v165) |
| Generar una nueva versión | [Metodología de release](#metodología-de-release) |
| Desplegar / actualizar VPS | [Despliegue](#despliegue-en-vps-con-https-caddy) |
| Escribir un test nuevo | [Patrones de tests](#patrones-de-tests) |
| Añadir un endpoint o feature | [Metodología de trabajo](#metodología-de-trabajo) |

---

## Stack

- **Backend**: FastAPI + SQLAlchemy 2.0 (estilo declarativo `Mapped` /
  `mapped_column`) + Alembic (migraciones) + APScheduler (jobs nocturnos).
- **BD**: SQLite, fichero único, volumen persistente.
- **Datos de mercado**: yfinance, detrás de una capa de abstracción de
  proveedores (`providers/`). Tipos de cambio EUR/USD del BCE.
- **Frontend**: React + Vite, instalable como PWA. Responsive (escritorio y
  móvil). Gráficos con `recharts`.
- **Despliegue**: dos contenedores Docker (`finanzas` + `caddy`), volumen
  persistente para `finanzas.db` y los backups. Caddy gestiona HTTPS
  automáticamente con Let's Encrypt.

---

## Reglas de oro (NO romper)

### Cálculo y datos

1. **Dinero siempre en `Decimal`, nunca `float`.** La conversión a
   `Decimal` ocurre al leer de SQLite; la conversión a `str`/`float` ocurre
   solo en la frontera de la API o de presentación. En medio, exactitud
   absoluta.
2. **Todo se deriva de `transactions`.** El número de acciones, el precio
   medio y los beneficios NO se almacenan. Se calculan aplicando FIFO sobre
   las transacciones. Una posición cerrada es la que tiene cero acciones
   vivas.
3. **FIFO obligatorio** para valores homogéneos (norma española): las
   acciones vendidas son siempre las primeras compradas.
4. **No hardcodear nada que pueda cambiar**: nombre de la app, mercados,
   splits, tipos de cambio, tramos IRPF. Todo gestionable por admin y/o
   almacenado en la BD.

### Arquitectura

5. **Capa de cálculo pura.** `services/calculations.py` y
   `services/tax_report.py` no importan SQLAlchemy, FastAPI ni nada de I/O.
6. **No mezclar responsabilidades**: repositorios para I/O puro, servicios
   para lógica pura, routers para HTTP.
7. **Distinguir modelos de BD y objetos de cálculo.** `TransactionRow` (BD) ≠
   `Transaction` (dataclass de cálculo). El repositorio traduce.
8. **El API REST es la única interfaz frontend↔backend.** No hay acceso
   directo a la BD desde el frontend.

### Calidad

9. **Verificar con tests** todo lo que tenga lógica no trivial. Cada test
   lleva en comentario la aritmética que justifica el resultado esperado.
10. **Escribir test antes de arreglar un bug.** No se arregla un bug sin un
    test que lo reproduzca y verifique la corrección.
11. **Explicar las decisiones de diseño antes de escribir el código.**
12. **Commits atómicos.** Cada commit es una unidad lógica completa con
    mensaje claro (qué y por qué). No mezclar cambios no relacionados.

### Frontend / UX

13. **Internacionalización obligatoria (ES/EN).** Todo texto visible se
    obtiene mediante `t('clave')` desde `AppContext`, **nunca hardcodeado**.
    Excepciones: nombres propios (Yahoo Ticker, ISIN, "EUR", "USD"). Al
    añadir cualquier texto se añaden simultáneamente ambas traducciones en
    `frontend/src/i18n/translations.js`.
14. **Versión visible en la UI** (sidebar, cabecera móvil, login). Se
    incrementa con cada release y se debe mostrar en interfaz.

### Operación

15. **Tras cada nueva versión generada, actualizar el changelog.** Mantener
    registro claro de cambios, mejoras y bugfixes. Después: número de
    versión en código, manual PDF, y zip de distribución.
16. **Mantener la seguridad en mente.** Proteger rutas autenticadas,
    validar entrada del usuario, manejar errores sin exponer detalles
    sensibles.

---

## Capas y separación de responsabilidades

```
┌─────────────┐   HTTP    ┌────────────┐    ┌─────────────────┐
│  Frontend   │ ←──────── │ api/       │ ─→ │ services/        │  (puro)
│  (React)    │           │ (routers)  │    │ - calculations   │
└─────────────┘           └────────────┘    │ - tax_report     │
                                │            │ - pdf_generator  │
                                ↓            └─────────────────┘
                          ┌────────────┐              ↑
                          │ repos/     │ ─────────────┘
                          │ (I/O puro) │  traduce TransactionRow → Transaction
                          └────────────┘
                                │
                                ↓
                          ┌────────────┐   ┌─────────────┐
                          │ models/    │ ← │ providers/  │  yfinance, BCE
                          │ (SQLAlch)  │   └─────────────┘
                          └────────────┘
```

- `repositories/` — I/O puro. No aplica FIFO, no decide nada fiscal, no
  redondea. Solo lectura para alimentar el cálculo.
- `repositories/tax_report_input.py` — orquestador: une repositorio +
  `compute_position` para producir el input de `build_tax_report`.
- `services/` — lógica pura, sin I/O.
- `api/` — routers FastAPI; única capa que conoce HTTP.

---

## Modelo de datos (SQLite)

**Tablas**: `users`, `user_status_log`, `securities`, `security_splits`,
`markets`, `price_history`, `price_snapshots`, `ecb_rates`, `favorites`,
`positions`, `transactions`, `dividends`, `app_config`, `tax_brackets`.

- `transactions` y `dividends` llevan `currency` (`'EUR'|'USD'`) y
  `exchange_rate` (tipo EUR/USD del BCE en la fecha; 1 para EUR). El BCE
  publica EUR/USD como "USD por 1 EUR" → `euros = dólares / rate`.
- FKs con intención: `positions.security_id` es `ON DELETE RESTRICT` (no se
  borra un valor con histórico); el resto es `CASCADE`.
- `security_splits.security_id` es `ON DELETE CASCADE`.
- `user_status_log.actor_id` es `ON DELETE SET NULL`.
- SQLite NO aplica claves foráneas si no se activa `PRAGMA foreign_keys=ON`
  en cada conexión (se hace en el factory de Session).
- Esquema de referencia: `crear-tablas.sql`.

### Migraciones Alembic (cronológico)

1. `d61c248a5dfa` — initial_schema
2. `9b1c2b84199f` — add_is_admin_to_users
3. `a3f9c1d2e5b4` — v1.2.0 dynamic markets
4. `c7f9e2b4d8a1` — v1.3.0 user subscriptions + `app_config.app_name`
5. `b2d1a3c4e5f6` — v1.4.0 `security_splits`
6. `e3f1a2b4c5d6` — v1.5.0 market `sort_order`
7. `f1a2b3c4d5e6` — v1.6.5 `tax_brackets` (con seed: 19/21/23/27/28 %)

---

## Convenciones de nombres importantes

- **Modelos SQLAlchemy** usan sufijo `Row` cuando hay confusión con el
  dataclass de cálculo: `TransactionRow`, `DividendRow`, `TaxBracketRow`,
  `MarketRow`. Mantener la distinción evita colisiones de import y deja
  claro qué es una fila de BD y qué es un objeto puro de cálculo.
- **El repositorio** traduce `TransactionRow` → `calculations.Transaction`.
  Es el puente entre la BD y la lógica.
- `SecuritySplit` (SQLAlchemy) vs `Split` (dataclass): misma distinción.
- Los `Decimal` se devuelven al JSON como **string** (por seguridad de
  precisión). En tests: `float(data["rate"]) == 19.0`, no `data["rate"] == 19.0`.

---

## Tipo `Money` (models/base.py)

`TypeDecorator` para columnas monetarias en SQLite:
- Al escribir: `Decimal` → `float` (lo único que SQLite entiende),
  validando que no entre un `float` crudo por accidente.
- Al leer: `float` → `Decimal(str(float))`, que elimina el ruido binario
  del `REAL` de SQLite.
- **Limitación**: el camino `Decimal → float → Decimal` no preserva los
  ceros finales (`100.10` se relee como `100.1`). Numéricamente exacto;
  solo se pierde la escala textual.

---

## Features detalladas

### Splits / contrasplits (v1.4.0)

- Tabla `security_splits`: `security_id`, `ex_date`, `ratio_num` (nuevas),
  `ratio_den` (antiguas), `notes`. Eventos globales gestionados por admin.
- `calculations._normalize_splits()` multiplica shares y divide price por
  el factor para todas las transacciones anteriores a `ex_date`. El coste
  total por lote se conserva (invariante).
- `PortfolioRepository.splits_for_security()` carga los splits; **todos
  los call-sites lo hacen** (portfolio abierto, cerrado, validaciones CRUD,
  tax_report_input, historial de cartera, analytics).
- El gráfico `/portfolio/history` normaliza también el `running_shares`
  para ser coherente con los precios split-adjusted de Yahoo.
- **Limitación conocida**: splits con ratios que producen decimales
  periódicos (ej. 3:2 aplicado dos veces) pueden dejar error de
  centésimas. Los tests usan `abs(valor - esperado) < 0.01`.

### Tramos IRPF configurables (v1.6.5)

- Tabla `tax_brackets`: `id`, `min_amount`, `max_amount` (NULL = sin techo),
  `rate`, `sort_order`. Editables por admin desde AdminPanel.
- Seed inicial: 0→6k 19 %, 6k→50k 21 %, 50k→200k 23 %, 200k→300k 27 %,
  >300k 28 % (vigentes 2023).
- `pdf_generator._build_tax_summary(report, brackets=None)`: si `brackets`
  es `None` usa `_BRACKETS` hardcodeado como fallback; si se pasa, usa
  esos. `api/reports.py` carga los tramos de la BD y los pasa.
- Colores del gráfico de tramos: gradiente verde→rojo por posición
  (`_bracket_color(i)`), no por valor concreto del rate.
- Endpoint público `GET /api/config/tax-brackets` (sin auth) para que el
  formulario de dividendos pueda leer el primer tramo para el botón
  "Aplicar -X %".

### Tipo de cambio automático (v1.6.5)

- `GET /api/markets/exchange-rate?date=YYYY-MM-DD`:
  1. Busca en `ecb_rates` el registro más reciente con `date <= pedida`.
  2. Si no hay, llama a `yf.Ticker("EURUSD=X").history(timeout=5)` (Yahoo).
  3. Si tampoco, devuelve `{rate: null, source: "not_found"}`.
- En el frontend, los formularios de transacción y dividendo auto-rellenan
  el campo `exchange_rate` cuando `currency=USD` y cambia la fecha. El
  campo queda editable para corrección manual.

### Hora real de Yahoo (v1.6.10)

- `LiveQuote.quote_time: str | None` — timestamp del último trade
  reportado por Yahoo, extraído del index del DataFrame de `history()`.
- El scheduler usa `quote.quote_time` (si está) en lugar de
  `datetime.now()` al guardar el snapshot. Así "Precios actualizados:"
  refleja la hora EN ORIGEN, no la del scheduler.

### Marca vs nombre de la app (v1.6.7)

- **"JSG Soft."** es el nombre del distribuidor, **hardcodeado** en el
  código (en defaults, manifest PWA, título del navegador).
- **Nombre de la aplicación** (ej. "JSG Portfolio") es **configurable por
  el admin** desde AdminPanel → Configuración. Se guarda en
  `app_config.app_name`. Aparece en sidebar, cabecera móvil y login.
- PWA instalado muestra "JSG Soft. - {app_name}" como título.

### PWA (v1.6.6)

- Configurado con `vite-plugin-pwa`. Manifest en `vite.config.js`.
- **Iconos imprescindibles**: `frontend/public/icons/icon-192.png` y
  `icon-512.png`. Sin ellos los navegadores no muestran el botón de
  instalación aunque VitePWA esté correctamente configurado. Hay tests en
  `test_distribution.py` que verifican que existen y son PNG válidos.

### Scatter plot de posiciones cerradas (v1.6.7+)

- `GET /portfolio/closed-analytics` añade `avg_days_held` (media ponderada
  por lote FIFO) y `pnl_pct` al `ClosedPositionSummary`.
- Color de cada punto: combina rentabilidad y tiempo (v1.6.12):
  - **Positivos**: rentabilidad anualizada (`pct/años`). Verde aceituna
    `#71732B` (3 %/año) → verde intenso `#16a34a` (60 %/año).
  - **Negativos**: intensidad `|pct| × (1 + años/3)`. Naranja `#D24608`
    (intensidad 5) → rojo oscuro `#7f1d1d` (intensidad 80+).
- Paletas separadas para evitar que una ganancia parezca pérdida.
- Toggle de escala X (lineal/logarítmica) para no perder visibilidad cuando
  hay outliers de tiempo.

### Dividendos por acción (v1.6.7+)

- `GET /portfolio/dividends-by-security` agrega todos los dividendos del
  usuario por valor (consolidando múltiples posiciones del mismo security).
- Campos: `count`, `months_held` (solo tiempo activo, ceil/30.44),
  `years_held`, `avg_yield_pct`, `avg_per_share`, `total_eur`,
  `yield_on_cost` (anualizado).
- Helper interno `_months_held_active(txs)`: itera transacciones ordenadas
  por fecha, suma solo días donde `shares > 0`. Si la posición sigue
  abierta, cuenta hasta hoy.
- Por cada dividendo, calcula el capital en esa fecha con
  `compute_position(txs_until_div_date)` → `avg_cost × shares_at_date`.

---

## Estado actual — v1.6.12

### Tests: 240 en verde

Ficheros principales:
- `test_api.py` — endpoints HTTP completos (auth, portfolio, securities,
  favorites, reports, backup).
- `test_calculations.py` — FIFO, agregación, valoración.
- `test_tax_report.py` y `test_tax_fiscal_window.py` — regla de recompra.
- `test_splits.py` — normalización por splits.
- `test_bugs.py` — regresiones de bugs históricos (cada bug = un test).
- `test_portfolio_repository.py`, `test_indicators.py`, `test_backup_service.py`.
- `test_user_subscriptions.py`, `test_markets_admin.py`, `test_catalog_import.py`.
- `test_tax_brackets.py` — CRUD admin + endpoint público de tramos IRPF.
- `test_portfolio_analytics.py` — endpoints `closed-analytics`,
  `dividends-by-security`, `exchange-rate`, `LiveQuote.quote_time`.
- `test_distribution.py` — coherencia Dockerfile/zip, iconos PWA, `entrypoint.sh` sin BOM.

### Routers y prefijos API

| Módulo            | Prefix          | Autenticación |
|-------------------|-----------------|---------------|
| app_config        | /api/config     | **ninguna** (público) |
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

### Endpoints especiales a recordar

- `GET /api/config` — público, devuelve `{app_name}`.
- `GET /api/config/tax-brackets` — público, lista los tramos.
- `GET /api/markets/exchange-rate?date=YYYY-MM-DD` — auth user, devuelve
  `{rate, date, source}` con `source ∈ {ecb, yahoo, not_found}`.
- `GET /api/portfolio/closed-analytics` — para el scatter de cerradas.
- `GET /api/portfolio/dividends-by-security` — tabla/gráficos dividendos.
- `GET /api/portfolio/history` — evolución de valor de cartera.
- `POST /api/markets/refresh-all` — admin, fuerza refresh de todos los snapshots.
- `POST /api/admin/force-history-update` — admin, recálculo histórico completo.

### Resumen de versiones recientes

> **Para el detalle completo: `git log --oneline -30` o [CHANGELOG.md](CHANGELOG.md).**

| Versión | Highlight |
|---|---|
| 1.6.12 | Paletas separadas (verde aceituna→verde, naranja→rojo) en scatter cerradas |
| 1.6.11 | Color por rentabilidad anualizada + tiempo en scatter cerradas |
| 1.6.10 | Hora real Yahoo, bar chart dividendos clickable, scroll vertical >10 |
| 1.6.9  | Tabla dividendos años/meses, scatter log scale, scrollbar oscuro |
| 1.6.8  | Fix dividendos `NameError DivRow`, scatter log scale, layout distribución |
| 1.6.7  | Rediseño Mi Cartera, scatter cerradas, tabla+gráficos dividendos. Rebranding JSG Soft. |
| 1.6.6  | PWA instalable (iconos), cálculo automático dividendos, botón editar solo admin |
| 1.6.5  | Tramos IRPF configurables, retención dividendos, tipo cambio automático |
| 1.6.4  | Caddy + HTTPS automático |
| 1.6.3  | Botón forzar actualización historial |
| 1.6.2  | Fix caída artificial en gráfico cartera (auto_adjust dividendo) |
| 1.6.1  | Buscador en mercados por ticker y nombre |
| 1.6.0  | Top movers en Dashboard |
| 1.5.0  | ETFs/cripto, idioma ES/EN, orden mercados |

### Limitaciones conocidas

- **Splits con ratios periódicos** (ej. 3:2 doble) pueden producir error de
  centésimas en el coste total. Numéricamente irrelevante, los tests usan
  tolerancia `< 0.01`.
- **Money** no preserva ceros finales (`100.10 → 100.1`). Aritmética
  exacta, solo escala textual.
- **Divisas**: solo EUR y USD. ETFs/securities en GBP u otros mercados no
  están soportados por el motor de cálculo.

---

## Sistema de roles y auth

- Columna `is_admin BOOLEAN NOT NULL DEFAULT 0` en `users`.
- Auth por cookie firmada (`itsdangerous`), password con bcrypt.
- Bloqueado si `is_enabled=False` o `expires_at` pasado → 403
  "Contactar con el administrador".
- Router `api/admin.py` con dependencia `require_admin` (403 si no es admin).
- Crear primer admin: `python -m app.scripts.create_user <user> <pass> --admin`
- Al arrancar, `_ensure_default_admin()` crea admin si
  `ADMIN_DEFAULT_USER` / `ADMIN_DEFAULT_PASSWORD` están en `.env`.

---

## Despliegue en VPS con HTTPS (Caddy)

- **2 contenedores**: `caddy` (puertos 80/443) + `finanzas` (puerto 8000
  interno, sin exponer al host).
- Caddy obtiene y renueva certificados Let's Encrypt automáticamente.
- Dominio en `.env` mediante `DOMAIN`.
- Para pruebas locales sin dominio: `DOMAIN=localhost` (Caddy sirve HTTP).
- `Caddyfile` típico en VPS:
  ```
  jsg-portfolio.com www.jsg-portfolio.com {
      reverse_proxy finanzas:8000
  }
  ```
- **Importante**: tras descomprimir el zip en el VPS, restaurar el
  `Caddyfile` real (el del zip usa `{$DOMAIN}` genérico) antes del
  `docker compose up`.

---

## Metodología de trabajo

Esta sección es **operacional**: cómo hacer cambios y releases sin saltarse pasos.

### Flujo de trabajo típico para una nueva feature

1. **Explorar primero, escribir después.** Usar la herramienta Explore
   (agente) para encontrar el código relevante antes de proponer cambios.
2. **Cuando la tarea es no trivial**: entrar en plan mode, escribir el plan
   en `~/.claude/plans/`, validarlo con el usuario antes de tocar nada.
3. **Preguntar las dudas ANTES de implementar**, no después. Si hay
   ambigüedad sobre el cálculo (qué fecha usar, qué pondera, etc.),
   `AskUserQuestion` con opciones concretas.
4. **Implementación**:
   - Backend primero (modelos → schemas → migración → repos → services → API).
   - Frontend después (componentes → traducciones ES+EN).
   - Tests al final pero antes del commit.
5. **Commits atómicos por funcionalidad**, no por fichero. Mensaje
   explicando el "por qué".
6. **Tests siempre en verde antes del commit**:
   `cd backend && .\venv\Scripts\python.exe -m pytest tests\ -q`

### Metodología de release

> **Esta secuencia es OBLIGATORIA**. Saltarse el `npm run build` deja el
> `frontend/dist/` desactualizado y el usuario despliega una versión donde
> los cambios no se ven aunque el código esté correcto.

```
1. Bump versión en 4 ficheros (sed)
2. Actualizar CHANGELOG.md con la nueva entrada
3. pytest — todo en verde
4. cd frontend && npm run build       ← IMPRESCINDIBLE
5. python gen_instrucciones.py        (regenera PDF)
6. printf '#!/bin/sh\n...' > entrypoint.sh   ← debe empezar 0x23 0x21
7. Generar zip (script Python al final de este documento)
8. git add ... && git commit con resumen claro
```

#### Bump de versión (4 ficheros)

```bash
sed -i 's/version="X.Y.Z"/version="X.Y.W"/' backend/app/main.py
sed -i 's/"version": "X.Y.Z"/"version": "X.Y.W"/' frontend/package.json
sed -i 's/version = "X.Y.Z"/version = "X.Y.W"/' backend/pyproject.toml
sed -i 's/VERSION = "X.Y.Z"/VERSION = "X.Y.W"/' gen_instrucciones.py
```

#### Generación del zip

El zip contiene el frontend **precompilado** para que el Docker en VPS no
necesite Node ni acceso a npm.

**Excluir siempre**:
- `.git/`, `.claude/`
- `backend/venv/`, `backend/.venv/`, `frontend/node_modules/`
- `backend/finanzas.egg-info/`
- `__pycache__/`, `.pytest_cache/`, `.mypy_cache/`, `htmlcov/`
- `backend/.env` (credenciales reales)
- `*.db`, `*.db-shm`, `*.db-wal`, `*.pyc`, `*.pyo`, `*.log`
- `CLAUDE.md`, `gen_instrucciones.py`
- `finanzas-vX.Y.Z.zip` (el propio zip)

**Incluir siempre**:
- `frontend/dist/` (precompilado — imprescindible)
- `frontend/src/`, `frontend/package*.json`, `frontend/vite.config.js`
- Todo `backend/app/`, `backend/alembic/`, `backend/tests/`
- `Dockerfile`, `docker-compose.yml`, `Caddyfile`, `entrypoint.sh`, `.dockerignore`
- `.env.example`, `instrucciones.pdf`, `CHANGELOG.md`, `README.md`
- `catalogo-valores.json`, `catalogo-etfs-completo.json`, `catalogo-crypto.json`

**Verificaciones obligatorias antes de commit**:
- `entrypoint.sh` en zip empieza con `0x23 0x21` (`#!`, sin BOM)
- No contiene `backend/.env`, `.claude/`, `CLAUDE.md`
- Contiene `frontend/dist/assets/*.js` con timestamp reciente
- Iconos PWA presentes en `frontend/dist/icons/`

#### Script de generación de zip

```python
# Ejecutar desde la raíz del proyecto
import zipfile, os

VERSION = "X.Y.Z"   # actualizar
zip_name = f"finanzas-v{VERSION}.zip"

EXCLUDE_DIRS = {'.git', '.claude', 'venv', '.venv', 'node_modules',
                'finanzas.egg-info', '__pycache__', '.pytest_cache',
                '.mypy_cache', 'htmlcov'}
EXCLUDE_FILES = {'backend/.env', 'CLAUDE.md', 'gen_instrucciones.py'}
EXCLUDE_EXT   = {'.pyc', '.pyo', '.log', '.db', '.db-shm', '.db-wal'}

def should_exclude(rel):
    parts = rel.split('/')
    if any(p in EXCLUDE_DIRS for p in parts): return True
    if rel in EXCLUDE_FILES: return True
    _, ext = os.path.splitext(rel)
    if ext in EXCLUDE_EXT: return True
    base = os.path.basename(rel)
    if base.startswith('finanzas-v') and base.endswith('.zip'): return True
    return False

count = 0
with zipfile.ZipFile(zip_name, 'w', zipfile.ZIP_DEFLATED) as zf:
    for root, dirs, files in os.walk('.'):
        dirs[:] = [d for d in sorted(dirs) if d not in EXCLUDE_DIRS and not d.startswith('.')]
        for file in sorted(files):
            full = os.path.join(root, file)
            rel  = os.path.relpath(full, '.').replace(os.sep, '/')
            if should_exclude(rel): continue
            zf.write(full, rel); count += 1
print(f"ZIP: {zip_name}  ({count} ficheros)")
```

#### Dockerfile para distribución

El `Dockerfile` actual usa `frontend/dist/` precompilado directamente
(sin etapa Node). Correcto para el zip. **No añadir** la etapa
`FROM node:20-alpine` — solo sirve para CI/CD que compilan desde fuente.

### Despliegue en VPS — pasos

Para desplegar el zip en el VPS:
1. `docker compose down` (libera puertos, conserva volúmenes/BD)
2. Limpiar `/opt/jsg-portfolio/` excepto `.env`
3. Copiar y descomprimir el nuevo zip
4. **Restaurar el Caddyfile real** con los dominios (`jsg-portfolio.com` etc.)
5. `docker compose up --build -d`
6. Verificar `docker compose logs caddy` busca "certificate obtained successfully"

---

## Patrones de tests

### Fixtures principales en `backend/tests/conftest.py`

- `engine` — SQLite en memoria con `foreign_keys=ON` y schema creado.
- `db` — Session limpia.
- `client` — TestClient sin sesión.
- `auth_client` — TestClient con sesión de usuario normal.
- `admin_client` — TestClient con sesión de admin.
- `test_user`, `test_admin` — usuarios insertados directamente.
- `seed_markets` — inserta IBEX/Continuo/Nasdaq.

### Patrón CRUD admin

```python
def test_admin_crea_X(admin_client):
    resp = admin_client.post("/api/admin/X", json={...})
    assert resp.status_code == 201
    data = resp.json()
    # Decimal vienen como string en JSON:
    assert float(data["rate"]) == 19.0   # NO data["rate"] == 19.0

def test_create_X_no_admin(auth_client):
    resp = auth_client.post("/api/admin/X", json={...})
    assert resp.status_code == 403
```

### Helpers comunes en `test_api.py`

```python
def _crear_security(client, ticker="SAN.MC"): ...
def _buy(client, pos_id, shares, price, d="2024-01-10", fee="0"): ...
def _sell(client, pos_id, shares, price, d="2024-06-01", fee="0"): ...
def _div(client, pos_id, shares, gross_per_share, d="..."): ...
```

### Test de regresión de bug

Cada bug arreglado se documenta en `test_bugs.py` con:
- Comentario explicando qué era el bug y por qué fallaba.
- El escenario mínimo que lo reproduce.
- Aritmética esperada en comentario.

---

## Frontend — convenciones y componentes clave

### Estructura

```
frontend/src/
├── pages/        — Dashboard, Markets, Portfolio, SecurityDetail, Utilities, AdminPanel, Login
├── components/   — PortfolioChartsPanel, SecurityTable, SecurityCard, Navigation
├── context/      — AuthContext (user, login, logout), AppContext (t, appName, theme, locale)
├── i18n/         — translations.js (ES+EN obligatorio)
├── api/          — client.js (fetch wrapper, dispara auth:logout en 401)
└── styles/       — global.css (variables CSS, dark/light theme)
```

### Helpers reutilizables

- `tableScrollStyle(count)` (en `Portfolio.jsx` y `SecurityDetail.jsx`):
  devuelve `{maxHeight: 540, overflowY: 'auto'}` si `count > 10`.
- `fmtYearsMonths(months)` (en `Portfolio.jsx`): "X año(s) y Y mes(es)".
- `pnlColor(pct, days)` (en `PortfolioChartsPanel.jsx`): color del scatter
  combinando rentabilidad y tiempo.
- Cabeceras de tabla **sticky** por defecto (CSS `th { position: sticky }`).

### PortfolioChartsPanel.jsx

Exporta componentes individuales para que `Portfolio.jsx` pueda componer
layouts custom (no solo el panel completo):
- `DistributionChart`, `PnLChart`, `HistoryChart` (originales).
- `ClosedScatterChart`, `DividendBarChart`, `DividendScatterChart` (v1.6.7+).

### Permisos en UI

- `useAuth().user?.is_admin` para mostrar/ocultar controles solo-admin
  (ej. botón "Editar" en SecurityDetail solo aparece para admin).

### Toggles en gráficos

- Scatter `ClosedScatterChart` y `DividendScatterChart` tienen toggle
  "Eje X lineal / logarítmico" con el mismo estilo visual.
- En escala log, los datos con valor 0 en X se filtran para evitar log(0).

---

## Comandos

```powershell
# Tests (Windows con venv)
cd backend; .\venv\Scripts\python.exe -m pytest tests\ -v

# Tests rápido (silencioso)
cd backend; .\venv\Scripts\python.exe -m pytest tests\ -q

# Servidor de desarrollo backend
cd backend; .\venv\Scripts\uvicorn.exe app.main:app --reload --port 8000

# Dev server frontend
cd frontend; npm run dev

# Build frontend (obligatorio antes del zip)
cd frontend; npm run build

# Migraciones
cd backend; .\venv\Scripts\alembic.exe upgrade head
cd backend; .\venv\Scripts\alembic.exe revision --autogenerate -m "mensaje"

# Crear usuario / admin
cd backend; .\venv\Scripts\python.exe -m app.scripts.create_user <username> <password> [--admin]

# Generar manual PDF
python gen_instrucciones.py

# Docker (local con DOMAIN=localhost)
docker compose up --build
```

---

## Notas operativas (lecciones aprendidas)

- **Reinicio del servicio uvicorn en Windows**: verificar instancias
  fantasma con `tasklist | findstr python` antes y después del reinicio.
- **Tras tocar frontend, recompilar antes de hacer zip.** `npm run build`
  no es opcional, regenera `frontend/dist/`.
- **Commits inmediatos tras cada cambio funcional**, no acumular.
- **`entrypoint.sh` debe crearse con `printf` desde Bash**, nunca con
  editores Windows o `Set-Content` de PowerShell (añaden BOM).
- **Decimal en JSON viene como string** — en tests, convertir a `float`
  para comparar valores numéricos.
- **El test `test_distribution.py` verifica el zip más reciente**: ejecutar
  los tests *después* de generar el zip detecta problemas como iconos PWA
  faltantes o `entrypoint.sh` con BOM.
